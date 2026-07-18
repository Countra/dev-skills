"""runtime layout、token 与 manager identity。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .atomic import atomic_write_bytes, read_json_file
from .errors import (
    IdentityError,
    ManagerAbsentError,
    RuntimeCorruptError,
    RuntimeRebuildRequiredError,
    StateError,
)
from .models import ManagerConfig
from .logs import write_capped_json
from .platforms.base import PlatformAdapter


TOKEN_BYTES = 32
MAX_IDENTITY_BYTES = 64 * 1024
MAX_OPERATION_BYTES = 64 * 1024
MAX_MANAGER_OPERATION_TIMEOUT_SECONDS = 3600.0
OPERATION_KINDS = {"ensure", "restart", "stop"}
OPERATION_STATES = {"pending", "succeeded", "failed"}
OPERATION_CHECKPOINTS = {
    "ensure": frozenset(
        "start-requested runtime-verified bootstrap-launched identity-published endpoint-ready".split()
    ),
    "stop": frozenset(
        "stop-requested intake-closed runs-terminating owners-empty manager-stopped bootstrap-cleaned".split()
    ),
    "restart": frozenset(
        "restart-requested intake-closed runs-terminating owners-empty manager-stopped bootstrap-cleaned "
        "runtime-verified bootstrap-launched identity-published endpoint-ready".split()
    ),
}
OPERATION_SUCCESS_CHECKPOINTS = {
    "ensure": "endpoint-ready",
    "stop": "bootstrap-cleaned",
    "restart": "endpoint-ready",
}
OPERATION_KEYS = frozenset(
    "schema operationId kind state checkpoint workspaceDigest configDigest expectedInstanceId replacementInstanceId "
    "expectedRuntimeFingerprint expectedWorkGeneration startedAt updatedAt deadlineAt outcome error".split()
)
MANAGER_IDENTITY_KEYS = {
    "schema",
    "operationId",
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
    "runtimeFingerprint",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def prepare_runtime_lock(path: Path, adapter: PlatformAdapter) -> None:
    """以排他创建和平台校验准备可安全打开的 runtime lock。"""

    adapter.secure_directory(path.parent)
    path = adapter.validate_runtime_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags, 0o600)
        os.write(descriptor, b"\0")
        os.fsync(descriptor)
    except FileExistsError:
        pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    adapter.secure_file(path)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_digest(config: ManagerConfig) -> str:
    data = json.dumps(config.public_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_operation_timeout(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
        or value > MAX_MANAGER_OPERATION_TIMEOUT_SECONDS
    ):
        raise ValueError(
            f"manager operation timeout 必须在 (0, {MAX_MANAGER_OPERATION_TIMEOUT_SECONDS:g}] 秒内"
        )
    return float(value)


def _parse_operation_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise RuntimeCorruptError(f"manager operation {label} 无效")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeCorruptError(f"manager operation {label} 无效") from exc
    if parsed.tzinfo is None:
        raise RuntimeCorruptError(f"manager operation {label} 缺少时区")
    return parsed.astimezone(timezone.utc)


class OperationStore:
    """持久化并校验 workspace 绑定的 manager operation receipt。"""

    def __init__(
        self,
        config: ManagerConfig,
        adapter: PlatformAdapter,
        *,
        workspace_digest: str,
        expected_config_digest: str,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.workspace_digest = workspace_digest
        self.expected_config_digest = expected_config_digest

    def read(self) -> dict[str, Any] | None:
        path = self.config.paths.operation
        self.adapter.validate_runtime_path(path)
        if not path.exists():
            return None
        self.adapter.verify_file(path)
        value = read_json_file(path, max_bytes=MAX_OPERATION_BYTES)
        self._validate(value)
        return value

    def prepare_lock(self) -> None:
        prepare_runtime_lock(self.config.paths.operation_lock, self.adapter)

    def _validate(self, value: Any) -> None:
        if not isinstance(value, dict) or set(value) != OPERATION_KEYS:
            raise RuntimeCorruptError("manager operation 字段集合无效")
        if value.get("schema") != "process-manager-operation":
            raise RuntimeCorruptError("manager operation schema 无效")
        kind = value.get("kind")
        state = value.get("state")
        if kind not in OPERATION_KINDS or state not in OPERATION_STATES:
            raise RuntimeCorruptError("manager operation kind/state 无效")
        required_strings = (
            "operationId",
            "checkpoint",
            "workspaceDigest",
            "startedAt",
            "updatedAt",
            "deadlineAt",
        )
        if any(not isinstance(value.get(key), str) or not value[key] for key in required_strings):
            raise RuntimeCorruptError("manager operation 必填字符串字段无效")
        try:
            canonical_operation_id = uuid.UUID(value["operationId"]).hex
        except (ValueError, AttributeError) as exc:
            raise RuntimeCorruptError("manager operation operationId 无效") from exc
        if value["operationId"] != canonical_operation_id:
            raise RuntimeCorruptError("manager operation operationId 不是 canonical UUID")
        if value["checkpoint"] not in OPERATION_CHECKPOINTS[kind]:
            raise RuntimeCorruptError("manager operation checkpoint 无效")
        if value["workspaceDigest"] != self.workspace_digest:
            raise RuntimeCorruptError("manager operation workspace identity 不匹配")
        if value.get("configDigest") != self.expected_config_digest:
            raise RuntimeCorruptError("manager operation config identity 不匹配")
        expected = value.get("expectedInstanceId")
        if expected is not None and (not isinstance(expected, str) or not expected):
            raise RuntimeCorruptError("manager operation expectedInstanceId 无效")
        replacement = value.get("replacementInstanceId")
        if replacement is not None and (not isinstance(replacement, str) or not replacement):
            raise RuntimeCorruptError("manager operation replacementInstanceId 无效")
        if kind != "restart" and replacement is not None:
            raise RuntimeCorruptError("非 restart operation 不得包含 replacementInstanceId")
        fingerprint = value.get("expectedRuntimeFingerprint")
        generation = value.get("expectedWorkGeneration")
        if kind in {"ensure", "restart"}:
            if not isinstance(fingerprint, str) or SHA256_RE.fullmatch(fingerprint) is None:
                raise RuntimeCorruptError("manager operation expectedRuntimeFingerprint 无效")
        elif fingerprint is not None:
            raise RuntimeCorruptError("stop operation 不得包含 runtime fingerprint")
        if kind in {"stop", "restart"}:
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
                raise RuntimeCorruptError("destructive operation expectedWorkGeneration 无效")
        elif generation is not None:
            raise RuntimeCorruptError("ensure operation 不得包含 work generation")
        if value.get("outcome") is not None and not isinstance(value["outcome"], dict):
            raise RuntimeCorruptError("manager operation outcome 无效")
        if value.get("error") is not None and not isinstance(value["error"], dict):
            raise RuntimeCorruptError("manager operation error 无效")
        if state == "pending" and (value.get("outcome") is not None or value.get("error") is not None):
            raise RuntimeCorruptError("pending manager operation 不得包含终态结果")
        if state == "succeeded" and (
            not isinstance(value.get("outcome"), dict)
            or value.get("error") is not None
            or value["checkpoint"] != OPERATION_SUCCESS_CHECKPOINTS[kind]
        ):
            raise RuntimeCorruptError("succeeded manager operation 终态结果无效")
        if state == "failed" and (
            not isinstance(value.get("error"), dict) or value.get("outcome") is not None
        ):
            raise RuntimeCorruptError("failed manager operation 终态结果无效")
        started = _parse_operation_time(value["startedAt"], "startedAt")
        updated = _parse_operation_time(value["updatedAt"], "updatedAt")
        deadline = _parse_operation_time(value["deadlineAt"], "deadlineAt")
        if updated < started or deadline <= started:
            raise RuntimeCorruptError("manager operation 时间顺序无效")

    def create(
        self,
        kind: str,
        *,
        timeout: float,
        expected_runtime_fingerprint: str | None,
        expected_work_generation: int | None,
    ) -> dict[str, Any]:
        if kind not in OPERATION_KINDS:
            raise ValueError(f"未知 manager operation: {kind}")
        timeout = validate_operation_timeout(timeout)
        now = datetime.now(timezone.utc)
        checkpoint = "start-requested" if kind == "ensure" else f"{kind}-requested"
        return {
            "schema": "process-manager-operation",
            "operationId": uuid.uuid4().hex,
            "kind": kind,
            "state": "pending",
            "checkpoint": checkpoint,
            "workspaceDigest": self.workspace_digest,
            "configDigest": self.expected_config_digest,
            "expectedInstanceId": None,
            "replacementInstanceId": None,
            "expectedRuntimeFingerprint": expected_runtime_fingerprint,
            "expectedWorkGeneration": expected_work_generation,
            "startedAt": now.isoformat(),
            "updatedAt": now.isoformat(),
            "deadlineAt": (now + timedelta(seconds=timeout)).isoformat(),
            "outcome": None,
            "error": None,
        }

    def write(self, operation: dict[str, Any]) -> None:
        self._validate(operation)
        write_capped_json(self.config.paths.operation, operation, MAX_OPERATION_BYTES)
        self.adapter.secure_file(self.config.paths.operation)

    def update(self, operation: dict[str, Any], **changes: Any) -> dict[str, Any]:
        if operation["state"] != "pending":
            raise RuntimeCorruptError("terminal manager operation 不可继续修改")
        next_checkpoint = changes.get("checkpoint", operation["checkpoint"])
        checkpoints = tuple(OPERATION_CHECKPOINTS[operation["kind"]])
        if next_checkpoint != operation["checkpoint"]:
            ordered = {
                "ensure": (
                    "start-requested",
                    "runtime-verified",
                    "bootstrap-launched",
                    "identity-published",
                    "endpoint-ready",
                ),
                "stop": (
                    "stop-requested",
                    "intake-closed",
                    "runs-terminating",
                    "owners-empty",
                    "manager-stopped",
                    "bootstrap-cleaned",
                ),
                "restart": (
                    "restart-requested",
                    "intake-closed",
                    "runs-terminating",
                    "owners-empty",
                    "manager-stopped",
                    "bootstrap-cleaned",
                    "runtime-verified",
                    "bootstrap-launched",
                    "identity-published",
                    "endpoint-ready",
                ),
            }[operation["kind"]]
            if next_checkpoint not in checkpoints or ordered.index(next_checkpoint) < ordered.index(operation["checkpoint"]):
                raise RuntimeCorruptError("manager operation checkpoint 不得倒退")
        value = {**operation, **changes, "updatedAt": now_text()}
        self.write(value)
        return value

    def complete_ensure(self, operation: dict[str, Any], instance_id: str) -> dict[str, Any]:
        if operation["kind"] != "ensure" or operation["state"] != "pending" or not instance_id:
            raise RuntimeCorruptError("无法用当前 manager 完成 pending ensure")
        expected_instance = operation.get("expectedInstanceId")
        if expected_instance is not None and expected_instance != instance_id:
            raise RuntimeCorruptError("pending ensure 与当前 manager instance 不匹配")
        operation = self.update(
            operation,
            checkpoint="endpoint-ready",
            expectedInstanceId=instance_id,
        )
        outcome = {
            "state": "ready",
            "changed": True,
            "managerInstanceId": instance_id,
        }
        return self.update(operation, state="succeeded", outcome=outcome)

    @staticmethod
    def expired(operation: dict[str, Any]) -> bool:
        return _parse_operation_time(operation["deadlineAt"], "deadlineAt") <= datetime.now(timezone.utc)

    @staticmethod
    def public_summary(operation: dict[str, Any] | None) -> dict[str, Any] | None:
        if operation is None:
            return None
        return {
            "operationId": operation["operationId"],
            "kind": operation["kind"],
            "state": operation["state"],
            "checkpoint": operation["checkpoint"],
            "deadlineAt": operation["deadlineAt"],
        }


def initialize_runtime(config: ManagerConfig, adapter: PlatformAdapter) -> None:
    paths = config.paths
    legacy_pid = adapter.validate_runtime_path(paths.state_root / "manager.pid")
    if legacy_pid.exists():
        raise RuntimeRebuildRequiredError("检测到旧 manager.pid；请使用新的隔离 stateRoot 或显式重建 runtime")
    adapter.secure_directory(paths.state_root)
    for directory in (paths.control, paths.services, paths.runs, paths.logs, paths.tmp):
        adapter.secure_directory(directory)
    adapter.secure_file(config.config_path)
    token_path = adapter.validate_runtime_path(paths.token)
    if not token_path.exists():
        atomic_write_bytes(token_path, (secrets.token_urlsafe(TOKEN_BYTES) + "\n").encode("ascii"))
    adapter.secure_file(token_path)


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
    operation_id: str,
    instance_id: str,
    port: int,
    bootstrap_backend: str,
    bootstrap_selection_reason: str,
    runtime_fingerprint: str,
) -> dict[str, Any]:
    try:
        canonical_operation_id = uuid.UUID(operation_id).hex
    except (ValueError, AttributeError) as exc:
        raise IdentityError("manager parent operationId 无效") from exc
    if operation_id != canonical_operation_id:
        raise IdentityError("manager parent operationId 不是 canonical UUID")
    if SHA256_RE.fullmatch(runtime_fingerprint) is None:
        raise IdentityError("manager runtime fingerprint 无效")
    return {
        "schema": "process-manager",
        "operationId": operation_id,
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
        "runtimeFingerprint": runtime_fingerprint,
    }


def write_manager_identity(config: ManagerConfig, adapter: PlatformAdapter, identity: dict[str, Any]) -> None:
    path = adapter.validate_runtime_path(config.paths.manager)
    write_capped_json(path, identity, MAX_IDENTITY_BYTES)
    adapter.secure_file(path)


def read_manager_identity_record(config: ManagerConfig, adapter: PlatformAdapter) -> dict[str, Any]:
    path = adapter.validate_runtime_path(config.paths.manager)
    if not path.exists():
        raise ManagerAbsentError("manager identity 不存在", recommended_action="ensure")
    adapter.verify_file(path)
    value = read_json_file(path, max_bytes=MAX_IDENTITY_BYTES)
    if not isinstance(value, dict) or value.get("schema") != "process-manager":
        raise RuntimeRebuildRequiredError("manager identity 使用旧或未知 runtime schema")
    if set(value) != MANAGER_IDENTITY_KEYS:
        raise IdentityError("manager identity 字段集合无效")
    string_fields = (
        "operationId",
        "instanceId",
        "platform",
        "bootstrapBackend",
        "bootstrapSelectionReason",
        "supervisorBackend",
        "capability",
        "selectionReason",
        "startedAt",
        "configSha256",
        "runtimeFingerprint",
    )
    if any(not isinstance(value.get(name), str) or not value[name] for name in string_fields):
        raise IdentityError("manager identity 字符串字段无效")
    try:
        canonical_operation_id = uuid.UUID(value["operationId"]).hex
    except (ValueError, AttributeError) as exc:
        raise IdentityError("manager identity operationId 无效") from exc
    if value["operationId"] != canonical_operation_id:
        raise IdentityError("manager identity operationId 不是 canonical UUID")
    if value.get("platform") != adapter.selection.platform:
        raise IdentityError("manager identity 平台与当前运行环境不匹配")
    if value.get("host") != config.host or value.get("configSha256") != config_digest(config):
        raise IdentityError("manager identity 与当前 config 不匹配")
    if SHA256_RE.fullmatch(value["runtimeFingerprint"]) is None:
        raise IdentityError("manager identity runtime fingerprint 无效")
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
    ):
        raise IdentityError("manager 进程身份字段无效")
    return value


def read_manager_identity(config: ManagerConfig, adapter: PlatformAdapter) -> dict[str, Any]:
    value = read_manager_identity_record(config, adapter)
    if not adapter.identity_matches(value["identity"]):
        raise IdentityError("manager 进程身份不可验证")
    return value


def remove_manager_identity(config: ManagerConfig, adapter: PlatformAdapter, instance_id: str) -> None:
    path = adapter.validate_runtime_path(config.paths.manager)
    if not path.exists():
        return
    try:
        adapter.verify_file(path)
        current = read_json_file(path, max_bytes=MAX_IDENTITY_BYTES)
    except StateError:
        return
    if isinstance(current, dict) and current.get("instanceId") == instance_id:
        try:
            adapter.verify_file(path)
            path.unlink()
        except FileNotFoundError:
            return
