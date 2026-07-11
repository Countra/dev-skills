"""唯一生产自动化后端：async Playwright CDP driver。"""

from __future__ import annotations

import contextlib
import inspect
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import VerifierError
from .diagnostics import DiagnosticRecorder
from .security import normalize_loopback_endpoint, validate_loopback_websocket


@dataclass(frozen=True)
class TargetCandidate:
    target_id: str
    title: str
    url: str
    target_type: str = "page"

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetId": self.target_id,
            "title": self.title,
            "url": self.url,
            "type": self.target_type,
        }


@dataclass
class LiveSession:
    session_id: str
    name: str
    cdp: str
    browser: Any
    context: Any
    page: Any
    target: TargetCandidate
    status: str = "connected"
    warnings: list[str] = field(default_factory=list)
    diagnostics: DiagnosticRecorder = field(default_factory=DiagnosticRecorder)


class PlaywrightCdpDriver:
    """所有方法都必须在同一个 automation event loop 中调用。"""

    def __init__(self, artifacts_dir: Path, playwright_factory: Any | None = None) -> None:
        self.artifacts_dir = artifacts_dir
        self._playwright_factory = playwright_factory
        self._playwright: Any | None = None
        self._sessions: dict[str, LiveSession] = {}

    async def start(self) -> None:
        if self._playwright is not None:
            return
        if self._playwright_factory is None:
            from playwright.async_api import async_playwright

            self._playwright_factory = async_playwright
        self._playwright = await self._playwright_factory().start()

    async def stop(self) -> None:
        for session_id in list(self._sessions):
            await self.close(session_id)
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def _connect_options(self, endpoint: str, timeout_ms: int) -> dict[str, Any]:
        assert self._playwright is not None
        connect = self._playwright.chromium.connect_over_cdp
        parameters = inspect.signature(connect).parameters
        options: dict[str, Any] = {"timeout": timeout_ms}
        if "is_local" in parameters:
            options["is_local"] = True
        if "no_defaults" in parameters:
            options["no_defaults"] = True
        if "artifacts_dir" in parameters:
            options["artifacts_dir"] = self.artifacts_dir
        return options

    def _discover_websocket(self, endpoint: str) -> str:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001,ANN201
                raise VerifierError("cdp_redirect_rejected", "CDP discovery 不允许 HTTP redirect")

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(f"{endpoint}/json/version", method="GET")
        try:
            with opener.open(request, timeout=5) as response:
                if response.status != 200:
                    raise VerifierError("cdp_discovery_failed", f"CDP discovery HTTP {response.status}", status=502)
                if int(response.headers.get("Content-Length") or 0) > 1024 * 1024:
                    raise VerifierError("cdp_discovery_too_large", "CDP discovery response 超过上限", status=502)
                raw = response.read(1024 * 1024 + 1)
        except VerifierError:
            raise
        except (OSError, urllib.error.URLError) as exc:
            raise VerifierError("cdp_discovery_failed", f"无法读取 CDP discovery：{exc}", status=502) from exc
        if len(raw) > 1024 * 1024:
            raise VerifierError("cdp_discovery_too_large", "CDP discovery response 超过上限", status=502)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerifierError("cdp_discovery_invalid", "CDP discovery 不是有效 UTF-8 JSON", status=502) from exc
        websocket = value.get("webSocketDebuggerUrl") if isinstance(value, dict) else None
        if not isinstance(websocket, str):
            raise VerifierError("cdp_discovery_invalid", "CDP discovery 缺少 webSocketDebuggerUrl", status=502)
        return validate_loopback_websocket(websocket)

    async def _connect(self, endpoint: str, timeout_ms: int = 15_000) -> Any:
        if self._playwright is None:
            raise VerifierError("driver_not_started", "Playwright driver 尚未启动", status=503)
        normalized = normalize_loopback_endpoint(endpoint)
        try:
            import asyncio

            websocket = await asyncio.to_thread(self._discover_websocket, normalized)
            return await self._playwright.chromium.connect_over_cdp(
                websocket,
                **self._connect_options(normalized, timeout_ms),
            )
        except Exception as exc:
            raise VerifierError(
                "cdp_connect_failed",
                f"Playwright 无法连接 CDP endpoint：{exc}",
                status=502,
                details={"endpoint": normalized},
            ) from exc

    async def _target_id(self, context: Any, page: Any) -> str:
        cdp_session = None
        try:
            cdp_session = await context.new_cdp_session(page)
            result = await cdp_session.send("Target.getTargetInfo")
            target_info = result.get("targetInfo") or {}
            return str(target_info.get("targetId") or "")
        except Exception:
            return ""
        finally:
            if cdp_session is not None:
                with contextlib.suppress(Exception):
                    await cdp_session.detach()

    async def _candidates(self, browser: Any) -> list[tuple[TargetCandidate, Any, Any]]:
        result: list[tuple[TargetCandidate, Any, Any]] = []
        for context in browser.contexts:
            for page in context.pages:
                if page.is_closed():
                    continue
                try:
                    title = await page.title()
                except Exception:
                    title = ""
                target_id = await self._target_id(context, page)
                result.append((TargetCandidate(target_id=target_id, title=title, url=page.url), context, page))
        return result

    def _select(
        self,
        candidates: list[tuple[TargetCandidate, Any, Any]],
        selector: dict[str, Any],
    ) -> tuple[TargetCandidate, Any, Any]:
        target_type = str(selector.get("targetType") or "page")
        if target_type != "page":
            raise VerifierError("unsupported_target_type", "Playwright CDP driver 仅支持 page target")
        filtered = candidates
        url_contains = str(selector.get("targetUrlContains") or "")
        title_contains = str(selector.get("targetTitleContains") or "")
        target_id = str(selector.get("targetId") or "")
        if url_contains:
            filtered = [item for item in filtered if url_contains in item[0].url]
        if title_contains:
            filtered = [item for item in filtered if title_contains in item[0].title]
        if target_id:
            filtered = [item for item in filtered if target_id == item[0].target_id]
        index = selector.get("targetIndex")
        if index is not None:
            if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(filtered):
                raise VerifierError(
                    "target_index_out_of_range",
                    f"targetIndex 超出候选范围：{index}",
                    details={"candidateCount": len(filtered)},
                )
            return filtered[index]
        if not filtered:
            raise VerifierError("target_not_found", "没有符合 selector 的 Electron page target", status=404)
        if len(filtered) > 1:
            raise VerifierError(
                "ambiguous_target",
                "selector 匹配多个 Electron page target，必须补充 title/url/id 或 targetIndex",
                details={"candidates": [item[0].to_dict() for item in filtered]},
            )
        return filtered[0]

    async def probe(self, endpoint: str, selector: dict[str, Any]) -> dict[str, Any]:
        browser = await self._connect(endpoint)
        try:
            candidates = await self._candidates(browser)
            selected = None
            selection_error = None
            try:
                selected = self._select(candidates, selector)[0].to_dict()
            except VerifierError as exc:
                selection_error = exc.envelope()
            return {
                "ok": True,
                "backend": "playwright-cdp",
                "browserVersion": browser.version,
                "targets": [item[0].to_dict() for item in candidates],
                "selectedTarget": selected,
                "selectionError": selection_error,
            }
        finally:
            await browser.close(reason="electron-ui-verifier probe complete")

    async def attach(
        self,
        session_id: str,
        name: str,
        endpoint: str,
        selector: dict[str, Any],
    ) -> LiveSession:
        browser = await self._connect(endpoint)
        try:
            target, context, page = self._select(await self._candidates(browser), selector)
            if not target.target_id:
                raise VerifierError("target_identity_unavailable", "无法取得稳定 CDP target identity", status=502)
        except Exception:
            await browser.close(reason="electron-ui-verifier attach failed")
            raise
        live = LiveSession(
            session_id=session_id,
            name=name,
            cdp=normalize_loopback_endpoint(endpoint),
            browser=browser,
            context=context,
            page=page,
            target=target,
        )
        page.on("close", lambda: setattr(live, "status", "stale"))
        browser.on("disconnected", lambda: setattr(live, "status", "stale"))
        live.diagnostics.bind(page)
        self._sessions[session_id] = live
        return live

    async def health(self, session_id: str) -> dict[str, Any]:
        live = self._sessions.get(session_id)
        if live is None:
            return {"connected": False, "status": "stale", "reason": "live_handle_missing"}
        if live.status != "connected" or not live.browser.is_connected() or live.page.is_closed():
            live.status = "stale"
            return {"connected": False, "status": "stale", "reason": "target_closed"}
        try:
            url = await live.page.evaluate("() => location.href")
            title = await live.page.title()
        except Exception as exc:
            live.status = "stale"
            return {"connected": False, "status": "stale", "reason": str(exc)}
        if live.target.target_id:
            current_id = await self._target_id(live.context, live.page)
            if not current_id:
                live.status = "stale"
                return {"connected": False, "status": "stale", "reason": "target_identity_unavailable"}
            if current_id != live.target.target_id:
                live.status = "stale"
                return {"connected": False, "status": "stale", "reason": "target_identity_changed"}
        return {"connected": True, "status": "connected", "url": url, "title": title}

    async def close(self, session_id: str) -> list[str]:
        live = self._sessions.pop(session_id, None)
        if live is None:
            return []
        warnings: list[str] = []
        try:
            await live.browser.close(reason="electron-ui-verifier detach")
        except Exception as exc:
            warnings.append(f"disconnect_warning: {exc}")
        live.status = "detached"
        return warnings

    def live(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)
