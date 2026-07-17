"""service-host handshake、launch spec 与失败清理。"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .atomic import read_json_file
from .errors import ConfigurationError, IdentityError, SupervisorError
from .models import ServiceConfig
from .platforms.base import PlatformAdapter, RunOwner


HOST_HANDSHAKE_SECONDS = 10
MAX_HOST_MESSAGE_BYTES = 64 * 1024
MAX_HOST_INPUT_BYTES = 256 * 1024


def read_managed_host_state(run: Any, adapter: PlatformAdapter) -> dict[str, Any] | None:
    """读取并验证内存 run 对应的 host-state。"""

    adapter.validate_runtime_path(run.host_state)
    if not run.host_state.exists():
        return None
    adapter.verify_file(run.host_state)
    value = read_json_file(run.host_state, max_bytes=MAX_HOST_MESSAGE_BYTES)
    if not isinstance(value, dict) or value.get("capabilityHash") != run.capability_hash:
        raise IdentityError("host-state capability identity 不匹配")
    return value


def owned_run(
    runs: dict[str, Any],
    lock: Any,
    record: dict[str, Any],
    instance_id: str,
) -> Any:
    """按 manager instance 与 capability 取得内存 owner。"""

    key = str(record["processKey"])
    with lock:
        run = runs.get(key)
    internal = record.get("internal", {})
    if run is None or internal.get("managerInstanceId") != instance_id:
        raise IdentityError("run owner 不属于当前 manager")
    if internal.get("capabilityHash") != run.capability_hash:
        raise IdentityError("run capability 不匹配")
    return run


def service_host_command(host_state: Path) -> tuple[list[str], dict[str, str]]:
    scripts_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-X",
        "utf8",
        "-B",
        "-m",
        "process_manager.service_host",
        "--host-state",
        str(host_state),
    ]
    environment = {"PYTHONPATH": str(scripts_root), "PYTHONIOENCODING": "utf-8"}
    for name in (
        "SystemRoot",
        "WINDIR",
        "ComSpec",
        "TEMP",
        "TMP",
        "PATH",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
    ):
        if name in os.environ:
            environment[name] = os.environ[name]
    return command, environment


def read_host_message(host: subprocess.Popen[str], timeout: float = HOST_HANDSHAKE_SECONDS) -> dict[str, Any]:
    if host.stdout is None:
        raise SupervisorError("service-host control stdout 不可用")
    result: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

    def read_line() -> None:
        try:
            result.put(host.stdout.readline(MAX_HOST_MESSAGE_BYTES + 1))
        except BaseException as exc:  # noqa: BLE001
            result.put(exc)

    threading.Thread(target=read_line, daemon=True).start()
    try:
        value = result.get(timeout=timeout)
    except queue.Empty as exc:
        raise SupervisorError("service-host handshake 超时") from exc
    if isinstance(value, BaseException):
        raise SupervisorError("service-host handshake 读取失败") from value
    if not value:
        raise SupervisorError("service-host 在 handshake 中退出")
    if len(value.encode("utf-8")) > MAX_HOST_MESSAGE_BYTES:
        raise SupervisorError("service-host message 超过上限")
    try:
        message = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SupervisorError("service-host message JSON 无效") from exc
    if not isinstance(message, dict):
        raise SupervisorError("service-host message 必须是 object")
    if message.get("event") == "host_error":
        error = message.get("error", {})
        raise SupervisorError(str(error.get("message", "service-host failed"))[:500])
    return message


def _write_host_message(host: subprocess.Popen[str], value: dict[str, Any], label: str) -> None:
    if host.stdin is None:
        raise SupervisorError("service-host control stdin 不可用")
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(data.encode("utf-8")) > MAX_HOST_INPUT_BYTES:
        raise SupervisorError(f"service-host {label} 超过上限")
    try:
        host.stdin.write(data)
        host.stdin.flush()
    except (BrokenPipeError, OSError, ValueError) as exc:
        raise SupervisorError(f"service-host {label} 发送失败") from exc


def write_host_spec(host: subprocess.Popen[str], spec: dict[str, Any]) -> None:
    _write_host_message(host, spec, "launch spec")


def read_target_identity_message(
    source: Any,
    spec: dict[str, Any],
    target: dict[str, int],
    host_pid: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    line = source.readline(MAX_HOST_INPUT_BYTES + 1)
    if not line:
        raise ConfigurationError("manager channel 在 target identity 提交前关闭")
    if len(line.encode("utf-8")) > MAX_HOST_INPUT_BYTES:
        raise ConfigurationError("target identity message 超过 256 KiB")
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("target identity message JSON 无效") from exc
    if not isinstance(value, dict) or set(value) != {
        "command",
        "capabilityHash",
        "targetIdentity",
        "ownerIdentity",
    }:
        raise ConfigurationError("target identity message schema 无效")
    target_identity = value["targetIdentity"]
    owner_identity = value["ownerIdentity"]
    if (
        value["command"] != "target_identity"
        or value["capabilityHash"] != spec["capabilityHash"]
        or not isinstance(target_identity, dict)
        or target_identity.get("pid") != target["pid"]
        or not isinstance(owner_identity, dict)
        or owner_identity.get("capabilityHash") != spec["capabilityHash"]
        or owner_identity.get("hostPid") != host_pid
    ):
        raise ConfigurationError("target identity message 与当前 owner 不匹配")
    return dict(target_identity), dict(owner_identity)


def build_host_spec(
    instance_id: str,
    service: ServiceConfig,
    record: dict[str, Any],
    owner: RunOwner,
    capability: str,
    capability_hash: str,
    environment: dict[str, str],
    secrets_to_redact: list[str],
) -> dict[str, Any]:
    run_dir = Path(record["runDir"])
    return {
        "schema": "process-manager",
        "runId": record["processId"],
        "managerInstanceId": instance_id,
        "runCapability": capability,
        "capabilityHash": capability_hash,
        "cwd": str(service.cwd),
        "launcher": service.launcher,
        "environment": environment,
        "redactValues": secrets_to_redact,
        "graceSeconds": service.stop["graceSeconds"],
        "ownerControl": owner.control_data,
        "logs": {
            "stdout": str(run_dir / "stdout.log"),
            "stderr": str(run_dir / "stderr.log"),
            "maxBytes": service.logs["maxBytes"],
            "backups": service.logs["backups"],
        },
    }


def cleanup_failed_start(owner: RunOwner | None, host: subprocess.Popen[str] | None) -> list[str]:
    failures: list[str] = []
    if owner is not None:
        try:
            forced = owner.force_stop()
            if not forced and not owner.is_empty():
                failures.append("owner force stop 未确认")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"owner force stop: {type(exc).__name__}")
        try:
            owner.close()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"owner close: {type(exc).__name__}")
        return failures
    if host is None or host.poll() is not None:
        return failures
    try:
        host.kill()
        host.wait(timeout=5)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"service-host cleanup: {type(exc).__name__}")
    return failures


def validate_target_handshake(
    adapter: PlatformAdapter,
    owner: RunOwner,
    host: subprocess.Popen[str],
    capability_hash: str,
) -> dict[str, Any]:
    spawned = read_host_message(host)
    if spawned.get("event") != "target_spawned" or spawned.get("capabilityHash") != capability_hash:
        raise IdentityError("service-host target spawn handshake 不匹配")
    target = spawned.get("target")
    if not isinstance(target, dict):
        raise IdentityError("service-host target identity 缺失")
    owner.bind_target(target)
    target_identity = adapter.process_identity(int(target["pid"]))
    owner_identity = owner.internal_identity()
    _write_host_message(
        host,
        {
            "command": "target_identity",
            "capabilityHash": capability_hash,
            "targetIdentity": target_identity,
            "ownerIdentity": owner_identity,
        },
        "target identity",
    )
    started = read_host_message(host)
    if (
        started.get("event") != "target_started"
        or started.get("capabilityHash") != capability_hash
        or started.get("target") != target
        or started.get("targetIdentity") != target_identity
        or started.get("ownerIdentity") != owner_identity
    ):
        raise IdentityError("service-host target identity commit 不匹配")
    return {
        "target": target,
        "hostIdentity": adapter.process_identity(host.pid),
        "targetIdentity": target_identity,
        "ownerIdentity": owner_identity,
    }
