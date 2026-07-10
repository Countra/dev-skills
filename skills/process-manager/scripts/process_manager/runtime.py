"""runtime layout、token 与 manager identity。"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic import atomic_write_bytes, atomic_write_json, read_json_file
from .errors import IdentityError, ManagerOfflineError, RuntimeRebuildRequiredError, StateError
from .models import ManagerConfig
from .platforms.base import PlatformAdapter


TOKEN_BYTES = 32
MAX_IDENTITY_BYTES = 64 * 1024
MANAGER_IDENTITY_KEYS = {
    "schema",
    "instanceId",
    "pid",
    "platform",
    "bootstrapBackend",
    "bootstrapSelectionReason",
    "supervisorBackend",
    "capability",
    "selectionReason",
    "identity",
    "host",
    "port",
    "startedAt",
    "configSha256",
}


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_digest(config: ManagerConfig) -> str:
    data = json.dumps(config.public_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def initialize_runtime(config: ManagerConfig, adapter: PlatformAdapter) -> None:
    paths = config.paths
    if (paths.state_root / "manager.pid").exists():
        raise RuntimeRebuildRequiredError("检测到旧 manager.pid；请使用新的隔离 stateRoot 或显式重建 runtime")
    adapter.secure_directory(paths.state_root)
    for directory in (paths.services, paths.runs, paths.logs, paths.tmp):
        adapter.secure_directory(directory)
    adapter.secure_file(config.config_path)
    if not paths.token.exists():
        atomic_write_bytes(paths.token, (secrets.token_urlsafe(TOKEN_BYTES) + "\n").encode("ascii"))
    adapter.secure_file(paths.token)


def read_token(config: ManagerConfig, adapter: PlatformAdapter) -> str:
    path = config.paths.token
    adapter.verify_file(path)
    try:
        if path.stat().st_size > 4096:
            raise StateError("runtime token 文件超过上限")
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise StateError("runtime token 不可读") from exc
    if len(token) < 32:
        raise StateError("runtime token 无效")
    return token


def build_manager_identity(
    config: ManagerConfig,
    adapter: PlatformAdapter,
    *,
    instance_id: str,
    port: int,
    bootstrap_backend: str,
    bootstrap_selection_reason: str,
) -> dict[str, Any]:
    return {
        "schema": "process-manager",
        "instanceId": instance_id,
        "pid": os.getpid(),
        "platform": adapter.selection.platform,
        "bootstrapBackend": bootstrap_backend,
        "bootstrapSelectionReason": bootstrap_selection_reason,
        "supervisorBackend": adapter.selection.backend,
        "capability": adapter.selection.capability,
        "selectionReason": adapter.selection.selection_reason,
        "identity": adapter.process_identity(os.getpid()),
        "host": config.host,
        "port": port,
        "startedAt": now_text(),
        "configSha256": config_digest(config),
    }


def write_manager_identity(config: ManagerConfig, adapter: PlatformAdapter, identity: dict[str, Any]) -> None:
    atomic_write_json(config.paths.manager, identity)
    adapter.secure_file(config.paths.manager)


def read_manager_identity(config: ManagerConfig, adapter: PlatformAdapter) -> dict[str, Any]:
    path = config.paths.manager
    if not path.exists():
        raise ManagerOfflineError("manager identity 不存在")
    adapter.verify_file(path)
    value = read_json_file(path, max_bytes=MAX_IDENTITY_BYTES)
    if not isinstance(value, dict) or value.get("schema") != "process-manager":
        raise RuntimeRebuildRequiredError("manager identity 使用旧或未知 runtime schema")
    if set(value) != MANAGER_IDENTITY_KEYS:
        raise IdentityError("manager identity 字段集合无效")
    string_fields = (
        "instanceId",
        "platform",
        "bootstrapBackend",
        "bootstrapSelectionReason",
        "supervisorBackend",
        "capability",
        "selectionReason",
        "startedAt",
        "configSha256",
    )
    if any(not isinstance(value.get(name), str) or not value[name] for name in string_fields):
        raise IdentityError("manager identity 字符串字段无效")
    if value.get("platform") != adapter.selection.platform:
        raise IdentityError("manager identity 平台与当前运行环境不匹配")
    if value.get("host") != config.host or value.get("configSha256") != config_digest(config):
        raise IdentityError("manager identity 与当前 config 不匹配")
    port = value.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise IdentityError("manager identity control port 无效")
    identity = value.get("identity")
    pid = value.get("pid")
    if (
        isinstance(pid, bool)
        or not isinstance(pid, int)
        or not isinstance(identity, dict)
        or identity.get("pid") != pid
        or not adapter.identity_matches(identity)
    ):
        raise IdentityError("manager 进程身份不可验证")
    return value


def remove_manager_identity(config: ManagerConfig, instance_id: str) -> None:
    path = config.paths.manager
    if not path.exists():
        return
    try:
        current = read_json_file(path, max_bytes=MAX_IDENTITY_BYTES)
    except StateError:
        return
    if isinstance(current, dict) and current.get("instanceId") == instance_id:
        try:
            path.unlink()
        except FileNotFoundError:
            return
