"""受限 loopback HTTP 控制面。"""

from __future__ import annotations

import hmac
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .errors import NotFoundError, PMError, RequestError
from .manager import ProcessManager
from .protocol import failure, success


MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        manager: ProcessManager,
        token: str,
        max_request_bytes: int,
    ) -> None:
        super().__init__(address, ControlHandler)
        self.manager = manager
        self.token = token
        self.max_request_bytes = max_request_bytes


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "ProcessManager"

    @property
    def control(self) -> ControlServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _operation(self) -> str:
        return urllib.parse.urlsplit(self.path).path.strip("/").replace("/", ".") or "unknown"

    def _authorized(self) -> bool:
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            return False
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.control.token}"
        return hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8"))

    def _send(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_RESPONSE_BYTES:
            value = failure(
                self._operation(),
                RequestError("response 超过控制面上限"),
                instance_id=self.control.manager.instance_id,
            )
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _deny_unless_authorized(self) -> bool:
        if self._authorized():
            return False
        self._send(
            401,
            {
                "ok": False,
                "operation": self._operation(),
                "error": {"code": "unauthorized", "message": "unauthorized", "retryable": False},
                "meta": {},
            },
        )
        return True

    def _read_body(self) -> dict[str, Any]:
        transfer_encoding = self.headers.get("Transfer-Encoding")
        if transfer_encoding:
            raise RequestError("控制面不接受 Transfer-Encoding")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise RequestError("POST 请求必须提供 Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise RequestError("Content-Length 无效") from exc
        if length < 0 or length > self.control.max_request_bytes:
            raise RequestError("请求体超过 maxRequestBytes")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError("请求体必须是 UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise RequestError("请求体必须是 JSON object")
        return value

    def _query(self, allowed: set[str]) -> dict[str, list[str]]:
        value = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
        unknown = sorted(set(value) - allowed)
        duplicates = sorted(key for key, items in value.items() if len(items) != 1)
        if unknown:
            raise RequestError("query 包含未知字段: " + ", ".join(unknown))
        if duplicates:
            raise RequestError("query 字段不能重复: " + ", ".join(duplicates))
        return value

    @staticmethod
    def _closed_body(
        value: dict[str, Any],
        *,
        allowed: set[str],
        required: set[str] = frozenset(),
    ) -> dict[str, Any]:
        unknown = sorted(set(value) - allowed)
        missing = sorted(required - set(value))
        if unknown:
            raise RequestError("请求体包含未知字段: " + ", ".join(unknown))
        if missing:
            raise RequestError("请求体缺少字段: " + ", ".join(missing))
        return value

    @staticmethod
    def _single(query: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
        return query.get(name, [default])[0]

    @staticmethod
    def _selector(values: dict[str, Any]) -> tuple[str | None, str | None]:
        service = values.get("service")
        process_key = values.get("processKey")
        if service is not None and (not isinstance(service, str) or not service):
            raise RequestError("service 必须是非空字符串")
        if process_key is not None and (not isinstance(process_key, str) or not process_key):
            raise RequestError("processKey 必须是非空字符串")
        if (service is None) == (process_key is None):
            raise RequestError("service 与 processKey 必须且只能提供一个")
        return service, process_key

    @staticmethod
    def _number(value: Any, label: str, minimum: float, maximum: float) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RequestError(f"{label} 必须是数字")
        result = float(value)
        if not minimum <= result <= maximum:
            raise RequestError(f"{label} 必须在 {minimum}-{maximum} 范围内")
        return result

    @staticmethod
    def _integer(value: Any, label: str, minimum: int, maximum: int) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise RequestError(f"{label} 必须是 {minimum}-{maximum} 范围内整数")
        return value

    @staticmethod
    def _boolean(value: Any, label: str) -> bool:
        if not isinstance(value, bool):
            raise RequestError(f"{label} 必须是 boolean")
        return value

    def _handle(self, operation: str, action: Callable[[], Any]) -> None:
        try:
            data = action()
            self._send(200, success(operation, data, instance_id=self.control.manager.instance_id))
        except PMError as exc:
            self._send(
                exc.http_status,
                failure(operation, exc, instance_id=self.control.manager.instance_id),
            )
        except Exception as exc:  # noqa: BLE001
            self._send(500, failure(operation, exc, instance_id=self.control.manager.instance_id))

    def do_GET(self) -> None:
        if self._deny_unless_authorized():
            return
        path = urllib.parse.urlsplit(self.path).path
        if path == "/health":
            def health() -> Any:
                self._query(set())
                return self.control.manager.health()

            self._handle("health", health)
        elif path == "/doctor":
            def doctor() -> Any:
                self._query(set())
                return self.control.manager.doctor()

            self._handle("doctor", doctor)
        elif path == "/processes":
            def list_processes() -> Any:
                query = self._query({"history"})
                history = self._single(query, "history", "false")
                if history not in {"true", "false"}:
                    raise RequestError("history 只允许 true 或 false")
                return self.control.manager.list_processes(include_history=history == "true")

            self._handle("processes.list", list_processes)
        elif path == "/processes/status":
            def status() -> Any:
                query = self._query({"service", "processKey"})
                service, process_key = self._selector(
                    {"service": self._single(query, "service"), "processKey": self._single(query, "processKey")}
                )
                return self.control.manager.status(service=service, process_key=process_key)

            self._handle("processes.status", status)
        elif path == "/processes/logs":
            def logs() -> Any:
                query = self._query({"service", "processKey", "stream", "tail", "maxBytes"})
                service, process_key = self._selector(
                    {"service": self._single(query, "service"), "processKey": self._single(query, "processKey")}
                )
                try:
                    tail = int(self._single(query, "tail", "80") or "")
                    max_bytes = int(self._single(query, "maxBytes", "262144") or "")
                except ValueError as exc:
                    raise RequestError("tail/maxBytes 必须是整数") from exc
                return self.control.manager.logs(
                    service=service,
                    process_key=process_key,
                    stream=self._single(query, "stream", "stdout") or "stdout",
                    tail_lines=tail,
                    max_bytes=max_bytes,
                )

            self._handle("processes.logs", logs)
        else:
            self._send(
                404,
                failure(
                    "unknown",
                    NotFoundError("control endpoint 不存在"),
                    instance_id=self.control.manager.instance_id,
                ),
            )

    def do_POST(self) -> None:
        if self._deny_unless_authorized():
            return
        path = urllib.parse.urlsplit(self.path).path
        operation = self._operation()

        def action() -> Any:
            body = self._read_body()
            if path == "/processes/start":
                self._closed_body(body, allowed={"servicePath"}, required={"servicePath"})
                service_path = body.get("servicePath")
                if not isinstance(service_path, str) or not service_path:
                    raise RequestError("start 缺少 servicePath")
                return self.control.manager.start(Path(service_path))
            if path == "/processes/stop":
                self._closed_body(body, allowed={"service", "processKey"})
                service, process_key = self._selector(body)
                return self.control.manager.stop(service=service, process_key=process_key)
            if path == "/processes/ready":
                self._closed_body(body, allowed={"service", "processKey", "timeoutSeconds"})
                service, process_key = self._selector(body)
                timeout = self._number(body.get("timeoutSeconds"), "timeoutSeconds", 0.1, 600)
                return self.control.manager.ready(
                    service=service,
                    process_key=process_key,
                    timeout_seconds=timeout,
                )
            if path == "/processes/restart":
                self._closed_body(body, allowed={"servicePath", "timeoutSeconds"}, required={"servicePath"})
                service_path = body.get("servicePath")
                if not isinstance(service_path, str) or not service_path:
                    raise RequestError("restart 缺少 servicePath")
                timeout = self._number(body.get("timeoutSeconds"), "timeoutSeconds", 0.1, 600)
                return self.control.manager.restart(Path(service_path), timeout_seconds=timeout)
            if path == "/processes/prune":
                self._closed_body(body, allowed={"dryRun", "maxInactive", "keepRuns"}, required={"dryRun"})
                dry_run = self._boolean(body.get("dryRun"), "dryRun")
                max_inactive = self._integer(body.get("maxInactive"), "maxInactive", 0, 10000)
                keep_runs = self._boolean(body.get("keepRuns", False), "keepRuns")
                return self.control.manager.prune(
                    max_inactive=max_inactive,
                    dry_run=dry_run,
                    keep_runs=keep_runs,
                )
            if path == "/shutdown":
                self._closed_body(body, allowed=set())
                result = self.control.manager.shutdown()
                threading.Thread(target=self.control.shutdown, daemon=True).start()
                return result
            raise NotFoundError("control endpoint 不存在")

        self._handle(operation, action)
