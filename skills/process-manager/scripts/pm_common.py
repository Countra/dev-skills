#!/usr/bin/env python3
"""process-manager 共享工具函数。"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 49321
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PROCESS_ID_RE = re.compile(r"^pm-\d{8}-\d{6}-[0-9a-f]{4,12}$")
PATH_FLAG_RE = re.compile(r"(path|file|dir|root|config|script|output|input|log)$", re.IGNORECASE)


class PMError(RuntimeError):
    """可安全返回给调用方的 process-manager 错误。"""


@dataclass(frozen=True)
class ManagerConfig:
    host: str
    port: int
    workspace_root: Path
    state_root: Path
    token_file: Path

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def processes_file(self) -> Path:
        return self.state_root / "processes.json"

    @property
    def runs_dir(self) -> Path:
        return self.state_root / "runs"

    @property
    def logs_dir(self) -> Path:
        return self.state_root / "logs"

    @property
    def services_dir(self) -> Path:
        return self.state_root / "services"

    @property
    def manager_pid_file(self) -> Path:
        return self.state_root / "manager.pid"


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_json(path: Path) -> Any:
    if not path.exists():
        raise PMError(f"文件不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PMError(f"JSON 格式错误：{path}: {exc}") from exc


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def ensure_object(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PMError(f"{label} 必须是 JSON object")
    return data


def ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PMError(f"{label} 必须是非空字符串")
    return value


def ensure_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PMError(f"{label} 必须是整数")
    return value


def require_absolute_path(value: Any, label: str, must_exist: bool = False) -> Path:
    text = ensure_string(value, label)
    path = Path(text)
    if not path.is_absolute():
        raise PMError(f"{label} 必须是绝对路径：{text}")
    resolved = path.resolve()
    if must_exist and not resolved.exists():
        raise PMError(f"{label} 不存在：{resolved}")
    return resolved


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def default_config_path(workspace: Path | None = None) -> Path:
    root = (workspace or Path.cwd()).resolve()
    return root / ".harness" / "process-manager" / "config.json"


def default_state_root(workspace: Path) -> Path:
    return workspace.resolve() / ".harness" / "process-manager"


def load_manager_config(path: Path) -> ManagerConfig:
    data = ensure_object(read_json(path), "manager config")
    host = ensure_string(data.get("host"), "host")
    if host != DEFAULT_HOST:
        raise PMError("manager host 只允许 127.0.0.1")
    port = ensure_int(data.get("port"), "port")
    if port <= 0 or port > 65535:
        raise PMError("port 必须在 1-65535 范围内")
    workspace_root = require_absolute_path(data.get("workspaceRoot"), "workspaceRoot", must_exist=True)
    state_root = require_absolute_path(data.get("stateRoot"), "stateRoot")
    token_file = require_absolute_path(data.get("tokenFile"), "tokenFile")
    if not is_relative_to(state_root, workspace_root):
        raise PMError("stateRoot 必须位于 workspaceRoot 内")
    if not is_relative_to(token_file, state_root):
        raise PMError("tokenFile 必须位于 stateRoot 内")
    return ManagerConfig(
        host=host,
        port=port,
        workspace_root=workspace_root,
        state_root=state_root,
        token_file=token_file,
    )


def create_default_manager_config(workspace: Path, path: Path | None = None) -> ManagerConfig:
    root = workspace.resolve()
    state_root = default_state_root(root)
    config_path = path or state_root / "config.json"
    config = {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "workspaceRoot": str(root),
        "stateRoot": str(state_root),
        "tokenFile": str(state_root / "token"),
    }
    write_json_atomic(config_path, config)
    for folder in ("services", "runs", "logs", "tmp"):
        (state_root / folder).mkdir(parents=True, exist_ok=True)
    token_path = state_root / "token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8", newline="\n")
    processes_file = state_root / "processes.json"
    if not processes_file.exists():
        write_json_atomic(processes_file, {"active": {}, "processes": {}})
    return load_manager_config(config_path)


def read_token(config: ManagerConfig) -> str:
    if not config.token_file.exists():
        raise PMError(f"token 文件不存在：{config.token_file}")
    token = config.token_file.read_text(encoding="utf-8-sig").strip()
    if not token:
        raise PMError("token 文件为空")
    return token


def load_processes(config: ManagerConfig) -> dict[str, Any]:
    if not config.processes_file.exists():
        return {"active": {}, "processes": {}}
    data = ensure_object(read_json(config.processes_file), "processes state")
    active = data.get("active")
    processes = data.get("processes")
    if not isinstance(active, dict):
        data["active"] = {}
    if not isinstance(processes, dict):
        data["processes"] = {}
    return data


def save_processes(config: ManagerConfig, data: dict[str, Any]) -> None:
    write_json_atomic(config.processes_file, data)


def generate_process_id() -> str:
    return f"pm-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def process_key(service_name: str, process_id: str) -> str:
    return f"{service_name}.{process_id}"


def split_process_key(value: str) -> tuple[str, str]:
    if "." not in value:
        raise PMError(f"processKey 格式错误：{value}")
    service, pid = value.rsplit(".", 1)
    if not service or not PROCESS_ID_RE.match(pid):
        raise PMError(f"processKey 格式错误：{value}")
    return service, pid


def validate_service_name(name: Any) -> str:
    text = ensure_string(name, "service.name")
    if not SERVICE_NAME_RE.match(text):
        raise PMError("service.name 只能包含字母、数字、点、下划线和短横线")
    return text


def service_from_path(path: Path) -> dict[str, Any]:
    return ensure_object(read_json(path), "service config")


def validate_service_config(service: dict[str, Any], workspace_root: Path | None = None) -> dict[str, Any]:
    name = validate_service_name(service.get("name"))
    kind = service.get("kind", "long-running")
    if kind != "long-running":
        raise PMError("service.kind 只支持 long-running")
    if "host" in service or "port" in service:
        raise PMError("service 顶层不允许通用 host/port；端点应写入 readiness 或启动参数")
    window = service.get("window", "hidden")
    if window != "hidden":
        raise PMError("service.window 只支持 hidden 或省略")
    cwd = require_absolute_path(service.get("cwd"), "service.cwd", must_exist=True)
    if workspace_root and not is_relative_to(cwd, workspace_root):
        raise PMError("service.cwd 必须位于 workspaceRoot 内")
    launcher = ensure_object(service.get("launcher"), "launcher")
    validate_launcher(launcher, cwd)
    env = service.get("env", {})
    if env is not None:
        env_obj = ensure_object(env, "service.env")
        for key, value in env_obj.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise PMError("service.env 只支持 string:string")
    readiness = service.get("readiness")
    if readiness is not None:
        validate_readiness(ensure_object(readiness, "readiness"))
    return {
        "name": name,
        "kind": kind,
        "cwd": str(cwd),
        "launcher": launcher,
        "env": env or {},
        "window": window,
        "readiness": readiness,
    }


def validate_launcher(launcher: dict[str, Any], cwd: Path) -> None:
    launcher_type = ensure_string(launcher.get("type"), "launcher.type")
    if launcher.get("shell") is True:
        raise PMError("不允许 shell: true")
    if launcher_type == "direct":
        argv = launcher.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            raise PMError("direct.argv 必须是非空字符串数组")
        require_absolute_path(argv[0], "direct.argv[0]", must_exist=True)
        validate_path_like_args(argv[1:])
        return
    if launcher_type == "cmd-file":
        script = require_absolute_path(launcher.get("script"), "cmd-file.script", must_exist=True)
        if script.suffix.lower() not in {".cmd", ".bat"}:
            raise PMError("cmd-file.script 必须是 .cmd 或 .bat")
        validate_args(launcher.get("args", []), "cmd-file.args")
        return
    if launcher_type == "powershell-file":
        script = require_absolute_path(launcher.get("script"), "powershell-file.script", must_exist=True)
        if script.suffix.lower() != ".ps1":
            raise PMError("powershell-file.script 必须是 .ps1")
        validate_args(launcher.get("args", []), "powershell-file.args")
        return
    raise PMError("launcher.type 只支持 direct、cmd-file、powershell-file")


def validate_args(args: Any, label: str) -> None:
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise PMError(f"{label} 必须是字符串数组")
    validate_path_like_args(args)


def validate_path_like_args(args: list[str]) -> None:
    for index, item in enumerate(args):
        if item.startswith("-"):
            continue
        previous = args[index - 1] if index > 0 else ""
        if PATH_FLAG_RE.search(previous.lstrip("-")):
            require_absolute_path(item, f"参数 {previous}")


def validate_readiness(readiness: dict[str, Any]) -> None:
    kind = ensure_string(readiness.get("type"), "readiness.type")
    timeout = readiness.get("timeoutSeconds", 30)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise PMError("readiness.timeoutSeconds 必须是正数")
    if kind == "http":
        url = ensure_string(readiness.get("url"), "readiness.url")
        if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")):
            raise PMError("readiness.http 只允许本地 URL")
        return
    if kind == "tcp":
        host = ensure_string(readiness.get("host"), "readiness.host")
        if host not in {"127.0.0.1", "localhost"}:
            raise PMError("readiness.tcp 只允许本地 host")
        port = ensure_int(readiness.get("port"), "readiness.port")
        if port <= 0 or port > 65535:
            raise PMError("readiness.port 必须在 1-65535 范围内")
        return
    if kind == "log":
        ensure_string(readiness.get("pattern"), "readiness.pattern")
        extract = readiness.get("extract")
        if extract is not None:
            extract_obj = ensure_object(extract, "readiness.extract")
            for value in extract_obj.values():
                if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                    raise PMError("readiness.extract 的值必须是非空字符串数组")
        return
    if kind == "process":
        stable = readiness.get("stableSeconds", 1)
        if not isinstance(stable, (int, float)) or stable <= 0:
            raise PMError("readiness.stableSeconds 必须是正数")
        return
    raise PMError("readiness.type 只支持 http、tcp、log、process")


def launcher_command(launcher: dict[str, Any]) -> list[str]:
    launcher_type = launcher["type"]
    if launcher_type == "direct":
        return list(launcher["argv"])
    if launcher_type == "cmd-file":
        return [
            str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"),
            "/d",
            "/s",
            "/c",
            launcher["script"],
            *list(launcher.get("args", [])),
        ]
    if launcher_type == "powershell-file":
        return [
            str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            launcher["script"],
            *list(launcher.get("args", [])),
        ]
    raise PMError(f"不支持的 launcher.type：{launcher_type}")


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_pid_tree(pid: int) -> bool:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.2)
    return not pid_alive(pid)


def http_request(config: ManagerConfig, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 35) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {read_token(config)}",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(f"{config.base_url}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            data = {"error": text}
        if "error" not in data:
            data["error"] = f"HTTP {exc.code} {exc.reason}"
        data.setdefault("ok", False)
        return exc.code, data
    except urllib.error.URLError as exc:
        raise PMError(f"manager 不可用：{exc}") from exc


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)


def fail(message: str) -> int:
    print_json({"ok": False, "error": message})
    return 1


def is_windows() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def require_windows() -> None:
    if not is_windows():
        raise PMError("当前版本只支持 Windows")


def tcp_ready(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
