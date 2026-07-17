"""在既有 operation receipt 下启动并验证 manager。"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .bootstrap import (
    BootstrapResult,
    ManagerBootstrap,
)
from .errors import (
    ConflictError,
    IdentityError,
    ManagerUnresponsiveError,
    OperationTimeoutError,
    PMError,
    RuntimeCorruptError,
    SupervisorError,
)
from .models import ManagerConfig
from .platforms.base import PlatformAdapter
from .runtime import OperationStore, initialize_runtime, read_manager_identity_record
from .runtime_fingerprint import compute_runtime_fingerprint


def cleanup_bootstrap_result(
    bootstrap: ManagerBootstrap,
    result: BootstrapResult,
    *,
    timeout: float = 5.0,
) -> bool:
    """有界回收本次 bootstrap 可证明拥有的进程与 native backend。"""
    process = result.process
    try:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=timeout)
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=timeout)
        if process is not None and process.poll() is None:
            return False
        return bootstrap.cleanup_residue(timeout=timeout, preferred_backend=result.backend)
    except (OSError, subprocess.SubprocessError):
        return False


class StartDrainGate:
    """线性化 service start 接纳，并为 manager shutdown 提供有界排空。"""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._accepting = False
        self._in_flight = 0

    def open(self) -> None:
        with self._condition:
            self._accepting = True

    def close(self) -> None:
        with self._condition:
            self._accepting = False

    @contextmanager
    def admit(self) -> Iterator[None]:
        with self._condition:
            if not self._accepting:
                raise ConflictError("manager 正在关闭，不再接受新 start")
            self._in_flight += 1
        try:
            yield
        finally:
            with self._condition:
                self._in_flight -= 1
                self._condition.notify_all()

    def wait_for_drain(self, deadline: float) -> None:
        with self._condition:
            while self._in_flight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SupervisorError(
                        "manager shutdown 等待已接纳 start 超时",
                        diagnostics={"startsInFlight": self._in_flight},
                    )
                self._condition.wait(timeout=remaining)


def manager_command(
    manager_script: Path,
    config_path: Path,
    backend: str,
    reason: str,
    *,
    operation_id: str,
    runtime_fingerprint: str,
) -> list[str]:
    return [
        sys.executable,
        "-X",
        "utf8",
        "-B",
        str(manager_script),
        "--config",
        str(config_path),
        "--bootstrap-backend",
        backend,
        "--bootstrap-reason",
        reason,
        "--operation-id",
        operation_id,
        "--runtime-fingerprint",
        runtime_fingerprint,
    ]


class ManagerStartCoordinator:
    """恢复或推进单个 ensure/restart 的 start phase。"""

    def __init__(
        self,
        config: ManagerConfig,
        adapter: PlatformAdapter,
        store: OperationStore,
        *,
        bootstrap_factory: Callable[[ManagerConfig, PlatformAdapter], ManagerBootstrap],
        manager_script: Path,
        resolver: Callable[..., Any],
        state_error: Callable[[Any], PMError],
        fingerprint_factory: Callable[[], str] = compute_runtime_fingerprint,
        sleeper: Callable[[float], None],
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.store = store
        self.bootstrap_factory = bootstrap_factory
        self.manager_script = manager_script
        self.resolver = resolver
        self.state_error = state_error
        self.fingerprint_factory = fingerprint_factory
        self.sleeper = sleeper

    @staticmethod
    def _remaining(deadline: float) -> float:
        return max(0.0, deadline - time.monotonic())

    def _rotate(self, path: Path, max_bytes: int, backups: int) -> None:
        path = self.adapter.validate_runtime_path(path)
        if not path.exists():
            return
        self.adapter.verify_file(path)
        if path.stat().st_size < max_bytes:
            return
        if backups <= 0:
            path.unlink()
            return
        rotated = [path.with_name(f"{path.name}.{index}") for index in range(1, backups + 1)]
        for candidate in rotated:
            self.adapter.validate_runtime_path(candidate)
            if candidate.exists():
                self.adapter.verify_file(candidate)
        rotated[-1].unlink(missing_ok=True)
        for index in range(backups - 1, 0, -1):
            source = rotated[index - 1]
            if source.exists():
                source.replace(rotated[index])
        path.replace(rotated[0])

    def _assert_runtime_contract(self, operation: dict[str, Any]) -> str:
        expected = operation.get("expectedRuntimeFingerprint")
        if not isinstance(expected, str):
            raise RuntimeCorruptError("manager start operation 缺少 runtime fingerprint")
        current = self.fingerprint_factory()
        if current != expected:
            raise RuntimeCorruptError(
                "manager runtime contract 在 operation 期间发生变化",
                diagnostics={
                    "operationId": operation["operationId"],
                    "expectedRuntimeFingerprint": expected,
                    "currentRuntimeFingerprint": current,
                },
                recommended_action="restart",
            )
        return current

    def _wait_existing(
        self,
        operation: dict[str, Any],
        *,
        deadline: float,
    ) -> tuple[dict[str, Any], Any]:
        last_state = None
        while self._remaining(deadline) > 0:
            self._assert_runtime_contract(operation)
            last_state = self.resolver(reconcile_operation_id=str(operation["operationId"]))
            if last_state.state == "ready":
                return operation, last_state
            if last_state.state != "starting":
                raise self.state_error(last_state)
            self.sleeper(min(0.1, self._remaining(deadline)))
        raise OperationTimeoutError(
            "等待既有 manager bootstrap 超时",
            diagnostics={
                "lastState": getattr(last_state, "state", "starting"),
                "operation": self.store.public_summary(operation),
            },
            recommended_action="status",
        )

    def recover(
        self,
        operation: dict[str, Any],
        *,
        timeout: float,
        deadline: float,
        release_terminal_fence: Callable[[], int] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """恢复可证明已放弃的 start receipt，必要时创建新期望。"""

        current_fingerprint = self.fingerprint_factory()
        fingerprint_changed = operation["expectedRuntimeFingerprint"] != current_fingerprint
        manager_path = self.adapter.validate_runtime_path(self.config.paths.manager)
        manager_present = manager_path.exists()
        safe_checkpoint = (
            operation["kind"] == "ensure" and operation["checkpoint"] == "start-requested"
            or operation["kind"] == "restart" and operation["checkpoint"] == "bootstrap-cleaned"
        )
        if safe_checkpoint and not fingerprint_changed and not manager_present:
            if self.store.expired(operation):
                operation = self.store.update(
                    operation,
                    deadlineAt=(datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat(),
                )
            return operation, True
        if not fingerprint_changed and not self.store.expired(operation):
            return operation, False
        bootstrap = self.bootstrap_factory(self.config, self.adapter)
        if manager_present:
            identity = read_manager_identity_record(self.config, self.adapter)
            if identity["operationId"] != operation["operationId"]:
                raise IdentityError("abandoned start manager 与 receipt operation 不匹配")
            if identity["runtimeFingerprint"] != operation["expectedRuntimeFingerprint"]:
                raise IdentityError("abandoned start manager identity 与 receipt 不匹配")
            expected_instance = operation.get("expectedInstanceId")
            replacement_instance = operation.get("replacementInstanceId")
            if operation["kind"] == "restart" and replacement_instance is None:
                replacement_instance = identity["instanceId"]
                operation = self.store.update(
                    operation,
                    replacementInstanceId=replacement_instance,
                )
            identity_expected = (
                replacement_instance
                if operation["kind"] == "restart"
                else expected_instance
            )
            if identity_expected is not None and identity["instanceId"] != identity_expected:
                raise IdentityError("abandoned start manager instance 与 receipt 不匹配")
            bootstrap.stop_manager(
                identity,
                request_shutdown=None,
                allow_terminate=True,
                timeout=self._remaining(deadline),
            )
        if not bootstrap.cleanup_residue(timeout=self._remaining(deadline)):
            raise ManagerUnresponsiveError(
                "abandoned manager bootstrap 清理未验证",
                recommended_action="doctor",
            )
        code = "runtime_contract_changed" if fingerprint_changed else "operation_timeout"
        self.store.update(
            operation,
            state="failed",
            error={
                "code": code,
                "message": "abandoned start receipt 已由 exact cleanup 收口",
                "cleanupVerified": True,
            },
        )
        generation = release_terminal_fence() if release_terminal_fence is not None else None
        replacement = self.store.create(
            str(operation["kind"]),
            timeout=timeout,
            expected_runtime_fingerprint=current_fingerprint,
            expected_work_generation=generation,
        )
        if operation["kind"] == "restart":
            replacement["expectedInstanceId"] = operation.get("expectedInstanceId")
        self.store.write(replacement)
        return replacement, True

    def run(
        self,
        operation: dict[str, Any],
        *,
        deadline: float,
        launch_authorized: bool,
    ) -> tuple[dict[str, Any], Any]:
        current = self.resolver(reconcile_operation_id=str(operation["operationId"]))
        if current.state == "ready":
            return operation, current
        if not launch_authorized or operation["checkpoint"] in {
            "bootstrap-launched",
            "identity-published",
        }:
            return self._wait_existing(operation, deadline=deadline)
        launched: BootstrapResult | None = None
        bootstrap: ManagerBootstrap | None = None
        try:
            runtime_fingerprint = self._assert_runtime_contract(operation)
            initialize_runtime(self.config, self.adapter)
            operation = self.store.update(operation, checkpoint="runtime-verified")
            stdout_path = self.config.paths.logs / "manager-stdout.log"
            stderr_path = self.config.paths.logs / "manager-stderr.log"
            self._rotate(stdout_path, self.config.log_max_bytes, self.config.log_backups)
            self._rotate(stderr_path, self.config.log_max_bytes, self.config.log_backups)

            def command_factory(backend: str, reason: str) -> list[str]:
                return manager_command(
                    self.manager_script,
                    self.config.config_path,
                    backend,
                    reason,
                    operation_id=str(operation["operationId"]),
                    runtime_fingerprint=runtime_fingerprint,
                )

            bootstrap = self.bootstrap_factory(self.config, self.adapter)
            with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
                launched = bootstrap.start(
                    command_factory,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    stdout=stdout,
                    stderr=stderr,
                )
            self.adapter.secure_file(stdout_path)
            self.adapter.secure_file(stderr_path)
            operation = self.store.update(operation, checkpoint="bootstrap-launched")
            identity_seen = operation["checkpoint"] == "identity-published"
            last_state = None
            while True:
                if launched.process is not None and launched.process.poll() is not None:
                    raise ManagerUnresponsiveError(
                        "manager bootstrap 提前退出",
                        recommended_action="doctor",
                    )
                if self._remaining(deadline) <= 0:
                    break
                self._assert_runtime_contract(operation)
                last_state = self.resolver(reconcile_operation_id=str(operation["operationId"]))
                if last_state.manager_instance_id and not identity_seen:
                    identity_seen = True
                    changes: dict[str, Any] = {"checkpoint": "identity-published"}
                    if operation["kind"] == "ensure":
                        changes["expectedInstanceId"] = last_state.manager_instance_id
                    else:
                        changes["replacementInstanceId"] = last_state.manager_instance_id
                    operation = self.store.update(operation, **changes)
                if last_state.state == "ready":
                    return operation, last_state
                if last_state.state != "starting":
                    raise self.state_error(last_state)
                self.sleeper(min(0.1, self._remaining(deadline)))
            raise OperationTimeoutError(
                "manager bootstrap 未在期限内就绪",
                diagnostics={"lastState": getattr(last_state, "state", "starting")},
                recommended_action="status",
            )
        except BaseException as exc:
            cleanup_verified = (
                launched is None
                or bootstrap is not None
                and cleanup_bootstrap_result(
                    bootstrap,
                    launched,
                    timeout=min(5.0, self._remaining(deadline)),
                )
            )
            error = (
                {"code": exc.code, "message": exc.message}
                if isinstance(exc, PMError)
                else {"code": "internal_error", "message": type(exc).__name__}
            )
            if isinstance(exc, RuntimeCorruptError) and "runtime contract" in exc.message:
                error["code"] = "runtime_contract_changed"
            error["cleanupVerified"] = cleanup_verified
            try:
                self.store.update(operation, state="failed", error=error)
            except (OSError, PMError) as receipt_error:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"failed receipt 写入失败: {type(receipt_error).__name__}")
            if not isinstance(exc, Exception):
                raise
            if not cleanup_verified:
                raise ManagerUnresponsiveError(
                    "manager bootstrap 失败且清理未验证",
                    diagnostics={"causeCode": error["code"]},
                    recommended_action="doctor",
                ) from exc
            if isinstance(exc, PMError):
                raise
            raise ManagerUnresponsiveError("manager bootstrap 失败", recommended_action="doctor") from exc
