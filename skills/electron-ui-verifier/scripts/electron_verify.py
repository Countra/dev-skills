#!/usr/bin/env python3
"""Electron UI 验证 runner。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class VerifyError(RuntimeError):
    """用于向 CLI 返回可读错误。"""


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def require_absolute(path_text: str, label: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        raise VerifyError(f"{label} must be an absolute path: {path_text}")
    return path


def url_json(url: str, timeout: float = 5.0) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise VerifyError(f"failed to read JSON from {url}: {exc}") from exc


def normalize_cdp_endpoint(cdp: str) -> str:
    cdp = cdp.rstrip("/")
    parsed = urllib.parse.urlparse(cdp)
    if parsed.scheme not in {"http", "https"}:
        raise VerifyError("CDP endpoint must start with http:// or https://")
    if not parsed.hostname:
        raise VerifyError("CDP endpoint must include a host")
    return cdp


@dataclass
class TargetInfo:
    id: str
    type: str
    title: str
    url: str
    web_socket_debugger_url: str


@dataclass
class StepResult:
    id: str
    action: str
    status: str
    started_at: str
    ended_at: str
    backend: str
    artifacts: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class RunContext:
    cdp: str
    out_dir: Path
    backend: str = "raw-cdp"
    events: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    not_covered: list[str] = field(default_factory=list)
    backend_attempts: list[dict[str, Any]] = field(default_factory=list)

    def artifact(self, name: str) -> Path:
        safe = name.replace("\\", "/").split("/")[-1]
        path = self.out_dir / safe
        self.artifacts.append(str(path))
        return path

    def event(self, message: str, **fields: Any) -> None:
        entry = {"time": iso_now(), "message": message}
        entry.update(fields)
        self.events.append(entry)


def cap_text(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated {len(text) - limit} chars]"


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class MinimalWebSocket:
    """最小 WebSocket 客户端，仅用于本机 raw CDP JSON 消息。"""

    def __init__(self, ws_url: str, timeout: float = 10.0, allow_remote: bool = False) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self.allow_remote = allow_remote
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        parsed = urllib.parse.urlparse(self.ws_url)
        if parsed.scheme != "ws":
            raise VerifyError("raw CDP transport only supports ws:// endpoints")
        if not self.allow_remote and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise VerifyError("raw CDP transport defaults to localhost endpoints only")
        host = parsed.hostname
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((host, port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = self._recv_http_response(sock)
        if " 101 " not in response.split("\r\n", 1)[0]:
            raise VerifyError(f"websocket handshake failed: {response.splitlines()[0] if response else 'empty response'}")
        accept = None
        for line in response.split("\r\n")[1:]:
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        if accept != expected:
            raise VerifyError("websocket accept header mismatch")
        self.sock = sock

    def _recv_http_response(self, sock: socket.socket) -> str:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 65536:
                raise VerifyError("websocket handshake response too large")
        return data.decode("iso-8859-1", errors="replace")

    def send_text(self, text: str) -> None:
        if self.sock is None:
            raise VerifyError("websocket is not connected")
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        if len(payload) < 126:
            header.append(0x80 | len(payload))
        elif len(payload) <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(payload)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(payload)))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_text(self) -> str:
        if self.sock is None:
            raise VerifyError("websocket is not connected")
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 0x1:
                return payload.decode("utf-8", errors="replace")
            if opcode == 0x8:
                raise VerifyError("websocket closed by peer")
            if opcode == 0x9:
                self._send_control(0xA, payload)
                continue

    def _recv_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise VerifyError("websocket is not connected")
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise VerifyError("websocket connection closed")
            data += chunk
        return data

    def _recv_frame(self) -> tuple[int, bytes]:
        first, second = self._recv_exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    def _send_control(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            return
        header = bytearray([0x80 | opcode, 0x80 | len(payload)])
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self._send_control(0x8, b"")
            finally:
                self.sock.close()
                self.sock = None


class CDPClient:
    """CDP JSON-RPC 客户端。"""

    def __init__(self, ws_url: str, allow_remote: bool = False) -> None:
        self.ws = MinimalWebSocket(ws_url, allow_remote=allow_remote)
        self.next_id = 1

    def __enter__(self) -> "CDPClient":
        self.ws.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
        msg_id = self.next_id
        self.next_id += 1
        self.ws.sock.settimeout(timeout) if self.ws.sock is not None else None
        self.ws.send_text(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = self.ws.recv_text()
            payload = json.loads(raw)
            if payload.get("id") != msg_id:
                continue
            if "error" in payload:
                raise VerifyError(f"CDP {method} failed: {payload['error']}")
            return payload.get("result", {})


def get_version(cdp: str) -> dict[str, Any]:
    return url_json(f"{cdp}/json/version")


def get_targets(cdp: str) -> list[TargetInfo]:
    raw_targets = url_json(f"{cdp}/json/list")
    targets: list[TargetInfo] = []
    for item in raw_targets:
        ws_url = item.get("webSocketDebuggerUrl")
        if not ws_url:
            continue
        targets.append(
            TargetInfo(
                id=str(item.get("id", "")),
                type=str(item.get("type", "")),
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                web_socket_debugger_url=str(ws_url),
            )
        )
    return targets


def select_target(targets: list[TargetInfo], workflow: dict[str, Any] | None = None) -> TargetInfo:
    workflow = workflow or {}
    target_type = workflow.get("targetType", "page")
    candidates = [target for target in targets if target.type == target_type]
    url_contains = workflow.get("targetUrlContains")
    title_contains = workflow.get("targetTitleContains")
    if url_contains:
        candidates = [target for target in candidates if url_contains in target.url]
    if title_contains:
        candidates = [target for target in candidates if title_contains in target.title]
    if "targetIndex" in workflow:
        index = int(workflow["targetIndex"])
        if index < 0 or index >= len(candidates):
            raise VerifyError(f"targetIndex out of range: {index}; candidates={len(candidates)}")
        return candidates[index]
    if len(candidates) == 1:
        return candidates[0]
    details = [{"id": t.id, "type": t.type, "title": t.title, "url": t.url} for t in candidates]
    raise VerifyError(f"target selection is ambiguous; specify targetUrlContains, targetTitleContains, or targetIndex: {json.dumps(details, ensure_ascii=False)}")


SNAPSHOT_SCRIPT = r"""
(() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const elements = Array.from(document.querySelectorAll('button,a,input,textarea,select,[role],td,th,li,div,span'))
    .filter(visible)
    .slice(0, 500)
    .map((el, index) => {
      const rect = el.getBoundingClientRect();
      const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ');
      return {
        index,
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || '',
        text,
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
        width: rect.width,
        height: rect.height
      };
    })
    .filter((item) => item.text || ['input','textarea','select','button','a'].includes(item.tag));
  return {
    title: document.title,
    url: location.href,
    text: document.body ? document.body.innerText : '',
    elements
  };
})()
"""


def evaluate(client: CDPClient, expression: str) -> Any:
    result = client.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
    remote = result.get("result", {})
    if "value" in remote:
        return remote["value"]
    if "description" in remote:
        return remote["description"]
    return None


def page_snapshot(client: CDPClient) -> dict[str, Any]:
    value = evaluate(client, SNAPSHOT_SCRIPT)
    if not isinstance(value, dict):
        raise VerifyError("snapshot did not return an object")
    return value


def wait_text(client: CDPClient, text: str, timeout_ms: int) -> dict[str, Any]:
    deadline = time.time() + timeout_ms / 1000.0
    last_text = ""
    while time.time() < deadline:
        snapshot = page_snapshot(client)
        last_text = str(snapshot.get("text", ""))
        if text in last_text:
            return snapshot
        time.sleep(0.5)
    raise VerifyError(f"timed out waiting for text: {text}; last text prefix={last_text[:120]!r}")


def capture_screenshot(client: CDPClient, path: Path) -> None:
    result = client.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}, timeout=20.0)
    data = result.get("data")
    if not data:
        raise VerifyError("CDP screenshot returned no data")
    path.write_bytes(base64.b64decode(data))
    if path.stat().st_size <= 0:
        raise VerifyError(f"screenshot is empty: {path}")


def click_xy(client: CDPClient, x: float, y: float) -> None:
    params = {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}
    client.call("Input.dispatchMouseEvent", params)
    params["type"] = "mouseReleased"
    client.call("Input.dispatchMouseEvent", params)


def find_text_candidate(snapshot: dict[str, Any], text: str, index: int = 0) -> dict[str, Any]:
    elements = snapshot.get("elements") or []
    matches = [item for item in elements if text in str(item.get("text", ""))]
    if not matches:
        raise VerifyError(f"text candidate not found: {text}")
    # 优先选择精确文本和面积更小的候选，避免点击包含目标文字的整页容器。
    def rank(item: dict[str, Any]) -> tuple[int, int, float]:
        item_text = str(item.get("text", "")).strip()
        exact = 0 if item_text == text else 1
        length = len(item_text)
        area = float(item.get("width", 0)) * float(item.get("height", 0))
        return exact, length, area

    matches = sorted(matches, key=rank)
    if index < 0 or index >= len(matches):
        raise VerifyError(f"text candidate index out of range: {index}; matches={len(matches)}")
    return matches[index]


def extract_table(snapshot: dict[str, Any]) -> list[str]:
    elements = snapshot.get("elements") or []
    rows: list[str] = []
    for item in elements:
        text = str(item.get("text", "")).strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def detect_playwright(cdp: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp, timeout=5000)
            page_count = sum(len(context.pages) for context in browser.contexts)
            browser.close()
            return {"backend": "playwright-cdp", "status": "available", "pageCount": page_count}
    except Exception as exc:  # Playwright 失败本身要进入 fallback 证据。
        return {"backend": "playwright-cdp", "status": "failed", "error": str(exc)}


def normalize_step(step: dict[str, Any]) -> tuple[str, str, Any]:
    step_id = str(step.get("id") or f"step-{now_ms()}")
    for action in ("snapshot", "screenshot", "clickText", "clickXY", "fillText", "pressKey", "extractText", "extractTable", "waitText", "waitUrlContains", "evaluate"):
        if action in step:
            return step_id, action, step[action]
    raise VerifyError(f"step has no supported action: {step_id}")


def run_step(client: CDPClient, ctx: RunContext, step: dict[str, Any]) -> StepResult:
    step_id, action, payload = normalize_step(step)
    started = iso_now()
    artifacts: list[str] = []
    data: dict[str, Any] = {}
    try:
        if action == "snapshot":
            snapshot = page_snapshot(client)
            path = ctx.artifact(f"{step_id}.snapshot.json")
            write_json(path, snapshot)
            artifacts.append(str(path))
            data = {"title": snapshot.get("title"), "url": snapshot.get("url"), "textLength": len(str(snapshot.get("text", "")))}
        elif action == "screenshot":
            name = str(payload if isinstance(payload, str) else f"{step_id}.png")
            path = ctx.artifact(name)
            capture_screenshot(client, path)
            artifacts.append(str(path))
            data = {"bytes": path.stat().st_size}
        elif action == "clickText":
            text = payload["text"] if isinstance(payload, dict) else str(payload)
            index = int(payload.get("index", 0)) if isinstance(payload, dict) else 0
            snapshot = page_snapshot(client)
            candidate = find_text_candidate(snapshot, text, index)
            click_xy(client, float(candidate["x"]), float(candidate["y"]))
            data = {"text": text, "candidate": candidate}
        elif action == "clickXY":
            if not isinstance(payload, dict):
                raise VerifyError("clickXY payload must be an object")
            click_xy(client, float(payload["x"]), float(payload["y"]))
            data = {"x": payload["x"], "y": payload["y"]}
        elif action == "fillText":
            if not isinstance(payload, dict):
                raise VerifyError("fillText payload must be an object")
            selector = str(payload["selector"])
            value = str(payload.get("value", ""))
            script = f"""
            (() => {{
              const el = document.querySelector({js_string(selector)});
              if (!el) throw new Error('selector not found: ' + {js_string(selector)});
              el.focus();
              el.value = {js_string(value)};
              el.dispatchEvent(new Event('input', {{ bubbles: true }}));
              el.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()
            """
            evaluate(client, script)
            data = {"selector": selector, "valueLength": len(value)}
        elif action == "pressKey":
            key = str(payload["key"] if isinstance(payload, dict) else payload)
            code = ord(key) if len(key) == 1 else 0
            client.call("Input.dispatchKeyEvent", {"type": "keyDown", "text": key if len(key) == 1 else "", "unmodifiedText": key if len(key) == 1 else "", "key": key, "windowsVirtualKeyCode": code})
            client.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "windowsVirtualKeyCode": code})
            data = {"key": key}
        elif action == "extractText":
            snapshot = page_snapshot(client)
            name = payload.get("name", step_id) if isinstance(payload, dict) else step_id
            data = {"name": name, "text": cap_text(str(snapshot.get("text", "")))}
        elif action == "extractTable":
            snapshot = page_snapshot(client)
            name = payload.get("name", step_id) if isinstance(payload, dict) else step_id
            data = {"name": name, "rows": extract_table(snapshot)}
        elif action == "waitText":
            text = payload["text"] if isinstance(payload, dict) else str(payload)
            timeout_ms = int(payload.get("timeoutMs", 30000)) if isinstance(payload, dict) else 30000
            snapshot = wait_text(client, text, timeout_ms)
            data = {"text": text, "title": snapshot.get("title"), "url": snapshot.get("url")}
        elif action == "waitUrlContains":
            text = payload["text"] if isinstance(payload, dict) else str(payload)
            timeout_ms = int(payload.get("timeoutMs", 30000)) if isinstance(payload, dict) else 30000
            deadline = time.time() + timeout_ms / 1000.0
            current_url = ""
            while time.time() < deadline:
                snapshot = page_snapshot(client)
                current_url = str(snapshot.get("url", ""))
                if text in current_url:
                    break
                time.sleep(0.5)
            else:
                raise VerifyError(f"timed out waiting for URL containing {text}; last={current_url}")
            data = {"urlContains": text, "url": current_url}
        elif action == "evaluate":
            if not isinstance(payload, dict):
                raise VerifyError("evaluate payload must be an object")
            if payload.get("allow") is not True:
                raise VerifyError("evaluate requires allow=true")
            expression = str(payload["expression"])
            value = evaluate(client, expression)
            data = {"value": value}
        else:
            raise VerifyError(f"unsupported action: {action}")
        return StepResult(step_id, action, "passed", started, iso_now(), ctx.backend, artifacts, data)
    except Exception as exc:
        if step.get("continueOnFailure") is True:
            data["continueOnFailure"] = True
            ctx.not_covered.append(f"optional step skipped: {step_id} ({action}) - {exc}")
            return StepResult(step_id, action, "skipped", started, iso_now(), ctx.backend, artifacts, data, str(exc))
        return StepResult(step_id, action, "failed", started, iso_now(), ctx.backend, artifacts, data, str(exc))


def build_report(
    ctx: RunContext,
    version: dict[str, Any],
    targets: list[TargetInfo],
    target: TargetInfo | None,
    steps: list[StepResult],
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": iso_now(),
        "backend": ctx.backend,
        "cdp": ctx.cdp,
        "version": version,
        "targets": [target.__dict__ for target in targets],
        "selectedTarget": target.__dict__ if target else None,
        "backendAttempts": ctx.backend_attempts,
        "steps": [step.__dict__ for step in steps],
        "artifacts": ctx.artifacts,
        "events": ctx.events,
        "notCovered": ctx.not_covered,
        "status": "failed" if any(step.status == "failed" for step in steps) else "passed",
    }


def write_summary(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Electron UI Verification Summary",
        "",
        f"- Status: {report['status']}",
        f"- Backend: {report['backend']}",
        f"- CDP: {report['cdp']}",
    ]
    target = report.get("selectedTarget")
    if target:
        lines.extend([f"- Target title: {target.get('title')}", f"- Target URL: {target.get('url')}"])
    lines.extend(["", "## Steps", ""])
    for step in report.get("steps", []):
        lines.append(f"- {step['status']}: {step['id']} ({step['action']})")
        if step.get("error"):
            lines.append(f"  - Error: {step['error']}")
    if report.get("notCovered"):
        lines.extend(["", "## Not Covered", ""])
        lines.extend(f"- {item}" for item in report["notCovered"])
    write_text(path, "\n".join(lines) + "\n")


def persist_report(ctx: RunContext, report: dict[str, Any]) -> None:
    write_json(ctx.out_dir / "report.json", report)
    write_summary(ctx.out_dir / "summary.md", report)
    events_path = ctx.out_dir / "events.ndjson"
    with events_path.open("w", encoding="utf-8") as handle:
        for event in ctx.events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def probe(cdp: str, out_dir: Path, workflow: dict[str, Any] | None = None) -> int:
    cdp = normalize_cdp_endpoint(cdp)
    ensure_dir(out_dir)
    ctx = RunContext(cdp=cdp, out_dir=out_dir)
    ctx.backend_attempts.append(detect_playwright(cdp))
    ctx.backend_attempts.append({"backend": "raw-cdp", "status": "selected"})
    version = get_version(cdp)
    targets = get_targets(cdp)
    selected: TargetInfo | None = None
    steps: list[StepResult] = []
    try:
        selected = select_target(targets, workflow)
        ctx.event("target selected", target=selected.__dict__)
    except VerifyError as exc:
        ctx.event("target selection failed", error=str(exc))
    report = build_report(ctx, version, targets, selected, steps)
    if selected is None:
        report["status"] = "failed"
        report["notCovered"] = ["target selection failed or ambiguous"]
    persist_report(ctx, report)
    print(json.dumps({"ok": selected is not None, "report": str(out_dir / "report.json")}, ensure_ascii=False))
    return 0 if selected is not None else 2


def run_workflow(workflow_path: Path, out_dir: Path) -> int:
    workflow = read_json(workflow_path)
    app = workflow.get("app") or {}
    cdp = normalize_cdp_endpoint(str(app.get("cdp") or workflow.get("cdp") or ""))
    ensure_dir(out_dir)
    ctx = RunContext(cdp=cdp, out_dir=out_dir)
    ctx.backend_attempts.append(detect_playwright(cdp))
    ctx.backend_attempts.append({"backend": "raw-cdp", "status": "selected"})
    version = get_version(cdp)
    targets = get_targets(cdp)
    target = select_target(targets, workflow)
    ctx.event("target selected", target=target.__dict__)
    steps: list[StepResult] = []
    with CDPClient(target.web_socket_debugger_url, allow_remote=bool(workflow.get("allowRemoteCdp"))) as client:
        client.call("Runtime.enable")
        client.call("Page.enable")
        for item in workflow.get("readiness", []):
            if "waitText" in item:
                payload = {"text": item["waitText"], "timeoutMs": item.get("timeoutMs", 30000)}
                steps.append(run_step(client, ctx, {"id": f"readiness-{len(steps)+1}", "waitText": payload}))
                if steps[-1].status == "failed":
                    break
            elif "waitUrlContains" in item:
                payload = {"text": item["waitUrlContains"], "timeoutMs": item.get("timeoutMs", 30000)}
                steps.append(run_step(client, ctx, {"id": f"readiness-{len(steps)+1}", "waitUrlContains": payload}))
                if steps[-1].status == "failed":
                    break
        if not any(step.status == "failed" for step in steps):
            for step in workflow.get("steps", []):
                result = run_step(client, ctx, step)
                steps.append(result)
                if result.status == "failed" and step.get("continueOnFailure") is not True:
                    break
    report = build_report(ctx, version, targets, target, steps)
    persist_report(ctx, report)
    print(json.dumps({"ok": report["status"] == "passed", "report": str(out_dir / "report.json")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 2


def one_shot(cdp: str, out_dir: Path, action: str, name: str | None = None) -> int:
    workflow: dict[str, Any] = {"app": {"cdp": cdp}, "steps": []}
    if action == "snapshot":
        workflow["steps"].append({"id": "snapshot", "snapshot": True})
    elif action == "screenshot":
        workflow["steps"].append({"id": "screenshot", "screenshot": name or "screenshot.png"})
    else:
        raise VerifyError(f"unsupported one-shot action: {action}")
    temp = out_dir / "_workflow.oneshot.json"
    ensure_dir(out_dir)
    write_json(temp, workflow)
    return run_workflow(temp, out_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify Electron UI through CDP and evidence reports.")
    sub = parser.add_subparsers(dest="command", required=True)

    probe_cmd = sub.add_parser("probe", help="Probe a CDP endpoint and select a target.")
    probe_cmd.add_argument("--cdp", required=True)
    probe_cmd.add_argument("--out", required=True)
    probe_cmd.add_argument("--workflow")

    run_cmd = sub.add_parser("run", help="Run a workflow JSON.")
    run_cmd.add_argument("--workflow", required=True)
    run_cmd.add_argument("--out", required=True)

    snap_cmd = sub.add_parser("snapshot", help="Capture a DOM text snapshot.")
    snap_cmd.add_argument("--cdp", required=True)
    snap_cmd.add_argument("--out", required=True)

    shot_cmd = sub.add_parser("screenshot", help="Capture a screenshot.")
    shot_cmd.add_argument("--cdp", required=True)
    shot_cmd.add_argument("--out", required=True)
    shot_cmd.add_argument("--name", default="screenshot.png")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "probe":
            out_dir = require_absolute(args.out, "--out")
            workflow = read_json(require_absolute(args.workflow, "--workflow")) if args.workflow else None
            return probe(args.cdp, out_dir, workflow)
        if args.command == "run":
            workflow_path = require_absolute(args.workflow, "--workflow")
            out_dir = require_absolute(args.out, "--out")
            return run_workflow(workflow_path, out_dir)
        if args.command == "snapshot":
            return one_shot(args.cdp, require_absolute(args.out, "--out"), "snapshot")
        if args.command == "screenshot":
            return one_shot(args.cdp, require_absolute(args.out, "--out"), "screenshot", args.name)
        raise VerifyError(f"unknown command: {args.command}")
    except VerifyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
