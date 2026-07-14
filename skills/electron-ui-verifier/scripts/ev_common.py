#!/usr/bin/env python3
"""Electron verifier server 的共享配置和客户端工具。"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18180
SERVICE_NAME = "electron-ui-verifier"
FINAL_OPERATION_STATES = {"succeeded", "failed", "cancelled", "deadline_exceeded", "unknown"}


class EVError(RuntimeError):
    """用于向 CLI 返回可读错误。"""


@dataclass(frozen=True)
class EVPaths:
    workspace_root: Path
    state_root: Path
    environment_file: Path
    config_file: Path
    token_file: Path
    server_file: Path
    sessions_file: Path
    reports_dir: Path
    pending_dir: Path
    workflows_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    tmp_dir: Path
    operations_dir: Path
    service_file: Path


@dataclass(frozen=True)
class EVConfig:
    host: str
    port: int
    port_retry_enabled: bool
    port_retry_max_switches: int
    workspace_root: Path
    state_root: Path
    token_file: Path
    server_file: Path
    sessions_file: Path
    reports_dir: Path
    pending_dir: Path
    workflows_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    tmp_dir: Path
    operations_dir: Path

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def fail(error: str, code: str = "error", exit_code: int = 2) -> int:
    print_json({"ok": False, "code": code, "error": error})
    return exit_code


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_json_arg(value: str, label: str) -> Any:
    path = Path(value)
    if path.is_absolute() and path.exists():
        return read_json(path)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise EVError(f"{label} must be an absolute JSON file path or JSON string") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(path)


def ensure_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EVError(f"{label} must be an object")
    return value


def require_absolute_path(value: Any, label: str, must_exist: bool = False) -> Path:
    if not isinstance(value, str) or not value:
        raise EVError(f"{label} must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        raise EVError(f"{label} must be an absolute path: {value}")
    if must_exist and not path.exists():
        raise EVError(f"{label} does not exist: {value}")
    return path


def discover_workspace_root(value: str | None = None) -> Path:
    if value:
        return require_absolute_path(value, "--workspace", must_exist=True)
    return Path.cwd().resolve()


def paths_for_workspace(workspace_root: Path) -> EVPaths:
    state_root = workspace_root / ".harness" / "electron-ui-verifier"
    return EVPaths(
        workspace_root=workspace_root,
        state_root=state_root,
        environment_file=state_root / "environment.json",
        config_file=state_root / "config.json",
        token_file=state_root / "token",
        server_file=state_root / "server.json",
        sessions_file=state_root / "sessions.json",
        reports_dir=state_root / "reports",
        pending_dir=state_root / "pending",
        workflows_dir=state_root / "workflows",
        artifacts_dir=state_root / "artifacts",
        logs_dir=state_root / "logs",
        tmp_dir=state_root / "tmp",
        operations_dir=state_root / "operations",
        service_file=workspace_root / ".harness" / "process-manager" / "services" / f"{SERVICE_NAME}.json",
    )


def resolve_config_path(args: argparse.Namespace | None = None) -> Path:
    config_arg = getattr(args, "config", None) if args is not None else None
    if config_arg:
        return require_absolute_path(config_arg, "--config", must_exist=True)
    workspace_arg = getattr(args, "workspace", None) if args is not None else None
    workspace_root = discover_workspace_root(workspace_arg)
    return paths_for_workspace(workspace_root).config_file


def normalize_host(host: Any) -> str:
    if host not in (None, "", DEFAULT_HOST):
        raise EVError("server.host only supports 127.0.0.1")
    return DEFAULT_HOST


def normalize_port(value: Any, label: str = "server.port") -> int:
    port = int(value if value not in (None, "") else DEFAULT_PORT)
    if port < 1 or port > 65535:
        raise EVError(f"{label} must be in 1-65535")
    return port


def load_environment(paths: EVPaths) -> dict[str, Any]:
    if not paths.environment_file.exists():
        return {}
    return ensure_object(read_json(paths.environment_file), "environment")


def write_environment(paths: EVPaths, python_path: Path | None = None, port: int | None = None) -> dict[str, Any]:
    existing = load_environment(paths)
    selected_python = python_path or Path(str(existing.get("python") or sys.executable)).resolve()
    if not selected_python.is_absolute() or not selected_python.exists():
        raise EVError(f"python must be an existing absolute path: {selected_python}")
    server = ensure_object(existing.get("server") or {}, "environment.server")
    environment = {
        "python": str(selected_python),
        "workspaceRoot": str(paths.workspace_root),
        "server": {
            "host": normalize_host(server.get("host")),
            "port": normalize_port(port if port is not None else server.get("port")),
        },
        "updatedAt": iso_now(),
    }
    write_json(paths.environment_file, environment)
    return environment


def ensure_runtime_dirs(paths: EVPaths) -> None:
    for folder in (paths.state_root, paths.reports_dir, paths.pending_dir, paths.workflows_dir, paths.artifacts_dir, paths.logs_dir, paths.tmp_dir, paths.operations_dir, paths.service_file.parent):
        folder.mkdir(parents=True, exist_ok=True)


def ensure_token(paths: EVPaths) -> str:
    if paths.token_file.exists():
        token = paths.token_file.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    paths.token_file.parent.mkdir(parents=True, exist_ok=True)
    paths.token_file.write_text(token + "\n", encoding="utf-8")
    return token


def config_from_data(data: dict[str, Any]) -> EVConfig:
    workspace_root = require_absolute_path(data.get("workspaceRoot"), "config.workspaceRoot", must_exist=True)
    state_root = require_absolute_path(data.get("stateRoot"), "config.stateRoot")
    port_retry = ensure_object(data.get("portRetry") or {}, "config.portRetry")
    workflows_dir = data.get("workflowsDir") or str(state_root / "workflows")
    pending_dir = data.get("pendingDir") or str(state_root / "pending")
    return EVConfig(
        host=normalize_host(data.get("host")),
        port=normalize_port(data.get("port"), "config.port"),
        port_retry_enabled=bool(port_retry.get("enabled", True)),
        port_retry_max_switches=int(port_retry.get("maxSwitches", 3)),
        workspace_root=workspace_root,
        state_root=state_root,
        token_file=require_absolute_path(data.get("tokenFile"), "config.tokenFile"),
        server_file=require_absolute_path(data.get("serverFile"), "config.serverFile"),
        sessions_file=require_absolute_path(data.get("sessionsFile"), "config.sessionsFile"),
        reports_dir=require_absolute_path(data.get("reportsDir"), "config.reportsDir"),
        pending_dir=require_absolute_path(pending_dir, "config.pendingDir"),
        workflows_dir=require_absolute_path(workflows_dir, "config.workflowsDir"),
        artifacts_dir=require_absolute_path(data.get("artifactsDir"), "config.artifactsDir"),
        logs_dir=require_absolute_path(data.get("logsDir"), "config.logsDir"),
        tmp_dir=require_absolute_path(data.get("tmpDir"), "config.tmpDir"),
        operations_dir=require_absolute_path(
            data.get("operationsDir") or str(state_root / "operations"),
            "config.operationsDir",
        ),
    )


def load_config(path: Path) -> EVConfig:
    if not path.exists():
        raise EVError(f"config file does not exist: {path}")
    return config_from_data(ensure_object(read_json(path), "config"))


def config_to_data(paths: EVPaths, environment: dict[str, Any]) -> dict[str, Any]:
    server = ensure_object(environment.get("server") or {}, "environment.server")
    return {
        "host": normalize_host(server.get("host")),
        "port": normalize_port(server.get("port")),
        "portRetry": {"enabled": True, "maxSwitches": 3},
        "workspaceRoot": str(paths.workspace_root),
        "stateRoot": str(paths.state_root),
        "tokenFile": str(paths.token_file),
        "serverFile": str(paths.server_file),
        "sessionsFile": str(paths.sessions_file),
        "reportsDir": str(paths.reports_dir),
        "pendingDir": str(paths.pending_dir),
        "workflowsDir": str(paths.workflows_dir),
        "artifactsDir": str(paths.artifacts_dir),
        "logsDir": str(paths.logs_dir),
        "tmpDir": str(paths.tmp_dir),
        "operationsDir": str(paths.operations_dir),
    }


def read_token(config: EVConfig) -> str:
    if not config.token_file.exists():
        raise EVError(f"token file does not exist: {config.token_file}")
    token = config.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise EVError("token file is empty")
    return token


def request_json(config: EVConfig, method: str, path: str, payload: Any | None = None, timeout: float = 30.0) -> dict[str, Any]:
    token = read_token(config)
    url = urllib.parse.urljoin(config.base_url, path)
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method.upper())
    request.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return ensure_object(json.loads(text), "error response")
        except json.JSONDecodeError:
            raise EVError(f"server HTTP {exc.code}: {text}") from exc
    except urllib.error.URLError as exc:
        raise EVError(f"failed to call verifier server {url}: {exc}") from exc
    try:
        return ensure_object(json.loads(text), "server response")
    except json.JSONDecodeError as exc:
        raise EVError(f"server returned non-JSON response: {text[:200]}") from exc


def result_exit_code(result: dict[str, Any]) -> int:
    return 0 if result.get("ok") is not False else 2


def wait_for_operation(
    config: EVConfig,
    operation_id: str,
    timeout_seconds: float,
    poll_seconds: float = 0.2,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise EVError("operation wait timeout must be greater than zero")
    if poll_seconds <= 0 or poll_seconds > 5:
        raise EVError("operation poll interval must be in (0, 5]")
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while True:
        query = urllib.parse.urlencode({"operationId": operation_id})
        last = request_json(config, "GET", f"/operations/get?{query}", timeout=min(30.0, timeout_seconds))
        operation = last.get("operation")
        if not isinstance(operation, dict):
            raise EVError("operation response is missing operation object")
        if operation.get("state") in FINAL_OPERATION_STATES:
            return last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "ok": False,
                "code": "operation_wait_timeout",
                "error": "client wait timeout；operation 仍可继续查询或取消",
                "operation": operation,
            }
        time.sleep(min(poll_seconds, remaining))


def operation_exit_code(result: dict[str, Any]) -> int:
    operation = result.get("operation")
    if result.get("ok") is False:
        return 2
    if not isinstance(operation, dict) or operation.get("state") not in FINAL_OPERATION_STATES:
        return 0
    return 0 if operation.get("state") == "succeeded" else 2


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="verifier config.json 的绝对路径")
    parser.add_argument("--workspace", help="workspace 根目录绝对路径；未指定时使用当前目录")
