"""在 owner 建立后才释放 target 的内部 service-host。"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import hmac
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .atomic import open_private_binary_append, retry_windows_file_operation
from .errors import ConfigurationError, StateError
from .launch import read_target_identity_message
from .logs import MAX_HOST_STATE_BYTES, write_capped_json
from .runtime import now_text


MAX_SPEC_BYTES = 256 * 1024
MAX_CONTROL_BYTES = 4096
PROCESS_GROUP_SETTLE_SECONDS = 1.0
PROCESS_GROUP_POLL_SECONDS = 0.02
LOG_PUMP_DRAIN_SECONDS = 5.0


def _write_host_state(path: Path, value: dict[str, Any]) -> None:
    write_capped_json(path, value, MAX_HOST_STATE_BYTES)


def _windows_console_supported() -> bool:
    return os.name == "nt"


class WindowsConsole:
    """为 target process group 建立隐藏但可接收 CTRL_BREAK 的专用 console。"""

    def __init__(self) -> None:
        self.allocated = False

    def prepare(self) -> None:
        if not _windows_console_supported():
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_ids = (ctypes.c_ulong * 1)()
        if kernel32.GetConsoleProcessList(process_ids, 1) > 0:
            return
        if not kernel32.AllocConsole():
            raise ConfigurationError(f"AllocConsole 失败，Win32 error={ctypes.get_last_error()}")
        self.allocated = True
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        window = kernel32.GetConsoleWindow()
        if window:
            user32.ShowWindow(window, 0)

    def close(self) -> None:
        if not self.allocated:
            return
        ctypes.WinDLL("kernel32", use_last_error=True).FreeConsole()
        self.allocated = False


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def _read_spec() -> dict[str, Any]:
    line = sys.stdin.readline(MAX_SPEC_BYTES + 1)
    if not line:
        raise ConfigurationError("manager channel 在 launch spec 前关闭")
    if len(line.encode("utf-8")) > MAX_SPEC_BYTES:
        raise ConfigurationError("launch spec 超过 256 KiB")
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("launch spec JSON 无效") from exc
    if not isinstance(value, dict) or value.get("schema") != "process-manager":
        raise ConfigurationError("launch spec schema 无效")
    capability = value.pop("runCapability", None)
    expected_hash = value.get("capabilityHash")
    if not isinstance(capability, str) or not isinstance(expected_hash, str):
        raise ConfigurationError("launch spec 缺少 run capability")
    actual_hash = hashlib.sha256(capability.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise ConfigurationError("launch spec run capability 不匹配")
    return value


def _target_command(launcher: dict[str, Any]) -> list[str]:
    launcher_type = launcher.get("type")
    args = list(launcher.get("args", [])) + list(launcher.get("pathArgs", []))
    if launcher_type == "direct":
        executable = str(launcher["executable"])
        if Path(executable).suffix.lower() in {".cmd", ".bat"}:
            command_interpreter = os.environ.get("ComSpec")
            if not command_interpreter:
                raise ConfigurationError("direct batch launcher 缺少 ComSpec")
            return [command_interpreter, "/d", "/s", "/c", executable, *args]
        return [executable, *args]
    if launcher_type == "script":
        interpreter = str(launcher["interpreter"])
        script = str(launcher["script"])
        name = Path(interpreter).name.lower()
        if name in {"powershell.exe", "pwsh.exe", "pwsh"}:
            return [interpreter, "-NoProfile", "-NonInteractive", "-File", script, *args]
        return [interpreter, script, *args]
    raise ConfigurationError("service-host 收到未知 launcher.type")


class SecretRedactor:
    def __init__(self, values: list[str]) -> None:
        self._secrets = sorted(
            {value.encode("utf-8") for value in values if value},
            key=len,
            reverse=True,
        )
        self._pending = b""

    def _consume(self, data: bytes, *, final: bool) -> tuple[bytes, bytes]:
        if not self._secrets:
            return data, b""
        output = bytearray()
        index = 0
        while index < len(data):
            remainder = data[index:]
            if not final and any(
                len(secret) > len(remainder) and secret.startswith(remainder)
                for secret in self._secrets
            ):
                break
            matched = next((secret for secret in self._secrets if data.startswith(secret, index)), None)
            if matched is not None:
                output.extend(b"***redacted***")
                index += len(matched)
                continue
            output.append(data[index])
            index += 1
        return bytes(output), data[index:]

    def feed(self, data: bytes) -> bytes:
        combined = self._pending + data
        output, self._pending = self._consume(combined, final=False)
        return output

    def finish(self) -> bytes:
        output, self._pending = self._consume(self._pending, final=True)
        return output


class RotatingBinaryLog:
    def __init__(self, path: Path, max_bytes: int, backups: int) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        self._handle = open_private_binary_append(self.path)

    @staticmethod
    def _retry_rotation(operation: Callable[[], object]) -> None:
        retry_windows_file_operation(operation)

    def _rotate(self) -> None:
        self._handle.close()
        try:
            if self.backups > 0:
                oldest = self.path.with_name(f"{self.path.name}.{self.backups}")
                self._retry_rotation(lambda: oldest.unlink(missing_ok=True))
                for index in range(self.backups - 1, 0, -1):
                    source = self.path.with_name(f"{self.path.name}.{index}")
                    if source.exists():
                        target = self.path.with_name(f"{self.path.name}.{index + 1}")
                        self._retry_rotation(lambda source=source, target=target: source.replace(target))
                if self.path.exists():
                    target = self.path.with_name(f"{self.path.name}.1")
                    self._retry_rotation(lambda: self.path.replace(target))
            else:
                self._retry_rotation(lambda: self.path.unlink(missing_ok=True))
        finally:
            self._handle = open_private_binary_append(self.path)

    def write(self, data: bytes) -> None:
        if not data:
            return
        current = self.path.stat().st_size if self.path.exists() else 0
        if current and current + len(data) > self.max_bytes:
            self._rotate()
        if len(data) > self.max_bytes:
            data = data[-self.max_bytes :]
        self._handle.write(data)

    def close(self) -> None:
        self._handle.close()


def _pump(
    source: BinaryIO,
    destination: RotatingBinaryLog,
    secrets: list[str],
    failures: list[dict[str, Any]] | None = None,
    stream: str = "unknown",
) -> None:
    redactor = SecretRedactor(secrets)
    read_available = getattr(source, "read1", source.read)
    try:
        try:
            while True:
                chunk = read_available(4096)
                if not chunk:
                    break
                destination.write(redactor.feed(chunk))
            destination.write(redactor.finish())
        except (OSError, StateError) as exc:
            if failures is not None:
                failures.append(
                    {
                        "stream": stream,
                        "errorType": type(exc).__name__,
                        "errno": getattr(exc, "errno", None),
                        "winerror": getattr(exc, "winerror", None),
                    }
                )
            # 日志落盘失败不能反向关闭目标管道，否则会改变被管理进程的退出行为。
            while read_available(4096):
                pass
    finally:
        source.close()
        destination.close()


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _group_remaining_after_target(
    pgid: int,
    mode: str,
    *,
    timeout: float = PROCESS_GROUP_SETTLE_SECONDS,
    is_alive: Callable[[int], bool] = _group_alive,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    if mode == "windows-job":
        return False
    deadline = monotonic() + max(0.0, timeout)
    while is_alive(pgid):
        remaining = deadline - monotonic()
        if remaining <= 0:
            return True
        sleep(min(PROCESS_GROUP_POLL_SECONDS, remaining))
    return False


def _log_pumps_timed_out(
    pumps: list[threading.Thread],
    *,
    timeout: float = LOG_PUMP_DRAIN_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    deadline = monotonic() + max(0.0, timeout)
    for thread in pumps:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        thread.join(timeout=remaining)
    return any(thread.is_alive() for thread in pumps)


class TargetController:
    def __init__(self, process: subprocess.Popen[bytes], mode: str, owner_control: dict[str, Any]) -> None:
        self.process = process
        self.mode = mode
        self.owner_control = owner_control
        self.pgid = process.pid

    def graceful(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            if self.mode == "windows-job":
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(self.pgid, signal.SIGTERM)
        except (OSError, ValueError):
            return

    def force(self) -> None:
        try:
            if self.mode == "windows-job":
                self.process.kill()
            else:
                os.killpg(self.pgid, signal.SIGKILL)
        except (OSError, ValueError):
            return

    def cleanup_after_manager_loss(self, grace_seconds: float) -> None:
        self.graceful()
        deadline = time.monotonic() + max(0.0, min(grace_seconds, 30.0))
        while time.monotonic() < deadline and self.process.poll() is None:
            time.sleep(0.1)
        if self.process.poll() is None:
            self.force()


def _spawn_target(spec: dict[str, Any]) -> tuple[subprocess.Popen[bytes], str, WindowsConsole]:
    owner_control = spec.get("ownerControl")
    if not isinstance(owner_control, dict):
        raise ConfigurationError("launch spec 缺少 ownerControl")
    mode = str(owner_control.get("mode", ""))
    kwargs: dict[str, Any] = {}
    console = WindowsConsole()
    if mode == "windows-job":
        console.prepare()
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    elif mode in {"process-group", "cgroup-v2"}:
        kwargs["start_new_session"] = True
    else:
        raise ConfigurationError("launch spec owner mode 无效")
    environment = spec.get("environment")
    if not isinstance(environment, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()):
        raise ConfigurationError("launch spec environment 无效")
    try:
        process = subprocess.Popen(
            _target_command(dict(spec.get("launcher", {}))),
            cwd=str(spec["cwd"]),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            **kwargs,
        )
    except Exception:
        console.close()
        raise
    return process, mode, console


def run_host(spec: dict[str, Any], host_state: Path) -> int:
    process, mode, console = _spawn_target(spec)
    owner_control = dict(spec["ownerControl"])
    controller = TargetController(process, mode, owner_control)
    target = {"pid": process.pid, "pgid": process.pid}
    _emit({"event": "target_spawned", "capabilityHash": spec["capabilityHash"], "target": target})
    try:
        target_identity, owner_identity = read_target_identity_message(
            sys.stdin,
            spec,
            target,
            os.getpid(),
        )
    except Exception:
        controller.cleanup_after_manager_loss(float(spec.get("graceSeconds", 8)))
        console.close()
        raise
    logs = dict(spec["logs"])
    secrets = [str(value) for value in spec.get("redactValues", []) if value]
    stdout_log = RotatingBinaryLog(Path(logs["stdout"]), int(logs["maxBytes"]), int(logs["backups"]))
    stderr_log = RotatingBinaryLog(Path(logs["stderr"]), int(logs["maxBytes"]), int(logs["backups"]))
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise ConfigurationError("target log pipe 创建失败")
    pump_failures: list[dict[str, Any]] = []
    pumps = [
        threading.Thread(
            target=_pump,
            args=(process.stdout, stdout_log, secrets, pump_failures, "stdout"),
            daemon=True,
        ),
        threading.Thread(
            target=_pump,
            args=(process.stderr, stderr_log, secrets, pump_failures, "stderr"),
            daemon=True,
        ),
    ]
    for thread in pumps:
        thread.start()
    state = {
        "schema": "process-manager",
        "runId": spec["runId"],
        "managerInstanceId": spec["managerInstanceId"],
        "capabilityHash": spec["capabilityHash"],
        "hostPid": os.getpid(),
        "target": target,
        "targetIdentity": target_identity,
        "ownerIdentity": owner_identity,
        "state": "running",
        "startedAt": now_text(),
    }
    _write_host_state(host_state, state)
    _emit(
        {
            "event": "target_started",
            "capabilityHash": spec["capabilityHash"],
            "target": target,
            "targetIdentity": target_identity,
            "ownerIdentity": owner_identity,
        }
    )

    manager_lost = threading.Event()

    def control_loop() -> None:
        while True:
            line = sys.stdin.readline(MAX_CONTROL_BYTES + 1)
            if not line:
                manager_lost.set()
                controller.cleanup_after_manager_loss(float(spec.get("graceSeconds", 8)))
                return
            if len(line) > MAX_CONTROL_BYTES:
                continue
            try:
                command = json.loads(line).get("command")
            except (json.JSONDecodeError, AttributeError):
                continue
            if command == "graceful_stop":
                controller.graceful()
            elif command == "force_stop":
                controller.force()

    watcher = threading.Thread(target=control_loop, daemon=True)
    watcher.start()
    exit_code = process.wait()
    group_remaining = _group_remaining_after_target(process.pid, mode)
    if group_remaining:
        controller.force()
    log_pump_timeout = _log_pumps_timed_out(pumps)
    state.update(
        {
            "state": (
                "manager_lost"
                if manager_lost.is_set()
                else (
                    "contract_violation"
                    if group_remaining or log_pump_timeout or pump_failures
                    else "exited"
                )
            ),
            "exitCode": exit_code,
            "exitedAt": now_text(),
            "groupRemainingAfterTarget": group_remaining,
            "logPumpTimeout": log_pump_timeout,
            "logPumpFailures": sorted(pump_failures, key=lambda value: str(value.get("stream", ""))),
        }
    )
    _write_host_state(host_state, state)
    _emit({"event": "target_exited", "exitCode": exit_code, "state": state["state"]})
    console.close()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="process-manager internal service host")
    parser.add_argument("--host-state", required=True)
    args = parser.parse_args(argv)
    host_state = Path(args.host_state).resolve()
    _emit({"event": "host_ready", "pid": os.getpid()})
    spec: dict[str, Any] | None = None
    try:
        spec = _read_spec()
        return run_host(spec, host_state)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        for secret in spec.get("redactValues", []) if isinstance(spec, dict) else []:
            if isinstance(secret, str) and secret:
                message = message.replace(secret, "***redacted***")
        _emit({"event": "host_error", "error": {"code": "service_host_error", "message": message[:500]}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
