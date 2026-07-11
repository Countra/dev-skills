"""受限 loopback HTTP service 和 route adapter。"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .automation import AutomationWorker
from .config import ServiceConfig
from .errors import VerifierError
from .limits import DEFAULT_LIMITS, RuntimeLimits
from .schema import ensure_json_depth
from .security import redact, secure_mode, token_matches


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class VerifierApplication:
    """HTTP adapter 只做认证、边界检查和 command submission。"""

    def __init__(
        self,
        config: ServiceConfig,
        *,
        limits: RuntimeLimits = DEFAULT_LIMITS,
        worker: AutomationWorker | None = None,
    ) -> None:
        self.config = config
        self.limits = limits
        self.token = config.token()
        self.worker = worker or AutomationWorker(config, limits=limits)
        self.actual_port = config.port

    def start(self) -> None:
        self.config.ensure_directories()
        secure_mode(self.config.state_root, 0o700)
        secure_mode(self.config.token_file, 0o600)
        self.worker.start()

    def stop(self) -> None:
        self.worker.shutdown()

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "electron-ui-verifier",
            "backend": "playwright-cdp",
            "pid": os.getpid(),
            "host": self.config.host,
            "port": self.actual_port,
            "automation": self.worker.stats(),
        }

    def route(self, method: str, path: str, query: dict[str, str], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if method == "GET" and path == "/health":
            return 200, self.health()
        if method == "GET" and path == "/sessions":
            return 200, self.worker.submit("sessions", {}, timeout=30)
        if method == "GET" and path == "/sessions/status":
            result = self.worker.submit("session_status", query, timeout=30)
            return (200 if result.get("ok") else 409), result
        if method == "POST" and path == "/targets/probe":
            return 200, self.worker.submit("probe", body, timeout=30)
        if method == "POST" and path == "/sessions/attach":
            return 200, self.worker.submit("attach", body, timeout=30)
        if method == "POST" and path == "/sessions/detach":
            return 200, self.worker.submit("detach", body, timeout=30)
        if method == "POST" and path == "/runs/prepare":
            return 200, self.worker.submit("run_prepare", body, timeout=60)
        if method == "GET" and path == "/runs/status":
            return 200, self.worker.submit("run_status", query, timeout=30)
        if method == "POST" and path == "/actions/run":
            result = self.worker.submit("run_action", body, timeout=120)
            return (200 if result.get("ok") else 409), result
        if method == "POST" and path == "/workflows/run":
            result = self.worker.submit("run_workflow", body, timeout=300)
            return (200 if result.get("ok") else 409), result
        if method == "POST" and path == "/runs/finalize":
            result = self.worker.submit("run_finalize", body, timeout=60)
            return (200 if result.get("ok") else 409), result
        if method == "GET" and path == "/reports/latest":
            return 200, self.worker.submit("report_latest", query, timeout=30)
        if method == "GET" and path == "/reports/get":
            return 200, self.worker.submit("report_get", query, timeout=30)
        if method == "GET" and path == "/artifacts/get":
            return 200, self.worker.submit("artifact_get", query, timeout=30)
        if method == "GET" and path == "/pending/preview":
            return 200, self.worker.submit("pending_preview", query, timeout=30)
        if method == "POST" and path == "/pending/approve":
            return 200, self.worker.submit("pending_approve", body, timeout=60)
        if method == "POST" and path == "/pending/reject":
            return 200, self.worker.submit("pending_reject", body, timeout=30)
        if method == "GET" and path == "/knowledge/verify":
            return 200, self.worker.submit("knowledge_verify", {}, timeout=30)
        if method == "POST" and path == "/knowledge/rebuild":
            return 200, self.worker.submit("knowledge_rebuild", {}, timeout=60)
        if method == "POST" and path == "/knowledge/search":
            return 200, self.worker.submit("knowledge_search", body, timeout=30)
        if method == "POST" and path == "/knowledge/compose":
            return 200, self.worker.submit("knowledge_compose", body, timeout=30)
        if method == "GET" and path == "/knowledge/assets/get":
            return 200, self.worker.submit("knowledge_asset_get", query, timeout=30)
        if method == "GET" and path == "/knowledge/assets":
            return 200, self.worker.submit("knowledge_assets", query, timeout=30)
        if method == "GET" and path == "/knowledge/stats":
            return 200, self.worker.submit("knowledge_stats", {}, timeout=30)
        raise VerifierError("route_not_found", f"未知 verifier endpoint：{path}", status=404)


class VerifierHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], application: VerifierApplication) -> None:
        self.application = application
        super().__init__(address, VerifierHandler)


class VerifierHandler(http.server.BaseHTTPRequestHandler):
    server: VerifierHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self, path: str) -> bool:
        if path == "/health":
            return True
        return token_matches(self.server.application.token, self.headers.get("Authorization", ""))

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise VerifierError("invalid_content_length", "Content-Length 必须是整数") from exc
        if length < 0 or length > self.server.application.limits.request_body_bytes:
            raise VerifierError("request_too_large", "request body 超过服务上限", status=413)
        if length == 0:
            return {}
        try:
            raw = self.rfile.read(length)
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerifierError("invalid_json", f"request body 不是有效 UTF-8 JSON：{exc}") from exc
        if not isinstance(value, dict):
            raise VerifierError("invalid_json", "request body 根节点必须是 object")
        ensure_json_depth(value, self.server.application.limits.json_depth)
        return value

    def _send(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(redact(value), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > self.server.application.limits.response_body_bytes:
            status = 500
            body = b'{"ok":false,"code":"response_too_large","error":"response exceeded service limit"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _handle(self, method: str) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if not self._authorized(path):
            self._send(401, VerifierError("unauthorized", "bearer token 无效", status=401).envelope())
            return
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=False))
        try:
            body = self._body() if method == "POST" else {}
            status, result = self.server.application.route(method, path, query, body)
            self._send(status, result)
        except VerifierError as exc:
            self._send(exc.status, exc.envelope())
        except Exception as exc:
            print(f"electron-ui-verifier internal error: {type(exc).__name__}: {redact(str(exc))}", file=sys.stderr, flush=True)
            self._send(500, VerifierError("internal_error", "verifier service 内部错误", status=500).envelope())

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")


def _bind_server(config: ServiceConfig, application: VerifierApplication) -> VerifierHTTPServer:
    last_error: OSError | None = None
    for offset in range(config.max_port_switches + 1):
        port = config.port + offset
        if port > 65535:
            break
        try:
            server = VerifierHTTPServer((config.host, port), application)
        except OSError as exc:
            last_error = exc
            continue
        application.actual_port = port
        if port != config.port:
            data = json.loads(config.config_file.read_text(encoding="utf-8-sig"))
            data["port"] = port
            atomic_write_json(config.config_file, data)
        return server
    raise VerifierError("bind_failed", f"无法绑定 verifier service 端口：{last_error}", status=500)


def serve(config_path: Path) -> int:
    config = ServiceConfig.load(config_path)
    application = VerifierApplication(config)
    application.start()
    server: VerifierHTTPServer | None = None
    try:
        server = _bind_server(config, application)
        atomic_write_json(
            config.server_file,
            {
                "schemaVersion": 1,
                "status": "ready",
                "host": config.host,
                "port": application.actual_port,
                "pid": os.getpid(),
                "backend": "playwright-cdp",
                "processManagerService": "electron-ui-verifier",
                "startedAt": _now(),
            },
        )
        print(f"EV_READY http://{config.host}:{application.actual_port}/health", flush=True)
        server.serve_forever(poll_interval=0.2)
        return 0
    finally:
        if server is not None:
            server.server_close()
        application.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 Electron UI verifier HTTP service。")
    parser.add_argument("--config", required=True, help="config.json 的绝对路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            raise VerifierError("invalid_config_path", "--config 必须是绝对路径")
        return serve(config_path)
    except VerifierError as exc:
        print(json.dumps(exc.envelope(), ensure_ascii=False), file=sys.stderr)
        return 2
