"""manager 与 service 的封闭配置 schema。"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

from .errors import ConfigurationError, ValidationError
from .logs import write_capped_json
from .models import ManagerConfig, ServiceConfig
from .patterns import compile_log_pattern


MAX_CONFIG_BYTES = 1024 * 1024
MAX_ENV_BYTES = 64 * 1024
DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_HISTORY_MAX_INACTIVE = 20
DEFAULT_HISTORY_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
DEFAULT_HISTORY_MAX_TOMBSTONES = 200
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUPS = 3
DEFAULT_LIMITS = {
    "maxActiveRuns": 16,
    "maxOpenSessions": 32,
    "maxSessionRecords": 128,
    "maxPendingPrunes": 32,
    "maxConcurrentControlRequests": 16,
    "maxRetainedBytes": 512 * 1024 * 1024,
}
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_NAME_RE = re.compile(
    r"(?:token|secret|password|passwd|api[_-]?key|private[_-]?key|credential|auth)",
    re.IGNORECASE,
)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            raise ConfigurationError(f"{label} 超过 1 MiB")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"{label} 不存在: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"{label} 不可读或 JSON 格式错误: {path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} 必须是 JSON object")
    return value


def _closed_object(
    value: Any,
    label: str,
    *,
    allowed: set[str],
    required: set[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} 必须是 JSON object")
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise ValidationError(f"{label} 包含未知字段: {', '.join(unknown)}")
    if missing:
        raise ValidationError(f"{label} 缺少字段: {', '.join(missing)}")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValidationError(f"{label} 必须是非空字符串且不能包含 NUL")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f"{label} 必须是 {minimum}-{maximum} 范围内整数")
    return value


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} 必须是数字")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValidationError(f"{label} 必须在 {minimum}-{maximum} 范围内")
    return result


def _absolute_path(value: Any, label: str, *, file_only: bool = False, directory_only: bool = False) -> Path:
    path = Path(_string(value, label))
    if not path.is_absolute():
        raise ValidationError(f"{label} 必须是绝对路径")
    resolved = path.resolve()
    if file_only and not resolved.is_file():
        raise ValidationError(f"{label} 必须指向现存文件: {resolved}")
    if directory_only and not resolved.is_dir():
        raise ValidationError(f"{label} 必须指向现存目录: {resolved}")
    return resolved


def _lexical_absolute_path(value: Any, label: str) -> Path:
    path = Path(_string(value, label))
    if not path.is_absolute():
        raise ValidationError(f"{label} 必须是绝对路径")
    return Path(os.path.abspath(path))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _is_lexically_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _string_list(value: Any, label: str, *, max_items: int = 256) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise ValidationError(f"{label} 必须是最多 {max_items} 项的字符串数组")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _string(item, f"{label}[{index}]")
        if len(text.encode("utf-8")) > 32768:
            raise ValidationError(f"{label}[{index}] 过长")
        result.append(text)
    return result


def _digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def default_config_path(workspace: Path | None = None) -> Path:
    root = (workspace or Path.cwd()).resolve()
    return root / ".harness" / "process-manager" / "config.json"


def load_manager_config(path: Path) -> ManagerConfig:
    config_path = path.resolve()
    data = _closed_object(
        _read_json(config_path, "manager config"),
        "manager config",
        allowed={"workspaceRoot", "stateRoot", "control", "history", "limits", "logs"},
        required={"workspaceRoot", "stateRoot", "control", "history", "limits", "logs"},
    )
    workspace = _absolute_path(data["workspaceRoot"], "workspaceRoot", directory_only=True)
    state_root = _lexical_absolute_path(data["stateRoot"], "stateRoot")
    if state_root == workspace or not _is_lexically_within(state_root, workspace):
        raise ValidationError("stateRoot 必须是 workspaceRoot 内的独立目录")
    if not _is_within(config_path, workspace):
        raise ValidationError("manager config 必须位于 workspaceRoot 内")
    control = _closed_object(
        data["control"],
        "control",
        allowed={"host", "port", "maxRequestBytes"},
        required={"host", "port", "maxRequestBytes"},
    )
    host = _string(control["host"], "control.host")
    if host != "127.0.0.1":
        raise ValidationError("control.host 只允许 127.0.0.1")
    history = _closed_object(
        data["history"],
        "history",
        allowed={"maxInactive", "maxAgeSeconds", "maxTombstones", "deleteRunDirs"},
        required={"maxInactive", "maxAgeSeconds", "maxTombstones", "deleteRunDirs"},
    )
    if not isinstance(history["deleteRunDirs"], bool):
        raise ValidationError("history.deleteRunDirs 必须是 boolean")
    raw_limits = _closed_object(
        data["limits"],
        "limits",
        allowed=set(DEFAULT_LIMITS),
        required=set(DEFAULT_LIMITS),
    )
    limits = {
        "maxActiveRuns": _integer(raw_limits["maxActiveRuns"], "limits.maxActiveRuns", 1, 10000),
        "maxOpenSessions": _integer(raw_limits["maxOpenSessions"], "limits.maxOpenSessions", 1, 10000),
        "maxSessionRecords": _integer(
            raw_limits["maxSessionRecords"], "limits.maxSessionRecords", 1, 10000
        ),
        "maxPendingPrunes": _integer(
            raw_limits["maxPendingPrunes"], "limits.maxPendingPrunes", 1, 10000
        ),
        "maxConcurrentControlRequests": _integer(
            raw_limits["maxConcurrentControlRequests"],
            "limits.maxConcurrentControlRequests",
            1,
            1024,
        ),
        "maxRetainedBytes": _integer(
            raw_limits["maxRetainedBytes"], "limits.maxRetainedBytes", 1024 * 1024, 1024**4
        ),
    }
    if limits["maxSessionRecords"] < limits["maxOpenSessions"]:
        raise ValidationError("limits.maxSessionRecords 不能小于 maxOpenSessions")
    logs = _validate_logs(data["logs"], "logs")
    port = _integer(control["port"], "control.port", 0, 65535)
    if port != 0:
        raise ValidationError("control.port 必须为 0，由 OS 分配实际端口")
    return ManagerConfig(
        workspace_root=workspace,
        state_root=state_root,
        host=host,
        port=port,
        max_request_bytes=_integer(control["maxRequestBytes"], "control.maxRequestBytes", 1024, MAX_CONFIG_BYTES),
        history_max_inactive=_integer(history["maxInactive"], "history.maxInactive", 0, 10000),
        history_max_age_seconds=_integer(
            history["maxAgeSeconds"], "history.maxAgeSeconds", 0, 10 * 365 * 24 * 60 * 60
        ),
        history_max_tombstones=_integer(
            history["maxTombstones"], "history.maxTombstones", 1, 10000
        ),
        history_delete_run_dirs=history["deleteRunDirs"],
        limits=limits,
        log_max_bytes=logs["maxBytes"],
        log_backups=logs["backups"],
        config_path=config_path,
    )


def create_default_manager_config(workspace: Path, path: Path | None = None) -> ManagerConfig:
    root = workspace.resolve()
    if not root.is_dir():
        raise ConfigurationError(f"workspace 不存在: {root}")
    state_root = root / ".harness" / "process-manager"
    config_path = (path or state_root / "config.json").resolve()
    value = {
        "workspaceRoot": str(root),
        "stateRoot": str(state_root),
        "control": {
            "host": "127.0.0.1",
            "port": 0,
            "maxRequestBytes": DEFAULT_MAX_REQUEST_BYTES,
        },
        "history": {
            "maxInactive": DEFAULT_HISTORY_MAX_INACTIVE,
            "maxAgeSeconds": DEFAULT_HISTORY_MAX_AGE_SECONDS,
            "maxTombstones": DEFAULT_HISTORY_MAX_TOMBSTONES,
            "deleteRunDirs": True,
        },
        "limits": dict(DEFAULT_LIMITS),
        "logs": {"maxBytes": DEFAULT_LOG_MAX_BYTES, "backups": DEFAULT_LOG_BACKUPS},
    }
    write_capped_json(config_path, value, MAX_CONFIG_BYTES)
    return load_manager_config(config_path)


def _validate_launcher(value: Any) -> dict[str, Any]:
    launcher = _closed_object(
        value,
        "launcher",
        allowed={"type", "executable", "interpreter", "script", "args", "pathArgs"},
        required={"type"},
    )
    launcher_type = _string(launcher["type"], "launcher.type")
    args = _string_list(launcher.get("args", []), "launcher.args")
    path_args = _string_list(launcher.get("pathArgs", []), "launcher.pathArgs", max_items=64)
    normalized_paths = [str(_absolute_path(item, f"launcher.pathArgs[{index}]")) for index, item in enumerate(path_args)]
    if launcher_type == "direct":
        required = {"type", "executable"}
        allowed = required | {"args", "pathArgs"}
        _closed_object(launcher, "launcher", allowed=allowed, required=required)
        return {
            "type": "direct",
            "executable": str(_absolute_path(launcher["executable"], "launcher.executable", file_only=True)),
            "args": args,
            "pathArgs": normalized_paths,
        }
    if launcher_type == "script":
        required = {"type", "interpreter", "script"}
        allowed = required | {"args", "pathArgs"}
        _closed_object(launcher, "launcher", allowed=allowed, required=required)
        return {
            "type": "script",
            "interpreter": str(_absolute_path(launcher["interpreter"], "launcher.interpreter", file_only=True)),
            "script": str(_absolute_path(launcher["script"], "launcher.script", file_only=True)),
            "args": args,
            "pathArgs": normalized_paths,
        }
    raise ValidationError("launcher.type 只允许 direct 或 script")


def _validate_environment(value: Any) -> dict[str, Any]:
    environment = _closed_object(
        value,
        "environment",
        allowed={"inherit", "set", "fromEnv"},
        required={"inherit", "set", "fromEnv"},
    )
    inherit = _string_list(environment["inherit"], "environment.inherit", max_items=256)
    from_env = _string_list(environment["fromEnv"], "environment.fromEnv", max_items=256)
    literal_value = environment["set"]
    if not isinstance(literal_value, dict):
        raise ValidationError("environment.set 必须是 JSON object")
    literal = dict(literal_value)
    for name in [*inherit, *from_env, *literal]:
        if not ENV_NAME_RE.fullmatch(name):
            raise ValidationError(f"环境变量名称不合法: {name}")
    if len(inherit) != len(set(inherit)) or len(from_env) != len(set(from_env)):
        raise ValidationError("environment.inherit/fromEnv 不能包含重复名称")
    overlap = (set(inherit) & set(from_env)) | (set(literal) & set(from_env)) | (set(inherit) & set(literal))
    if overlap:
        raise ValidationError("环境变量来源不能重叠: " + ", ".join(sorted(overlap)))
    for name in inherit:
        if SECRET_NAME_RE.search(name):
            raise ValidationError(f"秘密环境变量必须通过 fromEnv 引用: {name}")
    normalized_set: dict[str, str] = {}
    for name, item in literal.items():
        if SECRET_NAME_RE.search(name):
            raise ValidationError(f"environment.set 禁止 secret-like key: {name}")
        normalized_set[name] = _string(item, f"environment.set.{name}")
    return {"inherit": inherit, "set": normalized_set, "fromEnv": from_env}


def _validate_logs(value: Any, label: str) -> dict[str, int]:
    logs = _closed_object(
        value,
        label,
        allowed={"maxBytes", "backups"},
        required={"maxBytes", "backups"},
    )
    return {
        "maxBytes": _integer(logs["maxBytes"], f"{label}.maxBytes", 65536, 1024 * 1024 * 1024),
        "backups": _integer(logs["backups"], f"{label}.backups", 0, 10),
    }


def _validate_readiness(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    readiness = _closed_object(
        value,
        "readiness",
        allowed={"type", "url", "host", "port", "pattern", "extract", "stream", "stableSeconds", "timeoutSeconds", "scanBytes"},
        required={"type"},
    )
    kind = _string(readiness["type"], "readiness.type")
    result: dict[str, Any] = {"type": kind}
    if "timeoutSeconds" in readiness:
        result["timeoutSeconds"] = _number(readiness["timeoutSeconds"], "readiness.timeoutSeconds", 0.1, 600)
    if kind == "process":
        _closed_object(readiness, "readiness", allowed={"type", "stableSeconds", "timeoutSeconds"}, required={"type"})
        result["stableSeconds"] = _number(readiness.get("stableSeconds", 1), "readiness.stableSeconds", 0.1, 300)
    elif kind == "tcp":
        _closed_object(readiness, "readiness", allowed={"type", "host", "port", "timeoutSeconds"}, required={"type", "host", "port"})
        host = _string(readiness.get("host"), "readiness.host")
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValidationError("readiness.tcp 只允许 loopback host")
        result.update({"host": host, "port": _integer(readiness.get("port"), "readiness.port", 1, 65535)})
    elif kind == "http":
        _closed_object(readiness, "readiness", allowed={"type", "url", "timeoutSeconds"}, required={"type", "url"})
        url = _string(readiness.get("url"), "readiness.url")
        parsed = urllib.parse.urlsplit(url)
        try:
            loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
            parsed.port
        except ValueError:
            loopback = False
        if parsed.scheme not in {"http", "https"} or not loopback or parsed.username or parsed.password or parsed.fragment:
            raise ValidationError("readiness.http 只允许无凭据、无 fragment 的 loopback URL")
        result["url"] = url
    elif kind == "log":
        _closed_object(
            readiness,
            "readiness",
            allowed={"type", "pattern", "extract", "stream", "timeoutSeconds", "scanBytes"},
            required={"type", "pattern"},
        )
        pattern = _string(readiness.get("pattern"), "readiness.pattern")
        if len(pattern) > 1024:
            raise ValidationError("readiness.pattern 不能超过 1024 字符")
        compile_log_pattern(pattern)
        result["pattern"] = pattern
        stream = readiness.get("stream", "stdout")
        if stream not in {"stdout", "stderr"}:
            raise ValidationError("readiness.stream 只允许 stdout 或 stderr")
        result["stream"] = stream
        result["scanBytes"] = _integer(readiness.get("scanBytes", 262144), "readiness.scanBytes", 1024, 1048576)
        extract = readiness.get("extract", {})
        if not isinstance(extract, dict) or len(extract) > 20:
            raise ValidationError("readiness.extract 必须是最多 20 项的 object")
        result["extract"] = {key: _string_list(item, f"readiness.extract.{key}", max_items=20) for key, item in extract.items()}
    else:
        raise ValidationError("readiness.type 只允许 process、tcp、http 或 log")
    return result


def load_service_config(path: Path, manager: ManagerConfig) -> ServiceConfig:
    source_path = path.resolve()
    if not _is_within(source_path, manager.workspace_root):
        raise ValidationError("service config 必须位于 workspaceRoot 内")
    raw = _closed_object(
        _read_json(source_path, "service config"),
        "service config",
        allowed={"name", "kind", "cwd", "launcher", "environment", "stop", "readiness", "logs"},
        required={"name", "kind", "cwd", "launcher"},
    )
    name = _string(raw["name"], "service.name")
    if not SERVICE_NAME_RE.fullmatch(name):
        raise ValidationError("service.name 只能包含字母、数字、点、下划线和短横线")
    if raw["kind"] != "long-running":
        raise ValidationError("service.kind 只允许 long-running")
    cwd = _absolute_path(raw["cwd"], "service.cwd", directory_only=True)
    if not _is_within(cwd, manager.workspace_root):
        raise ValidationError("service.cwd 必须位于 workspaceRoot 内")
    launcher = _validate_launcher(raw["launcher"])
    environment = _validate_environment(raw.get("environment", {"inherit": [], "set": {}, "fromEnv": []}))
    stop = _closed_object(raw.get("stop", {"graceSeconds": 8}), "stop", allowed={"graceSeconds"}, required={"graceSeconds"})
    normalized_stop = {"graceSeconds": _number(stop["graceSeconds"], "stop.graceSeconds", 0, 300)}
    logs = _validate_logs(
        raw.get("logs", {"maxBytes": manager.log_max_bytes, "backups": manager.log_backups}),
        "service.logs",
    )
    return ServiceConfig(
        name=name,
        kind="long-running",
        cwd=cwd,
        launcher=launcher,
        environment=environment,
        stop=normalized_stop,
        readiness=_validate_readiness(raw.get("readiness")),
        logs=logs,
        source_path=source_path,
        config_digest=_digest(raw),
        launcher_digest=_digest(launcher),
    )


def resolve_service_environment(service: ServiceConfig, source: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    current = source if source is not None else os.environ
    result: dict[str, str] = {}
    for name in service.environment["inherit"]:
        if name in current:
            result[name] = str(current[name])
    result.update(service.environment["set"])
    secrets: list[str] = []
    for name in service.environment["fromEnv"]:
        value = current.get(name)
        if value is None or value == "":
            raise ValidationError(f"缺少 fromEnv 环境变量: {name}")
        result[name] = str(value)
        secrets.append(str(value))
    size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    if size > MAX_ENV_BYTES:
        raise ValidationError("解析后的 service environment 超过 64 KiB")
    return result, secrets
