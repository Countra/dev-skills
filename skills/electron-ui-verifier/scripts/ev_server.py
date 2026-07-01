#!/usr/bin/env python3
"""Electron UI verifier server。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ev_common import EVConfig, EVError, config_from_data, iso_now as common_iso_now, load_config, read_token, write_json as write_runtime_json
from ev_knowledge_extract import extract_knowledge
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


SCHEMA_VERSION = 1
SUPPORTED_ACTIONS = (
    "snapshot",
    "screenshot",
    "clickText",
    "clickXY",
    "fillText",
    "pressKey",
    "extractText",
    "extractTable",
    "waitText",
    "waitUrlContains",
    "evaluate",
    "collectConsole",
    "collectExceptions",
    "collectNetwork",
    "domSnapshot",
    "accessibilitySnapshot",
)


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
    diagnostics: dict[str, Any] = field(default_factory=lambda: {"enabledDomains": [], "eventCounts": {}})
    named_results: dict[str, Any] = field(default_factory=dict)
    step_event_indexes: dict[str, int] = field(default_factory=dict)

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


def json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def write_json_limited(path: Path, data: Any, max_bytes: int | None = None, on_too_large: str = "artifact") -> dict[str, Any]:
    text = json_text(data)
    original_bytes = len(text.encode("utf-8"))
    if max_bytes and original_bytes > max_bytes:
        if on_too_large == "fail":
            raise VerifyError(f"artifact is too large: {original_bytes} bytes > {max_bytes} bytes")
        preview = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        data = {"truncated": True, "originalBytes": original_bytes, "preview": preview}
    write_json(path, data)
    return {"bytes": path.stat().st_size, "truncated": bool(max_bytes and original_bytes > max_bytes), "originalBytes": original_bytes}


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def set_named_result(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise VerifyError("saveAs must not be empty")
    cursor = target
    for part in parts[:-1]:
        current = cursor.get(part)
        if current is None:
            current = {}
            cursor[part] = current
        if not isinstance(current, dict):
            raise VerifyError(f"saveAs path conflicts with non-object value: {dotted_path}")
        cursor = current
    cursor[parts[-1]] = value


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
        self.events: list[dict[str, Any]] = []

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
                self._record_event(payload)
                continue
            if "error" in payload:
                raise VerifyError(f"CDP {method} failed: {payload['error']}")
            return payload.get("result", {})

    def _record_event(self, payload: dict[str, Any]) -> None:
        if "method" not in payload:
            return
        self.events.append({"receivedAt": iso_now(), **payload})

    def drain_events(self, duration_ms: int = 100, max_messages: int = 100) -> int:
        if self.ws.sock is None:
            return 0
        original_timeout = self.ws.sock.gettimeout()
        deadline = time.time() + max(duration_ms, 0) / 1000.0
        count = 0
        try:
            while count < max_messages and time.time() < deadline:
                remaining = max(deadline - time.time(), 0.001)
                self.ws.sock.settimeout(remaining)
                try:
                    payload = json.loads(self.ws.recv_text())
                except socket.timeout:
                    break
                self._record_event(payload)
                count += 1
        finally:
            self.ws.sock.settimeout(original_timeout)
        return count

    def event_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            method = str(event.get("method", ""))
            counts[method] = counts.get(method, 0) + 1
        return counts

    def events_by_method(self, methods: set[str]) -> list[dict[str, Any]]:
        return [event for event in self.events if event.get("method") in methods]


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


def evaluate(
    client: CDPClient,
    expression: str,
    return_by_value: bool = True,
    await_promise: bool = True,
    timeout: float = 10.0,
) -> Any:
    result = client.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": return_by_value, "awaitPromise": await_promise},
        timeout=timeout,
    )
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        text = details.get("text") or details.get("exception", {}).get("description") or "unknown evaluate exception"
        raise VerifyError(f"Runtime.evaluate exception: {text}")
    remote = result.get("result", {})
    if "value" in remote:
        return remote["value"]
    if "unserializableValue" in remote:
        return remote["unserializableValue"]
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


def remote_object_preview(remote: dict[str, Any], max_chars: int = 2000) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": remote.get("type"),
        "subtype": remote.get("subtype"),
    }
    if "value" in remote:
        item["value"] = cap_text(str(remote["value"]), max_chars)
    if "unserializableValue" in remote:
        item["unserializableValue"] = str(remote["unserializableValue"])
    if "description" in remote:
        item["description"] = cap_text(str(remote["description"]), max_chars)
    return {key: value for key, value in item.items() if value is not None}


def console_event_record(event: dict[str, Any]) -> dict[str, Any]:
    params = event.get("params") or {}
    args = [remote_object_preview(arg) for arg in params.get("args", []) if isinstance(arg, dict)]
    text_parts = []
    for arg in args:
        if "value" in arg:
            text_parts.append(str(arg["value"]))
        elif "description" in arg:
            text_parts.append(str(arg["description"]))
    return {
        "receivedAt": event.get("receivedAt"),
        "timestamp": params.get("timestamp"),
        "type": params.get("type"),
        "level": params.get("type"),
        "text": cap_text(" ".join(text_parts), 2000),
        "args": args,
        "stackTrace": params.get("stackTrace"),
        "source": "runtime",
    }


def exception_event_record(event: dict[str, Any]) -> dict[str, Any]:
    params = event.get("params") or {}
    details = params.get("exceptionDetails") or {}
    exception = details.get("exception") if isinstance(details.get("exception"), dict) else {}
    return {
        "receivedAt": event.get("receivedAt"),
        "timestamp": params.get("timestamp"),
        "text": details.get("text"),
        "url": details.get("url"),
        "lineNumber": details.get("lineNumber"),
        "columnNumber": details.get("columnNumber"),
        "exception": remote_object_preview(exception) if exception else None,
        "stackTrace": details.get("stackTrace"),
    }


def network_entries(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        method = event.get("method")
        params = event.get("params") or {}
        request_id = str(params.get("requestId", ""))
        if not request_id:
            continue
        if request_id not in entries:
            entries[request_id] = {"requestId": request_id}
            order.append(request_id)
        entry = entries[request_id]
        if method == "Network.requestWillBeSent":
            request = params.get("request") or {}
            entry.update(
                {
                    "url": request.get("url"),
                    "method": request.get("method"),
                    "resourceType": params.get("type"),
                    "startedAt": params.get("timestamp"),
                    "wallTime": params.get("wallTime"),
                }
            )
        elif method == "Network.responseReceived":
            response = params.get("response") or {}
            entry.update(
                {
                    "url": entry.get("url") or response.get("url"),
                    "resourceType": entry.get("resourceType") or params.get("type"),
                    "status": response.get("status"),
                    "statusText": response.get("statusText"),
                    "mimeType": response.get("mimeType"),
                    "fromDiskCache": response.get("fromDiskCache"),
                    "fromServiceWorker": response.get("fromServiceWorker"),
                }
            )
        elif method == "Network.loadingFailed":
            entry.update(
                {
                    "failed": True,
                    "failureText": params.get("errorText"),
                    "canceled": params.get("canceled"),
                    "resourceType": entry.get("resourceType") or params.get("type"),
                    "finishedAt": params.get("timestamp"),
                }
            )
        elif method == "Network.loadingFinished":
            entry.update({"finishedAt": params.get("timestamp"), "encodedDataLength": params.get("encodedDataLength")})
    result = []
    for request_id in order:
        entry = entries[request_id]
        entry["failed"] = bool(entry.get("failed"))
        result.append(entry)
    return result


def status_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        status = entry.get("status")
        key = str(status if status is not None else ("failed" if entry.get("failed") else "pending"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def events_since(client: CDPClient, ctx: RunContext, methods: set[str], options: dict[str, Any]) -> list[dict[str, Any]]:
    since_step = options.get("sinceStep")
    start = ctx.step_event_indexes.get(str(since_step), 0) if since_step else 0
    return [event for event in client.events[start:] if event.get("method") in methods]


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
    for action in SUPPORTED_ACTIONS:
        if action in step:
            return step_id, action, step[action]
    raise VerifyError(f"step has no supported action: {step_id}")


def workflow_actions(workflow: dict[str, Any]) -> set[str]:
    actions: set[str] = set()
    for section in ("readiness", "steps"):
        for step in workflow.get(section, []):
            if isinstance(step, dict):
                for action in SUPPORTED_ACTIONS:
                    if action in step:
                        actions.add(action)
    return actions


def normalize_object_payload(payload: Any, action: str) -> dict[str, Any]:
    if payload is True or payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise VerifyError(f"{action} payload must be an object")


def timeout_seconds(options: dict[str, Any], default_ms: int = 10000) -> float:
    return int(options.get("timeoutMs", default_ms)) / 1000.0


def inline_or_artifact(ctx: RunContext, step_id: str, suffix: str, value: Any, payload: dict[str, Any]) -> dict[str, Any]:
    max_inline_chars = int(payload.get("maxInlineChars", 2000))
    on_too_large = str(payload.get("onTooLarge", "artifact"))
    text = json.dumps(value, ensure_ascii=False)
    result: dict[str, Any] = {"valueType": type(value).__name__, "truncated": False}
    if len(text) <= max_inline_chars and on_too_large != "artifact":
        result["inlineValue"] = value
        return result
    if len(text) <= max_inline_chars and "artifact" not in payload:
        result["inlineValue"] = value
        return result
    if len(text) > max_inline_chars and on_too_large == "fail":
        raise VerifyError(f"evaluate result is too large: {len(text)} chars > {max_inline_chars} chars")
    if len(text) > max_inline_chars and on_too_large == "truncate":
        result.update({"valuePreview": cap_text(text, max_inline_chars), "truncated": True, "chars": len(text)})
        return result
    artifact_name = str(payload.get("artifact") or f"{step_id}.{suffix}.json")
    path = ctx.artifact(artifact_name)
    write_json(path, value)
    result.update(
        {
            "valuePreview": cap_text(text, max_inline_chars),
            "truncated": len(text) > max_inline_chars,
            "artifact": str(path),
            "chars": len(text),
            "bytes": path.stat().st_size,
        }
    )
    return result


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
        elif action == "collectConsole":
            options = normalize_object_payload(payload, action)
            client.drain_events(int(options.get("drainMs", 100)), int(options.get("maxDrainMessages", 200)))
            levels = set(str(item) for item in options.get("levels", []))
            rows = [console_event_record(event) for event in events_since(client, ctx, {"Runtime.consoleAPICalled"}, options)]
            if levels:
                rows = [row for row in rows if str(row.get("level")) in levels]
            max_events = int(options.get("maxEvents", 200))
            truncated = len(rows) > max_events
            rows = rows[-max_events:]
            path = ctx.artifact(f"{step_id}.console.ndjson")
            write_ndjson(path, rows)
            artifacts.append(str(path))
            data = {
                "name": options.get("name", step_id),
                "count": len(rows),
                "levels": sorted(levels) if levels else "all",
                "truncated": truncated,
                "artifact": str(path),
                "sample": rows[: min(len(rows), 20)],
            }
        elif action == "collectExceptions":
            options = normalize_object_payload(payload, action)
            client.drain_events(int(options.get("drainMs", 100)), int(options.get("maxDrainMessages", 200)))
            rows = [exception_event_record(event) for event in events_since(client, ctx, {"Runtime.exceptionThrown"}, options)]
            max_events = int(options.get("maxEvents", 100))
            truncated = len(rows) > max_events
            rows = rows[-max_events:]
            path = ctx.artifact(f"{step_id}.exceptions.json")
            write_json(path, rows)
            artifacts.append(str(path))
            data = {
                "name": options.get("name", step_id),
                "count": len(rows),
                "hasException": bool(rows),
                "truncated": truncated,
                "artifact": str(path),
                "sample": rows[: min(len(rows), 20)],
            }
            if rows and options.get("failOnException") is True:
                raise VerifyError(f"page exceptions collected: {len(rows)}")
        elif action == "collectNetwork":
            options = normalize_object_payload(payload, action)
            client.drain_events(int(options.get("drainMs", 200)), int(options.get("maxDrainMessages", 500)))
            methods = {"Network.requestWillBeSent", "Network.responseReceived", "Network.loadingFailed", "Network.loadingFinished"}
            rows = network_entries(events_since(client, ctx, methods, options))
            url_contains = options.get("urlContains")
            if url_contains:
                rows = [row for row in rows if str(url_contains) in str(row.get("url", ""))]
            if options.get("includeFailedOnly") is True:
                rows = [row for row in rows if row.get("failed")]
            max_events = int(options.get("maxEvents", 300))
            truncated = len(rows) > max_events
            rows = rows[-max_events:]
            path = ctx.artifact(f"{step_id}.network.json")
            write_json(path, rows)
            artifacts.append(str(path))
            failed_count = sum(1 for row in rows if row.get("failed"))
            data = {
                "name": options.get("name", step_id),
                "requestCount": len(rows),
                "failedCount": failed_count,
                "statusCounts": status_counts(rows),
                "truncated": truncated,
                "artifact": str(path),
                "sample": rows[: min(len(rows), 20)],
            }
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
        elif action == "domSnapshot":
            options = normalize_object_payload(payload, action)
            params = {
                "computedStyles": options.get("computedStyles", []),
                "includeDOMRects": bool(options.get("includeDOMRects", False)),
                "includePaintOrder": bool(options.get("includePaintOrder", False)),
            }
            snapshot = client.call("DOMSnapshot.captureSnapshot", params, timeout=timeout_seconds(options, 20000))
            path = ctx.artifact(f"{step_id}.dom-snapshot.json")
            meta = write_json_limited(path, snapshot, int(options.get("maxBytes", 0)) or None, str(options.get("onTooLarge", "artifact")))
            artifacts.append(str(path))
            documents = snapshot.get("documents", []) if isinstance(snapshot, dict) else []
            node_count = 0
            layout_count = 0
            for document in documents:
                if isinstance(document, dict):
                    nodes = document.get("nodes") or {}
                    layout = document.get("layout") or {}
                    node_names = nodes.get("nodeName") if isinstance(nodes, dict) else None
                    layout_nodes = layout.get("nodeIndex") if isinstance(layout, dict) else None
                    node_count += len(node_names) if isinstance(node_names, list) else 0
                    layout_count += len(layout_nodes) if isinstance(layout_nodes, list) else 0
            data = {
                "name": options.get("name", step_id),
                "documentCount": len(documents),
                "nodeCount": node_count,
                "layoutCount": layout_count,
                "artifact": str(path),
                **meta,
            }
        elif action == "accessibilitySnapshot":
            options = normalize_object_payload(payload, action)
            result = client.call("Accessibility.getFullAXTree", {}, timeout=timeout_seconds(options, 20000))
            nodes = result.get("nodes", []) if isinstance(result, dict) else []
            max_nodes = int(options.get("maxNodes", 2000))
            truncated = len(nodes) > max_nodes
            rows = nodes[:max_nodes]
            path = ctx.artifact(f"{step_id}.accessibility.json")
            write_json(path, rows)
            artifacts.append(str(path))
            ignored_count = sum(1 for node in rows if isinstance(node, dict) and node.get("ignored"))
            data = {
                "name": options.get("name", step_id),
                "nodeCount": len(rows),
                "ignoredCount": ignored_count,
                "truncated": truncated,
                "artifact": str(path),
                "sample": rows[: min(len(rows), 20)],
            }
        elif action == "evaluate":
            if not isinstance(payload, dict):
                raise VerifyError("evaluate payload must be an object")
            if payload.get("allow") is not True:
                raise VerifyError("evaluate requires allow=true")
            expression = str(payload["expression"])
            timeout_ms = int(payload.get("timeoutMs", 10000))
            value = evaluate(
                client,
                expression,
                return_by_value=bool(payload.get("returnByValue", True)),
                await_promise=bool(payload.get("awaitPromise", True)),
                timeout=timeout_ms / 1000.0,
            )
            data = inline_or_artifact(ctx, step_id, "evaluate", value, payload)
            data["name"] = payload.get("name", step_id)
            if "inlineValue" in data:
                data["value"] = data["inlineValue"]
            if "saveAs" in payload:
                save_as = str(payload["saveAs"])
                if "artifact" in data and data.get("truncated"):
                    set_named_result(ctx.named_results, save_as, {"artifact": data["artifact"], "truncated": True})
                elif data.get("truncated"):
                    set_named_result(ctx.named_results, save_as, {"valuePreview": data.get("valuePreview"), "truncated": True})
                else:
                    set_named_result(ctx.named_results, save_as, value)
                data["saveAs"] = save_as
        else:
            raise VerifyError(f"unsupported action: {action}")
        ctx.step_event_indexes[step_id] = len(client.events)
        return StepResult(step_id, action, "passed", started, iso_now(), ctx.backend, artifacts, data)
    except Exception as exc:
        ctx.step_event_indexes[step_id] = len(client.events)
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
        "diagnostics": ctx.diagnostics,
        "namedResults": ctx.named_results,
        "events": ctx.events,
        "notCovered": ctx.not_covered,
        "status": "failed" if any(step.status == "failed" for step in steps) else "passed",
    }


def write_summary(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Electron UI 验证摘要",
        "",
        f"- 状态: {report['status']}",
        f"- Backend: {report['backend']}",
        f"- CDP: {report['cdp']}",
    ]
    target = report.get("selectedTarget")
    if target:
        lines.extend([f"- Target title: {target.get('title')}", f"- Target URL: {target.get('url')}"])
    lines.extend(["", "## 步骤", ""])
    for step in report.get("steps", []):
        lines.append(f"- {step['status']}: {step['id']} ({step['action']})")
        if step.get("error"):
            lines.append(f"  - Error: {step['error']}")
    if report.get("notCovered"):
        lines.extend(["", "## 未覆盖", ""])
        lines.extend(f"- {item}" for item in report["notCovered"])
    write_text(path, "\n".join(lines) + "\n")


def persist_report(ctx: RunContext, report: dict[str, Any]) -> None:
    write_json(ctx.out_dir / "report.json", report)
    write_summary(ctx.out_dir / "summary.md", report)
    events_path = ctx.out_dir / "events.ndjson"
    with events_path.open("w", encoding="utf-8") as handle:
        for event in ctx.events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def persist_report_knowledge(config: EVConfig, report_path: Path, app_id: str | None, notes: str | None) -> dict[str, Any]:
    payload = extract_knowledge(report_path, app_id_override=app_id, notes=notes)
    with open_store_from_paths(knowledge_paths_from_config(config)) as store:
        app = store.upsert_app(payload["app"])
        screens = [store.upsert_screen(item) for item in payload.get("screens", [])]
        elements = [store.upsert_element(item) for item in payload.get("elements", [])]
        workflows = [store.upsert_workflow(item) for item in payload.get("workflows", [])]
        evidence = store.add_evidence(payload["evidence"])
        meta = store.meta()
    return {
        "status": "learned",
        "appId": app.get("app_id"),
        "screenCount": len(screens),
        "elementCount": len(elements),
        "workflowCount": len(workflows),
        "evidenceId": evidence.get("evidence_id"),
        "stats": payload.get("stats"),
        "meta": meta,
    }


@dataclass
class VerifierSession:
    """服务端持有的 CDP 会话，进程退出后不会伪装恢复。"""

    session_id: str
    name: str
    cdp: str
    target: TargetInfo
    client: CDPClient
    created_at: str
    last_used_at: str
    enabled_domains: set[str] = field(default_factory=set)
    latest_report: str | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

    def record(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "name": self.name,
            "cdp": self.cdp,
            "targetId": self.target.id,
            "targetTitle": self.target.title,
            "targetUrl": self.target.url,
            "status": "attached",
            "createdAt": self.created_at,
            "lastUsedAt": self.last_used_at,
            "enabledDomains": sorted(self.enabled_domains),
            "latestReport": self.latest_report,
            "eventCounts": self.client.event_counts(),
        }


class VerifierController:
    """HTTP handler 背后的业务控制器。"""

    def __init__(self, config: EVConfig, config_path: Path) -> None:
        self.config = config
        self.config_path = config_path
        self.token = read_token(config)
        self.sessions: dict[str, VerifierSession] = {}
        self.lock = threading.RLock()
        for folder in (config.state_root, config.reports_dir, config.artifacts_dir, config.logs_dir, config.tmp_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.persist_sessions()

    def set_actual_port(self, port: int) -> None:
        if port != self.config.port:
            data = read_json(self.config_path)
            data["port"] = port
            write_runtime_json(self.config_path, data)
            self.config = config_from_data(data)
        write_runtime_json(
            self.config.server_file,
            {
                "host": self.config.host,
                "port": port,
                "pid": os.getpid(),
                "processManagerService": "electron-ui-verifier",
                "startedAt": iso_now(),
            },
        )

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "electron-ui-verifier",
            "pid": os.getpid(),
            "host": self.config.host,
            "port": self.config.port,
            "sessions": len(self.sessions),
        }

    def persist_sessions(self) -> None:
        records = [session.record() for session in self.sessions.values()]
        write_runtime_json(self.config.sessions_file, {"updatedAt": iso_now(), "sessions": records})

    def list_sessions(self) -> dict[str, Any]:
        with self.lock:
            return {"ok": True, "sessions": [session.record() for session in self.sessions.values()]}

    def session_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.get_session(payload)
        with session.lock:
            try:
                session.client.call("Runtime.evaluate", {"expression": "location.href", "returnByValue": True}, timeout=5.0)
                connected = True
                error = None
            except Exception as exc:
                connected = False
                error = str(exc)
        return {"ok": connected, "session": session.record(), "connected": connected, "error": error}

    def get_session(self, payload: dict[str, Any]) -> VerifierSession:
        name = str(payload.get("session") or payload.get("name") or payload.get("sessionId") or "")
        if not name:
            raise VerifyError("session is required")
        with self.lock:
            session = self.sessions.get(name)
            if session is None:
                for item in self.sessions.values():
                    if item.session_id == name:
                        session = item
                        break
            if session is None:
                raise VerifyError(f"session not found: {name}")
            return session

    def probe(self, payload: dict[str, Any]) -> dict[str, Any]:
        cdp = normalize_cdp_endpoint(str(payload.get("cdp") or ""))
        version = get_version(cdp)
        targets = get_targets(cdp)
        selected: dict[str, Any] | None = None
        selection_error: str | None = None
        try:
            selected = select_target(targets, payload).__dict__
        except VerifyError as exc:
            selection_error = str(exc)
        return {
            "ok": True,
            "version": version,
            "targets": [target.__dict__ for target in targets],
            "selectedTarget": selected,
            "selectionError": selection_error,
        }

    def attach(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or payload.get("session") or "").strip()
        if not name:
            raise VerifyError("session name is required")
        reuse = payload.get("reuse", True) is not False
        with self.lock:
            if reuse and name in self.sessions:
                return {"ok": True, "session": self.sessions[name].record(), "reused": True}
        cdp = normalize_cdp_endpoint(str(payload.get("cdp") or ""))
        targets = get_targets(cdp)
        target = select_target(targets, payload)
        client = CDPClient(target.web_socket_debugger_url, allow_remote=bool(payload.get("allowRemoteCdp")))
        client.ws.connect()
        session = VerifierSession(
            session_id=f"ev-{int(time.time())}-{len(self.sessions) + 1}",
            name=name,
            cdp=cdp,
            target=target,
            client=client,
            created_at=iso_now(),
            last_used_at=iso_now(),
        )
        with session.lock:
            self.ensure_domains(session, {"Runtime", "Page"})
        with self.lock:
            old = self.sessions.get(name)
            if old is not None:
                old.client.ws.close()
            self.sessions[name] = session
            self.persist_sessions()
        return {"ok": True, "session": session.record(), "reused": False}

    def detach(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.get_session(payload)
        with self.lock:
            self.sessions.pop(session.name, None)
            session.client.ws.close()
            self.persist_sessions()
        return {"ok": True, "session": session.record()}

    def ensure_domains(self, session: VerifierSession, domains: set[str]) -> None:
        for domain in domains:
            if domain in session.enabled_domains:
                continue
            session.client.call(f"{domain}.enable")
            session.enabled_domains.add(domain)

    def report_dir(self, session: VerifierSession, prefix: str) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        path = self.config.reports_dir / session.name / f"{stamp}-{prefix}"
        ensure_dir(path)
        return path

    def run_steps(
        self,
        session: VerifierSession,
        steps_payload: list[dict[str, Any]],
        prefix: str,
        learn: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with session.lock:
            actions = set()
            for step in steps_payload:
                for action in SUPPORTED_ACTIONS:
                    if action in step:
                        actions.add(action)
            required = {"Runtime", "Page"}
            if "collectNetwork" in actions:
                required.add("Network")
            self.ensure_domains(session, required)
            out_dir = self.report_dir(session, prefix)
            ctx = RunContext(cdp=session.cdp, out_dir=out_dir)
            ctx.backend_attempts.append({"backend": "raw-cdp", "status": "selected"})
            version = get_version(session.cdp)
            targets = get_targets(session.cdp)
            steps: list[StepResult] = []
            for step in steps_payload:
                result = run_step(session.client, ctx, step)
                steps.append(result)
                if result.status == "failed" and step.get("continueOnFailure") is not True:
                    break
            session.client.drain_events(50, 100)
            ctx.diagnostics["enabledDomains"] = sorted(session.enabled_domains)
            ctx.diagnostics["eventCounts"] = session.client.event_counts()
            report = build_report(ctx, version, targets, session.target, steps)
            report["session"] = session.record()
            persist_report(ctx, report)
            session.latest_report = str(out_dir / "report.json")
            if learn:
                try:
                    report["knowledge"] = persist_report_knowledge(
                        self.config,
                        Path(session.latest_report),
                        app_id=learn.get("appId"),
                        notes=learn.get("notes"),
                    )
                except (EVError, VerifyError, OSError, ValueError) as exc:
                    report["knowledge"] = {"status": "failed", "error": str(exc)}
                persist_report(ctx, report)
            session.last_used_at = iso_now()
            self.persist_sessions()
            return {"ok": report["status"] == "passed", "report": session.latest_report, "summary": str(out_dir / "summary.md"), "result": report}

    def run_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.get_session(payload)
        step = payload.get("step") or payload.get("action")
        if not isinstance(step, dict):
            raise VerifyError("action step must be an object")
        learn = normalize_learn_options(payload.get("learn"))
        return self.run_steps(session, [step], "action", learn=learn)

    def run_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.get_session(payload)
        workflow = ensure_workflow(payload.get("workflow"))
        steps_payload: list[dict[str, Any]] = []
        for index, item in enumerate(workflow.get("readiness", []), start=1):
            if not isinstance(item, dict):
                raise VerifyError(f"workflow readiness item must be an object: {index}")
            if "waitText" in item:
                steps_payload.append({"id": f"readiness-{index}", "waitText": {"text": item["waitText"], "timeoutMs": item.get("timeoutMs", 30000)}})
            elif "waitUrlContains" in item:
                steps_payload.append({"id": f"readiness-{index}", "waitUrlContains": {"text": item["waitUrlContains"], "timeoutMs": item.get("timeoutMs", 30000)}})
        for index, item in enumerate(workflow.get("steps", []), start=1):
            if not isinstance(item, dict):
                raise VerifyError(f"workflow step must be an object: {index}")
            steps_payload.append(item)
        learn = normalize_learn_options(payload.get("learn") or workflow.get("learn"))
        return self.run_steps(session, steps_payload, "workflow", learn=learn)

    def latest_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.get_session(payload)
        if not session.latest_report:
            raise VerifyError(f"session has no report yet: {session.name}")
        path = Path(session.latest_report)
        return {"ok": True, "report": str(path), "result": read_json(path)}

    def safe_state_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            raise VerifyError("path must be absolute")
        resolved = path.resolve()
        state_root = self.config.state_root.resolve()
        if state_root not in resolved.parents and resolved != state_root:
            raise VerifyError(f"path must be under verifier state root: {state_root}")
        if not resolved.exists():
            raise VerifyError(f"path does not exist: {resolved}")
        return resolved

    def get_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        path_text = str(payload.get("path") or "")
        path = self.safe_state_path(path_text)
        return {"ok": True, "report": str(path), "result": read_json(path)}

    def get_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        path_text = str(payload.get("path") or "")
        path = self.safe_state_path(path_text)
        if path.is_dir():
            raise VerifyError("artifact path must be a file")
        return {"ok": True, "artifact": str(path), "bytes": path.stat().st_size}


def ensure_workflow(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerifyError("workflow must be an object")
    return value


def normalize_learn_options(value: Any) -> dict[str, Any] | None:
    if value in (None, False):
        return None
    if value is True:
        return {"notes": "learned by verifier server"}
    if not isinstance(value, dict):
        raise VerifyError("learn must be a boolean or object")
    app_id = value.get("appId")
    notes = value.get("notes")
    return {
        "appId": str(app_id).strip() if app_id not in (None, "") else None,
        "notes": str(notes).strip() if notes not in (None, "") else "learned by verifier server",
    }


class VerifierHTTPServer(http.server.ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], controller: VerifierController) -> None:
        self.controller = controller
        super().__init__(server_address, VerifierHandler)


class VerifierHandler(http.server.BaseHTTPRequestHandler):
    server: VerifierHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if self.path.split("?", 1)[0] == "/health":
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {self.server.controller.token}"

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise VerifyError("request body must be a JSON object")
        return value

    def _handle(self, method: str) -> None:
        if not self._authorized():
            self._json(401, {"ok": False, "code": "unauthorized", "error": "invalid bearer token"})
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = dict(urllib.parse.parse_qsl(parsed.query))
        controller = self.server.controller
        try:
            if method == "GET" and path == "/health":
                self._json(200, controller.health())
                return
            if method == "GET" and path == "/sessions":
                self._json(200, controller.list_sessions())
                return
            if method == "GET" and path == "/sessions/status":
                self._json(200, controller.session_status(query))
                return
            if method == "GET" and path == "/reports/latest":
                self._json(200, controller.latest_report(query))
                return
            if method == "GET" and path == "/reports/get":
                self._json(200, controller.get_report(query))
                return
            if method == "GET" and path == "/artifacts/get":
                self._json(200, controller.get_artifact(query))
                return
            if method == "POST" and path == "/targets/probe":
                self._json(200, controller.probe(self._body()))
                return
            if method == "POST" and path == "/sessions/attach":
                self._json(200, controller.attach(self._body()))
                return
            if method == "POST" and path == "/sessions/detach":
                self._json(200, controller.detach(self._body()))
                return
            if method == "POST" and path == "/actions/run":
                result = controller.run_action(self._body())
                self._json(200 if result.get("ok") else 500, result)
                return
            if method == "POST" and path == "/workflows/run":
                result = controller.run_workflow(self._body())
                self._json(200 if result.get("ok") else 500, result)
                return
            self._json(404, {"ok": False, "code": "not_found", "error": f"unknown endpoint: {path}"})
        except VerifyError as exc:
            self._json(400, {"ok": False, "code": "request_failed", "error": str(exc)})
        except Exception as exc:
            self._json(500, {"ok": False, "code": "internal_error", "error": str(exc)})

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 Electron UI verifier HTTP server。")
    parser.add_argument("--config", required=True, help="config.json 的绝对路径")
    return parser


def serve(config_path: Path) -> int:
    config = load_config(config_path)
    controller = VerifierController(config, config_path)
    max_switches = config.port_retry_max_switches if config.port_retry_enabled else 0
    last_error: OSError | None = None
    for offset in range(max_switches + 1):
        port = config.port + offset
        try:
            server = VerifierHTTPServer((config.host, port), controller)
        except OSError as exc:
            last_error = exc
            continue
        controller.set_actual_port(port)
        print(f"EV_READY http://{config.host}:{port}/health", flush=True)
        server.serve_forever()
        return 0
    raise VerifyError(f"failed to bind verifier server port after retries: {last_error}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = require_absolute(args.config, "--config")
        return serve(config_path)
    except (VerifyError, EVError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
