#!/usr/bin/env python3
"""process-manager 本地常驻管理服务。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pm_common import (
    DEFAULT_HOST,
    PMError,
    ManagerConfig,
    generate_process_id,
    http_request,
    is_relative_to,
    launcher_command,
    load_manager_config,
    load_processes,
    now_text,
    pid_alive,
    print_json,
    process_key,
    read_token,
    save_processes,
    service_from_path,
    split_process_key,
    stop_pid_tree,
    tcp_ready,
    validate_service_config,
)


class ProcessManager:
    """持有业务进程生命周期的 manager 核心。"""

    def __init__(self, config: ManagerConfig) -> None:
        self.config = config

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "manager": "process-manager",
            "host": self.config.host,
            "port": self.config.port,
            "workspaceRoot": str(self.config.workspace_root),
            "stateRoot": str(self.config.state_root),
        }

    def start(self, service_path: Path) -> dict[str, Any]:
        service_path = service_path.resolve()
        if not is_relative_to(service_path, self.config.workspace_root):
            raise PMError("servicePath 必须位于 workspaceRoot 内")
        service = validate_service_config(service_from_path(service_path), self.config.workspace_root)
        existing = self.status(service=service["name"], allow_missing=True)
        if existing.get("status") == "running":
            return {"ok": True, "result": "already_running", **existing}

        process_id = generate_process_id()
        key = process_key(service["name"], process_id)
        run_dir = self.config.runs_dir / service["name"] / process_id
        run_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        pid_file = run_dir / "pid"
        process_file = run_dir / "process.json"
        command = launcher_command(service["launcher"])
        env = os.environ.copy()
        env.update(service.get("env", {}))

        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)

        with stdout_path.open("ab") as stdout_handle, stderr_path.open("ab") as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=service["cwd"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                close_fds=True,
                creationflags=flags,
                start_new_session=os.name != "nt",
            )

        time.sleep(0.3)
        exit_code = process.poll()
        if exit_code is not None:
            record = self._base_record(service, process_id, key, run_dir, stdout_path, stderr_path, pid_file, service_path)
            record.update({"pid": process.pid, "status": "exited", "exitCode": exit_code, "startedAt": now_text()})
            self._write_record(record, process_file)
            raise PMError(f"服务启动后立即退出：{service['name']} exit_code={exit_code}")

        pid_file.write_text(f"{process.pid}\n", encoding="ascii", newline="\n")
        record = self._base_record(service, process_id, key, run_dir, stdout_path, stderr_path, pid_file, service_path)
        record.update(
            {
                "pid": process.pid,
                "status": "running",
                "startedAt": now_text(),
                "startedAtEpoch": time.time(),
                "command": command,
                "observed": {},
            }
        )
        self._write_record(record, process_file)
        state = load_processes(self.config)
        state["active"][service["name"]] = key
        state["processes"][key] = record
        save_processes(self.config, state)
        return {"ok": True, "result": "started", **record}

    def status(self, service: str | None = None, process_key_value: str | None = None, allow_missing: bool = False) -> dict[str, Any]:
        state = load_processes(self.config)
        key = process_key_value
        if not key and service:
            key = state.get("active", {}).get(service)
        if not key:
            if allow_missing:
                return {"ok": True, "status": "not_found", "service": service}
            raise PMError("未找到 active process，请提供 service 或 processKey")
        record = state.get("processes", {}).get(key)
        if not isinstance(record, dict):
            if allow_missing:
                return {"ok": True, "status": "not_found", "service": service, "processKey": key}
            raise PMError(f"processKey 不存在：{key}")
        status = self._refresh_record(record)
        state["processes"][key] = status
        if status.get("status") != "running" and state.get("active", {}).get(status.get("service")) == key:
            state["active"].pop(status["service"], None)
        save_processes(self.config, state)
        return {"ok": True, **status}

    def list_processes(self) -> dict[str, Any]:
        state = load_processes(self.config)
        refreshed: dict[str, Any] = {}
        for key, record in list(state.get("processes", {}).items()):
            if isinstance(record, dict):
                refreshed[key] = self._refresh_record(record)
        state["processes"] = refreshed
        for service, key in list(state.get("active", {}).items()):
            if refreshed.get(key, {}).get("status") != "running":
                state["active"].pop(service, None)
        save_processes(self.config, state)
        return {"ok": True, "active": state.get("active", {}), "processes": refreshed}

    def stop(self, service: str | None = None, process_key_value: str | None = None) -> dict[str, Any]:
        status = self.status(service=service, process_key_value=process_key_value)
        pid = status.get("pid")
        if status.get("status") != "running" or not isinstance(pid, int):
            return {"ok": True, "result": "not_running", **status}
        stopped = stop_pid_tree(pid)
        state = load_processes(self.config)
        key = status["processKey"]
        record = state["processes"].get(key, status)
        record["status"] = "stopped" if stopped else "stop_timeout"
        record["stoppedAt"] = now_text() if stopped else None
        state["processes"][key] = record
        if stopped and state.get("active", {}).get(record.get("service")) == key:
            state["active"].pop(record["service"], None)
        save_processes(self.config, state)
        return {"ok": True, "result": record["status"], **record}

    def ready(self, service: str | None = None, process_key_value: str | None = None, timeout_override: float | None = None) -> dict[str, Any]:
        status = self.status(service=service, process_key_value=process_key_value)
        if status.get("status") != "running":
            return {"ok": False, "status": "not_ready", "reason": "not_running", **status}
        readiness = status.get("serviceConfig", {}).get("readiness")
        if not readiness:
            return {"ok": True, "status": "running", "ready": False, "reason": "readiness_not_configured", **status}
        timeout = float(timeout_override or readiness.get("timeoutSeconds", 30))
        deadline = time.monotonic() + timeout
        last = status
        while time.monotonic() <= deadline:
            last = self.status(process_key_value=status["processKey"])
            if last.get("status") != "running":
                return {"ok": False, "status": "not_ready", "reason": "process_exited", **last}
            ready_result = self._check_readiness(last, readiness)
            if ready_result.get("ready"):
                self._merge_observed(last["processKey"], ready_result.get("observed", {}))
                return {"ok": True, "status": "ready", **last, **ready_result}
            time.sleep(0.25)
        return {"ok": False, "status": "not_ready", "reason": "timeout", **last}

    def logs(self, service: str | None = None, process_key_value: str | None = None, stream: str = "stdout", tail: int = 80) -> dict[str, Any]:
        status = self.status(service=service, process_key_value=process_key_value)
        if stream not in {"stdout", "stderr"}:
            raise PMError("stream 只支持 stdout 或 stderr")
        path = Path(status[stream])
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, min(tail, 500)) :]
        return {"ok": True, "path": str(path), "lines": lines, **status}

    def _base_record(
        self,
        service: dict[str, Any],
        process_id: str,
        key: str,
        run_dir: Path,
        stdout_path: Path,
        stderr_path: Path,
        pid_file: Path,
        service_path: Path,
    ) -> dict[str, Any]:
        return {
            "service": service["name"],
            "processId": process_id,
            "processKey": key,
            "servicePath": str(service_path.resolve()),
            "serviceConfig": service,
            "runDir": str(run_dir),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "pidFile": str(pid_file),
            "processFile": str(run_dir / "process.json"),
            "window": "hidden",
        }

    def _write_record(self, record: dict[str, Any], process_file: Path) -> None:
        from pm_common import write_json_atomic

        write_json_atomic(process_file, record)

    def _refresh_record(self, record: dict[str, Any]) -> dict[str, Any]:
        refreshed = dict(record)
        pid = refreshed.get("pid")
        alive = pid_alive(pid if isinstance(pid, int) else None)
        if refreshed.get("status") == "running" and not alive:
            refreshed["status"] = "exited"
            refreshed.setdefault("exitedAt", now_text())
        process_file = refreshed.get("processFile")
        if isinstance(process_file, str):
            self._write_record(refreshed, Path(process_file))
        return refreshed

    def _check_readiness(self, status: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
        kind = readiness.get("type")
        if kind == "http":
            url = readiness["url"]
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    return {"ready": 200 <= response.status < 400, "readyBy": "http", "observed": {"urls": [url]}}
            except (urllib.error.URLError, TimeoutError, OSError):
                return {"ready": False}
        if kind == "tcp":
            host = readiness["host"]
            port = int(readiness["port"])
            return {"ready": tcp_ready(host, port, 2), "readyBy": "tcp", "observed": {"ports": [port]}}
        if kind == "log":
            text = self._read_combined_logs(status)
            pattern = readiness["pattern"]
            matched = re.search(pattern, text) is not None
            observed = self._extract_observed(text, readiness.get("extract", {})) if matched else {}
            return {"ready": matched, "readyBy": "log", "observed": observed}
        if kind == "process":
            stable_seconds = float(readiness.get("stableSeconds", 1))
            started_at_epoch = status.get("startedAtEpoch")
            if not isinstance(started_at_epoch, (int, float)):
                return {"ready": False, "readyBy": "process"}
            return {"ready": time.time() - float(started_at_epoch) >= stable_seconds, "readyBy": "process"}
        return {"ready": False}

    def _read_combined_logs(self, status: dict[str, Any]) -> str:
        chunks: list[str] = []
        for key in ("stdout", "stderr"):
            path = Path(status[key])
            if path.exists():
                chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(chunks)

    def _extract_observed(self, text: str, extract: Any) -> dict[str, Any]:
        if not isinstance(extract, dict):
            return {}
        observed: dict[str, Any] = {}
        for key, patterns in extract.items():
            if not isinstance(patterns, list):
                continue
            values: list[str] = []
            for pattern in patterns:
                if isinstance(pattern, str):
                    values.extend(match.group(0) for match in re.finditer(pattern, text))
            if key == "ports":
                ints = []
                for value in values:
                    try:
                        ints.append(int(value))
                    except ValueError:
                        pass
                observed[key] = sorted(set(ints))
            else:
                observed[key] = sorted(set(values))
        return observed

    def _merge_observed(self, key: str, observed: dict[str, Any]) -> None:
        if not observed:
            return
        state = load_processes(self.config)
        record = state.get("processes", {}).get(key)
        if not isinstance(record, dict):
            return
        current = record.setdefault("observed", {})
        for name, values in observed.items():
            old = current.get(name, [])
            if not isinstance(old, list):
                old = []
            if isinstance(values, list):
                current[name] = sorted(set(old + values), key=str)
        state["processes"][key] = record
        save_processes(self.config, state)
        process_file = record.get("processFile")
        if isinstance(process_file, str):
            self._write_record(record, Path(process_file))


class Handler(BaseHTTPRequestHandler):
    server_version = "ProcessManager/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    @property
    def manager(self) -> ProcessManager:
        return self.server.manager  # type: ignore[attr-defined]

    def _auth_ok(self) -> bool:
        expected = read_token(self.manager.config)
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {expected}"

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PMError(f"请求 JSON 格式错误：{exc}") from exc
        if not isinstance(data, dict):
            raise PMError("请求体必须是 JSON object")
        return data

    def _query(self) -> dict[str, list[str]]:
        from urllib.parse import parse_qs, urlparse

        return parse_qs(urlparse(self.path).query)

    def _path(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.path).path

    def do_GET(self) -> None:
        try:
            if not self._auth_ok():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            path = self._path()
            query = self._query()
            if path == "/health":
                self._send_json(200, self.manager.health())
                return
            if path == "/processes":
                self._send_json(200, self.manager.list_processes())
                return
            if path == "/processes/status":
                self._send_json(200, self.manager.status(query.get("service", [None])[0], query.get("processKey", [None])[0]))
                return
            if path == "/processes/logs":
                stream = query.get("stream", ["stdout"])[0]
                tail = int(query.get("tail", ["80"])[0])
                self._send_json(200, self.manager.logs(query.get("service", [None])[0], query.get("processKey", [None])[0], stream, tail))
                return
            self._send_json(404, {"ok": False, "error": "not_found"})
        except PMError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        try:
            if not self._auth_ok():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            path = self._path()
            data = self._read_body()
            if path == "/processes/start":
                self._send_json(200, self.manager.start(Path(data["servicePath"])))
                return
            if path == "/processes/ready":
                result = self.manager.ready(data.get("service"), data.get("processKey"), data.get("timeoutSeconds"))
                self._send_json(200 if result.get("ok") else 503, result)
                return
            if path == "/processes/stop":
                self._send_json(200, self.manager.stop(data.get("service"), data.get("processKey")))
                return
            self._send_json(404, {"ok": False, "error": "not_found"})
        except KeyError as exc:
            self._send_json(400, {"ok": False, "error": f"缺少字段：{exc}"})
        except PMError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


class PMHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], manager: ProcessManager) -> None:
        super().__init__(server_address, Handler)
        self.manager = manager


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动 process-manager 本地管理服务")
    parser.add_argument("--config", required=True, help="manager-config.json 绝对路径")
    parser.add_argument("--stdout-log", help="manager stdout 日志路径")
    parser.add_argument("--stderr-log", help="manager stderr 日志路径")
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        raise SystemExit("manager --config 必须是绝对路径")
    if args.stdout_log:
        stdout_path = Path(args.stdout_log)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = stdout_path.open("a", encoding="utf-8", buffering=1)
    if args.stderr_log:
        stderr_path = Path(args.stderr_log)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stderr = stderr_path.open("a", encoding="utf-8", buffering=1)
    config = load_manager_config(config_path)
    if config.host != DEFAULT_HOST:
        raise SystemExit("manager 只允许绑定 127.0.0.1")
    server = PMHTTPServer((config.host, config.port), ProcessManager(config))
    print_json({"ok": True, "status": "listening", "host": config.host, "port": config.port})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
