"""Playwright typed action、observation 和 diagnostics 执行器。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .assertions import evaluate_all
from .evidence import PendingArtifact
from .errors import VerifierError
from .locators import locator_risks, raw_locator, resolve_strict
from .limits import DEFAULT_LIMITS
from .models import ActionSpec, MUTATING_ACTIONS
from .security import redact
from .sensitivity import sanitize_url


DIAGNOSTIC_ACTIONS = {"collectConsole", "collectExceptions", "collectNetwork"}
EVALUATE_ALLOWLIST = {
    "documentTitle": "() => document.title",
    "locationHref": "() => location.href",
    "activeElement": "() => { const e = document.activeElement; return e ? {tag: e.tagName, role: e.getAttribute('role'), name: e.getAttribute('aria-label')} : null; }",
}


@dataclass
class ActionExecution:
    result: dict[str, Any]
    artifacts: list[PendingArtifact] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)


def _safe_page_url(value: str) -> str:
    return sanitize_url(value)


async def page_state(page: Any) -> dict[str, Any]:
    return {
        "url": _safe_page_url(page.url),
        "title": (await page.title())[:500],
    }


def _timeout(options: dict[str, Any], default: int = 30_000) -> int:
    value = int(options.get("timeoutMs", default))
    if value < 1 or value > 120_000:
        raise VerifierError("invalid_timeout", "action timeoutMs 必须在 1..120000")
    return value


async def _ensure_editable(locator: Any, timeout: int) -> None:
    await locator.wait_for(state="visible", timeout=timeout)
    if not await locator.is_enabled(timeout=timeout) or not await locator.is_editable(timeout=timeout):
        raise VerifierError("action_not_actionable", "目标元素不可编辑或已禁用")


async def _ensure_enabled(locator: Any, timeout: int) -> None:
    await locator.wait_for(state="visible", timeout=timeout)
    if not await locator.is_enabled(timeout=timeout):
        raise VerifierError("action_not_actionable", "目标元素已禁用")


async def execute_mutation(page: Any, action: ActionSpec) -> dict[str, Any]:
    timeout = _timeout(action.options)
    locator = await resolve_strict(page, action.locator) if action.locator is not None else None
    action_type = action.action_type
    if action_type in {"click", "doubleClick"}:
        if locator is None:
            coordinates = action.options["coordinates"]
            viewport = await page.evaluate("() => ({width: innerWidth, height: innerHeight})")
            if float(coordinates["x"]) >= float(viewport["width"]) or float(coordinates["y"]) >= float(viewport["height"]):
                raise VerifierError("coordinate_outside_viewport", "坐标动作超出当前 viewport")
            try:
                await page.mouse.click(
                    float(coordinates["x"]),
                    float(coordinates["y"]),
                    click_count=2 if action_type == "doubleClick" else 1,
                )
            except Exception as exc:
                raise VerifierError(
                    "action_outcome_unknown",
                    f"坐标动作结果未知：{type(exc).__name__}",
                    details={"outcome": "unknown"},
                ) from exc
            return {"action": action_type, "coordinate": True}
        try:
            if action_type == "click":
                await locator.click(trial=True, timeout=timeout)
            else:
                await locator.dblclick(trial=True, timeout=timeout)
        except Exception as exc:
            raise VerifierError("action_not_actionable", f"目标未通过 Playwright actionability：{type(exc).__name__}") from exc
        try:
            if action_type == "click":
                await locator.click(timeout=timeout)
            else:
                await locator.dblclick(timeout=timeout)
        except Exception as exc:
            raise VerifierError(
                "action_outcome_unknown",
                f"{action_type} 结果未知：{type(exc).__name__}",
                details={"outcome": "unknown"},
            ) from exc
        return {"action": action_type}
    if action_type == "fill":
        await _ensure_editable(locator, timeout)
        if not isinstance(action.value, str):
            raise VerifierError("invalid_action_value", "fill.value 必须是字符串")
        try:
            await locator.fill(action.value, timeout=timeout)
        except Exception as exc:
            raise VerifierError(
                "action_outcome_unknown",
                f"fill 结果未知：{type(exc).__name__}",
                details={"outcome": "unknown"},
            ) from exc
        return {"action": "fill", "characters": len(action.value)}
    if action_type == "select":
        await _ensure_enabled(locator, timeout)
        try:
            selected = await locator.select_option(action.value, timeout=timeout)
        except Exception as exc:
            raise VerifierError(
                "action_outcome_unknown",
                f"select 结果未知：{type(exc).__name__}",
                details={"outcome": "unknown"},
            ) from exc
        return {"action": "select", "selectedCount": len(selected)}
    if action_type in {"check", "uncheck"}:
        try:
            method = locator.check if action_type == "check" else locator.uncheck
            await method(trial=True, timeout=timeout)
        except Exception as exc:
            raise VerifierError(
                "action_not_actionable",
                f"{action_type} 未通过 actionability：{type(exc).__name__}",
            ) from exc
        try:
            await method(timeout=timeout)
        except Exception as exc:
            raise VerifierError(
                "action_outcome_unknown",
                f"{action_type} 结果未知：{type(exc).__name__}",
                details={"outcome": "unknown"},
            ) from exc
        return {"action": action_type}
    if action_type in {"press", "keyChord"}:
        key = action.value
        if not isinstance(key, str) or not key.strip():
            raise VerifierError("invalid_action_value", f"{action_type}.value 必须是非空按键字符串")
        key = key.replace("Mod+", "ControlOrMeta+")
        try:
            if locator is not None:
                await locator.press(key, timeout=timeout)
            else:
                await page.keyboard.press(key)
        except Exception as exc:
            raise VerifierError(
                "action_outcome_unknown",
                f"{action_type} 结果未知：{type(exc).__name__}",
                details={"outcome": "unknown"},
            ) from exc
        return {"action": action_type, "key": key}
    raise VerifierError("unsupported_action", f"不支持的 mutation：{action_type}")


def _json_artifact(value: Any, label: str) -> PendingArtifact:
    data = (json.dumps(redact(value), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return PendingArtifact("application/json", data, label, "json")


async def execute_read(
    page: Any,
    live: Any,
    action: ActionSpec,
    sensitive_masks: tuple[Any, ...] = (),
) -> ActionExecution:
    action_type = action.action_type
    timeout = _timeout(action.options)
    artifacts: list[PendingArtifact] = []
    result: dict[str, Any] = {"action": action_type}
    try:
        if action_type == "hover":
            locator = await resolve_strict(page, action.locator)
            await locator.hover(timeout=timeout)
        elif action_type == "scroll":
            value = action.value if isinstance(action.value, dict) else {}
            await page.mouse.wheel(float(value.get("deltaX", 0)), float(value.get("deltaY", 500)))
        elif action_type == "snapshot":
            backend = "aria-snapshot"
            try:
                snapshot = await page.locator("body").aria_snapshot(timeout=timeout)
            except Exception as exc:
                backend = f"bounded-inner-text-fallback:{type(exc).__name__}"
                snapshot = await page.locator("body").inner_text(timeout=timeout)
            snapshot = snapshot[:256_000]
            artifacts.append(PendingArtifact("text/plain", snapshot.encode("utf-8"), "observation", "txt"))
            result.update({"backend": backend, "characters": len(snapshot), "preview": snapshot[:2000]})
        elif action_type == "screenshot":
            mask_locators = [raw_locator(page, spec) for spec in sensitive_masks]
            for locator in mask_locators:
                if await locator.count() == 0:
                    raise VerifierError(
                        "sensitive_evidence_blocked",
                        "敏感输入对应 locator 已失效，拒绝生成 screenshot",
                    )
            try:
                data = await page.screenshot(timeout=timeout, mask=mask_locators)
            except Exception as exc:
                if mask_locators:
                    raise VerifierError(
                        "sensitive_evidence_blocked",
                        f"无法稳定 mask 敏感输入区域：{type(exc).__name__}",
                    ) from exc
                raise
            label = str(action.options.get("label") or "screenshot")[:200]
            artifacts.append(PendingArtifact("image/png", data, label, "png"))
            result.update({"bytes": len(data), "maskedLocatorCount": len(mask_locators)})
        elif action_type == "waitText":
            if not isinstance(action.value, str):
                raise VerifierError("invalid_action_value", "waitText.value 必须是字符串")
            await page.get_by_text(action.value, exact=action.options.get("exact", True) is not False).wait_for(
                state="visible", timeout=timeout
            )
            result["text"] = action.value[:500]
        elif action_type == "waitUrlContains":
            if not isinstance(action.value, str):
                raise VerifierError("invalid_action_value", "waitUrlContains.value 必须是字符串")
            await page.wait_for_url(f"**{action.value}**", timeout=timeout)
            result["matched"] = True
        elif action_type == "evaluate":
            name = str(action.value or "")
            if action.options.get("allowEvaluate") is not True or name not in EVALUATE_ALLOWLIST:
                raise VerifierError("evaluate_not_allowed", "evaluate 必须显式允许并使用内置 allowlist 名称")
            value = await page.evaluate(EVALUATE_ALLOWLIST[name])
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > DEFAULT_LIMITS.evaluate_result_bytes:
                raise VerifierError("evaluate_result_too_large", "evaluate 结果超过 256 KiB 上限")
            result["value"] = redact(value, text_limit=10_000)
        elif action_type == "extractText":
            locator = await resolve_strict(page, action.locator)
            text = await locator.inner_text(timeout=timeout)
            artifacts.append(PendingArtifact("text/plain", text[:256_000].encode("utf-8"), "extracted-text", "txt"))
            result.update({"characters": len(text), "preview": text[:2000]})
        elif action_type == "extractTable":
            locator = await resolve_strict(page, action.locator) if action.locator else page.locator("table")
            if action.locator is None and await locator.count() != 1:
                raise VerifierError("ambiguous_locator", "extractTable 默认 locator 未唯一匹配 table")
            rows = await locator.evaluate(
                "table => Array.from(table.rows).map(row => Array.from(row.cells).map(cell => cell.innerText))"
            )
            artifacts.append(_json_artifact(rows, "extracted-table"))
            result.update({"rowCount": len(rows), "preview": rows[:10]})
        elif action_type in DIAGNOSTIC_ACTIONS:
            kind = {"collectConsole": "console", "collectExceptions": "exception", "collectNetwork": "network"}[action_type]
            maximum = int(action.options.get("maxEvents", 200))
            rows = live.diagnostics.ring.select(kind, maximum, **action.options)
            artifacts.append(_json_artifact(rows, kind))
            result["eventCount"] = len(rows)
            if action_type == "collectExceptions" and rows and action.options.get("failOnException") is True:
                raise VerifierError("page_exception_detected", f"检测到 {len(rows)} 个页面异常")
        else:
            raise VerifierError("unsupported_action", f"不支持的 read action：{action_type}")
    except VerifierError:
        raise
    except Exception as exc:
        raise VerifierError("action_failed", f"{action_type} 执行失败：{type(exc).__name__}") from exc
    return ActionExecution(result=result, artifacts=artifacts, risks=locator_risks(action.locator))


async def execute_action(
    live: Any,
    action: ActionSpec,
    *,
    sensitive_masks: tuple[Any, ...] = (),
) -> ActionExecution:
    page = live.page
    before = await page_state(page)
    if action.action_type in MUTATING_ACTIONS:
        result = await execute_mutation(page, action)
        execution = ActionExecution(result=result, risks=locator_risks(action.locator))
        if action.action_type in {"click", "doubleClick"} and action.locator is None:
            execution.risks.append({"code": "coordinate_action", "learnable": False})
    else:
        execution = await execute_read(page, live, action, sensitive_masks)
    assertions = await evaluate_all(page, action.postconditions)
    execution.result.update(
        {
            "preState": before,
            "postState": await page_state(page),
            "postconditions": assertions,
        }
    )
    return execution
