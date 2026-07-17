"""manager 只读状态解析与可恢复收敛操作。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .atomic import InterProcessFileLock
from .bootstrap import (
    BootstrapResult,
    ManagerBootstrap,
    cleanup_bootstrap_result,
    manager_command,
)
from .client import ManagerClient
from .errors import (
    EnvironmentUnverifiableError,
    ManagerStaleError,
    ManagerUnresponsiveError,
    OperationConflictError,
    OperationTimeoutError,
    PMError,
    RuntimeCorruptError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
    RuntimeUninitializedError,
    SupervisorError,
)
from .platforms import select_platform_adapter
from .platforms.base import PlatformAdapter
from .runtime import OperationStore, initialize_runtime, read_manager_identity_record, read_token, validate_operation_timeout
from .runtime_context import RuntimeContext


MANAGER_STATES = frozenset(
    "ready absent starting stopping stale unresponsive runtime_insecure "
    "runtime_permission_denied environment_unverifiable corrupt".split()
)
DEFAULT_START_TIMEOUT_SECONDS = 12.0

def _empty_evidence() -> dict[str, bool | None]:
    return {
        "runtimeReadable": False,
        "runtimeSecure": None,
        "identityPresent": False,
        "identityValid": None,
        "processAlive": None,
        "endpointReachable": None,
        "instanceMatched": None,
        "bootstrapResidue": False,
    }

@dataclass(frozen=True)
class ManagerStateSnapshot:
    state: str
    initialized: bool
    operation: dict[str, Any] | None
    evidence: dict[str, bool | None]
    recommended_action: str
    retry_after_ms: int | None
    context: RuntimeContext
    manager_instance_id: str | None = None

    @property
    def manager_ready(self) -> bool:
        return self.state == "ready"

    def public_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "managerReady": self.manager_ready,
            "initialized": self.initialized,
            "operation": self.operation,
            "evidence": dict(self.evidence),
            "recommendedAction": self.recommended_action,
            "retryAfterMs": self.retry_after_ms,
            "workspaceDigest": self.context.workspace_digest,
            "configDigest": self.context.config_digest,
            "managerInstanceId": self.manager_instance_id,
        }


AdapterFactory = Callable[[Path, Path], PlatformAdapter]
ClientFactory = Callable[..., ManagerClient]
BootstrapFactory = Callable[[Any, PlatformAdapter], ManagerBootstrap]


def _operation_store(context: RuntimeContext, adapter: PlatformAdapter) -> OperationStore:
    config = context.config
    digest = context.config_digest
    if config is None or digest is None:
        raise RuntimeUninitializedError("runtime 尚未初始化", recommended_action="init")
    return OperationStore(
        config,
        adapter,
        workspace_digest=context.workspace_digest,
        expected_config_digest=digest,
    )


def _runtime_failure_state(
    exc: BaseException,
    evidence: dict[str, bool | None],
    *,
    default: str,
) -> str:
    if isinstance(exc, RuntimeInsecureError):
        evidence["runtimeSecure"] = False
        return "runtime_insecure"
    if isinstance(exc, (PermissionError, RuntimePermissionDeniedError)):
        evidence["runtimeSecure"] = None
        return "runtime_permission_denied"
    if isinstance(exc, (EnvironmentUnverifiableError, SupervisorError, OSError)):
        evidence["runtimeSecure"] = None
        return "environment_unverifiable"
    return default


class ManagerStateResolver:
    def __init__(
        self,
        context: RuntimeContext,
        *,
        adapter_factory: AdapterFactory = select_platform_adapter,
        client_factory: ClientFactory = ManagerClient,
        bootstrap_factory: BootstrapFactory = ManagerBootstrap,
        probe_timeout: float = 0.5,
    ) -> None:
        self.context = context
        self.adapter_factory = adapter_factory
        self.client_factory = client_factory
        self.bootstrap_factory = bootstrap_factory
        self.probe_timeout = probe_timeout

    def _snapshot(
        self,
        state: str,
        evidence: dict[str, bool | None],
        *,
        operation: dict[str, Any] | None = None,
        store: OperationStore | None = None,
        instance_id: str | None = None,
    ) -> ManagerStateSnapshot:
        if state not in MANAGER_STATES:
            raise AssertionError(f"未知 manager state: {state}")
        actions = {
            "ready": "none",
            "absent": "ensure" if self.context.initialized else "init",
            "starting": "wait",
            "stopping": "wait",
            "stale": "restart",
            "unresponsive": "restart",
            "runtime_insecure": "doctor",
            "runtime_permission_denied": "doctor",
            "environment_unverifiable": "doctor",
            "corrupt": "doctor",
        }
        retry_after = 250 if state in {"starting", "stopping"} else None
        summary = store.public_summary(operation) if store is not None else None
        return ManagerStateSnapshot(
            state,
            self.context.initialized,
            summary,
            evidence,
            actions[state],
            retry_after,
            self.context,
            instance_id,
        )

    def _inspect_bootstrap_residue(
        self,
        config: Any,
        adapter: PlatformAdapter,
        evidence: dict[str, bool | None],
    ) -> str | None:
        try:
            evidence["bootstrapResidue"] = self.bootstrap_factory(config, adapter).residue_present()
        except (OSError, PMError) as exc:
            return _runtime_failure_state(exc, evidence, default="environment_unverifiable")
        return None

    def resolve(self, *, reconcile_operation_id: str | None = None) -> ManagerStateSnapshot:
        evidence = _empty_evidence()
        if not self.context.initialized:
            return self._snapshot("absent", evidence)
        config = self.context.config
        assert config is not None
        if config.state_root.is_symlink() or not config.state_root.is_dir():
            return self._snapshot("corrupt", evidence)
        try:
            adapter = self.adapter_factory(config.workspace_root, config.state_root)
            adapter.verify_file(config.config_path)
        except (OSError, PMError) as exc:
            return self._snapshot(_runtime_failure_state(exc, evidence, default="corrupt"), evidence)
        evidence["runtimeReadable"] = True
        evidence["runtimeSecure"] = True
        store = _operation_store(self.context, adapter)
        try:
            operation = store.read()
        except (OSError, PMError) as exc:
            return self._snapshot(_runtime_failure_state(exc, evidence, default="corrupt"), evidence)
        pending = operation is not None and operation["state"] == "pending"
        expired = bool(pending and store.expired(operation))
        pending_state = "stopping" if pending and operation["kind"] == "stop" else "starting"
        identity_path = config.paths.manager
        evidence["identityPresent"] = identity_path.exists()
        if pending and not expired and operation["operationId"] != reconcile_operation_id:
            return self._snapshot(pending_state, evidence, operation=operation, store=store)
        if not identity_path.exists():
            residue_error = self._inspect_bootstrap_residue(config, adapter, evidence)
            if residue_error is not None:
                return self._snapshot(residue_error, evidence, operation=operation, store=store)
            if pending:
                return self._snapshot("stale" if expired else pending_state, evidence, operation=operation, store=store)
            if evidence["bootstrapResidue"]:
                return self._snapshot("stale", evidence, operation=operation, store=store)
            return self._snapshot("absent", evidence, operation=operation, store=store)
        if not config.paths.token.exists():
            return self._snapshot("corrupt", evidence, operation=operation, store=store)
        try:
            read_token(config, adapter)
            identity = read_manager_identity_record(config, adapter)
        except (OSError, PMError) as exc:
            state = _runtime_failure_state(exc, evidence, default="corrupt")
            return self._snapshot(state, evidence, operation=operation, store=store)
        evidence["identityValid"] = True
        instance_id = str(identity["instanceId"])
        try:
            process_alive = adapter.identity_matches(identity["identity"])
        except (OSError, PMError) as exc:
            return self._snapshot(
                _runtime_failure_state(exc, evidence, default="environment_unverifiable"),
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        evidence["processAlive"] = process_alive
        if not process_alive:
            residue_error = self._inspect_bootstrap_residue(config, adapter, evidence)
            if residue_error is not None:
                return self._snapshot(
                    residue_error,
                    evidence,
                    operation=operation,
                    store=store,
                    instance_id=instance_id,
                )
            return self._snapshot("stale", evidence, operation=operation, store=store, instance_id=instance_id)
        try:
            _, response = self.client_factory(config, adapter, timeout=self.probe_timeout).request("GET", "/health")
            data = response.get("data")
            healthy = (
                response.get("ok") is True
                and isinstance(data, dict)
                and data.get("managerReady") is True
            )
        except PMError:
            healthy = False
        evidence["endpointReachable"] = healthy
        evidence["instanceMatched"] = healthy
        if healthy:
            return self._snapshot("ready", evidence, operation=operation, store=store, instance_id=instance_id)
        if pending and not expired:
            return self._snapshot(pending_state, evidence, operation=operation, store=store, instance_id=instance_id)
        return self._snapshot("unresponsive", evidence, operation=operation, store=store, instance_id=instance_id)


class ManagerConverger:
    def __init__(
        self,
        context: RuntimeContext,
        *,
        adapter_factory: AdapterFactory = select_platform_adapter,
        client_factory: ClientFactory = ManagerClient,
        bootstrap_factory: BootstrapFactory = ManagerBootstrap,
        manager_script: Path | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.context = context
        self.adapter_factory = adapter_factory
        self.client_factory = client_factory
        self.bootstrap_factory = bootstrap_factory
        self.manager_script = manager_script or Path(__file__).resolve().parents[1] / "manager_server.py"
        self.sleeper = sleeper

    def _resolver(self) -> ManagerStateResolver:
        return ManagerStateResolver(
            self.context,
            adapter_factory=self.adapter_factory,
            client_factory=self.client_factory,
            bootstrap_factory=self.bootstrap_factory,
        )

    @staticmethod
    def _rotate(path: Path, max_bytes: int, backups: int) -> None:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        if backups > 0:
            path.with_name(f"{path.name}.{backups}").unlink(missing_ok=True)
            for index in range(backups - 1, 0, -1):
                source = path.with_name(f"{path.name}.{index}")
                if source.exists():
                    source.replace(path.with_name(f"{path.name}.{index + 1}"))
            path.replace(path.with_name(f"{path.name}.1"))
        else:
            path.unlink()

    def _state_error(self, state: ManagerStateSnapshot) -> PMError:
        if state.state == "stale":
            return ManagerStaleError("manager runtime 已过期", recommended_action="restart")
        if state.state == "unresponsive":
            return ManagerUnresponsiveError("manager 进程存活但控制面不可达", recommended_action="restart")
        if state.state == "runtime_insecure":
            return RuntimeInsecureError("manager runtime 权限不安全", recommended_action="doctor")
        if state.state == "runtime_permission_denied":
            return RuntimePermissionDeniedError("manager runtime 访问被拒绝", recommended_action="doctor")
        if state.state == "environment_unverifiable":
            return EnvironmentUnverifiableError("当前环境无法验证 manager runtime", recommended_action="doctor")
        return RuntimeCorruptError("manager runtime 状态损坏", recommended_action="doctor")

    def _wait_for_existing_operation(
        self,
        store: OperationStore,
        operation: dict[str, Any],
        *,
        timeout: float,
    ) -> tuple[ManagerStateSnapshot, str | None]:
        deadline = time.monotonic() + timeout
        operation_id = str(operation["operationId"])
        last_state = self._resolver().resolve()
        while True:
            if operation["kind"] == "ensure":
                last_state = self._resolver().resolve(reconcile_operation_id=operation_id)
                if last_state.state == "ready":
                    store.complete_ensure(operation, last_state.manager_instance_id)
                    return last_state, operation_id
            else:
                last_state = self._resolver().resolve()
            if last_state.state not in {"starting", "stopping"}:
                return last_state, None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OperationTimeoutError(
                    "等待既有 manager operation 超时",
                    diagnostics={
                        "lastState": last_state.state,
                        "operation": store.public_summary(operation),
                    },
                    recommended_action="status",
                )
            self.sleeper(min(0.1, remaining))

    def ensure(self, *, timeout: float = DEFAULT_START_TIMEOUT_SECONDS) -> dict[str, Any]:
        timeout = validate_operation_timeout(timeout)
        initial = self._resolver().resolve()
        if initial.state == "ready":
            return {"state": "ready", "changed": False, "manager": initial.public_dict()}
        if not self.context.initialized or self.context.config is None:
            raise RuntimeUninitializedError("runtime 尚未初始化", recommended_action="init")
        config = self.context.config
        adapter = self.adapter_factory(config.workspace_root, config.state_root)
        adapter.secure_directory(config.paths.control)
        try:
            with InterProcessFileLock(config.paths.operation_lock, timeout=timeout + 1):
                adapter.secure_file(config.paths.operation_lock)
                store = _operation_store(self.context, adapter)
                current = self._resolver().resolve()
                if current.state == "ready":
                    return {"state": "ready", "changed": False, "manager": current.public_dict()}
                if current.state in {"starting", "stopping"}:
                    operation = store.read()
                    if operation is None or operation["state"] != "pending":
                        raise RuntimeCorruptError(
                            "过渡状态缺少 pending operation",
                            recommended_action="doctor",
                        )
                    current, operation_id = self._wait_for_existing_operation(
                        store,
                        operation,
                        timeout=timeout,
                    )
                    if current.state == "ready":
                        manager = current.public_dict()
                        manager["operation"] = store.public_summary(store.read())
                        return {
                            "state": "ready",
                            "changed": False,
                            "operationId": operation_id,
                            "manager": manager,
                        }
                if current.state != "absent":
                    raise self._state_error(current)
                operation_deadline = time.monotonic() + timeout
                operation = store.create("ensure", timeout=timeout)
                store.write(operation)
                launched: BootstrapResult | None = None
                bootstrap: ManagerBootstrap | None = None
                try:
                    initialize_runtime(config, adapter)
                    operation = store.update(operation, checkpoint="runtime-verified")
                    stdout_path = config.paths.logs / "manager-stdout.log"
                    stderr_path = config.paths.logs / "manager-stderr.log"
                    self._rotate(stdout_path, config.log_max_bytes, config.log_backups)
                    self._rotate(stderr_path, config.log_max_bytes, config.log_backups)

                    def command_factory(backend: str, reason: str) -> list[str]:
                        return manager_command(self.manager_script, config.config_path, backend, reason)

                    bootstrap = self.bootstrap_factory(config, adapter)
                    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
                        launched = bootstrap.start(
                            command_factory,
                            stdout_path=stdout_path,
                            stderr_path=stderr_path,
                            stdout=stdout,
                            stderr=stderr,
                        )
                    adapter.secure_file(stdout_path)
                    adapter.secure_file(stderr_path)
                    operation = store.update(operation, checkpoint="bootstrap-launched")
                    identity_seen = False
                    last_state = current
                    while time.monotonic() < operation_deadline:
                        if launched.process is not None and launched.process.poll() is not None:
                            raise ManagerUnresponsiveError(
                                "manager bootstrap 提前退出",
                                recommended_action="doctor",
                            )
                        last_state = self._resolver().resolve(
                            reconcile_operation_id=str(operation["operationId"])
                        )
                        if last_state.manager_instance_id and not identity_seen:
                            identity_seen = True
                            operation = store.update(
                                operation,
                                checkpoint="identity-published",
                                expectedInstanceId=last_state.manager_instance_id,
                            )
                        if last_state.state == "ready":
                            completed = store.complete_ensure(
                                operation,
                                last_state.manager_instance_id,
                            )
                            manager = last_state.public_dict()
                            manager["operation"] = store.public_summary(completed)
                            return {
                                **completed["outcome"],
                                "operationId": operation["operationId"],
                                "manager": manager,
                            }
                        if last_state.state not in {"starting"}:
                            raise self._state_error(last_state)
                        self.sleeper(min(0.1, max(0.0, operation_deadline - time.monotonic())))
                    raise OperationTimeoutError(
                        "manager bootstrap 未在期限内就绪",
                        diagnostics={"lastState": last_state.state},
                        recommended_action="status",
                    )
                except BaseException as exc:
                    cleanup_verified = (
                        launched is None
                        or bootstrap is not None
                        and cleanup_bootstrap_result(bootstrap, launched)
                    )
                    error = (
                        {"code": exc.code, "message": exc.message}
                        if isinstance(exc, PMError)
                        else {"code": "internal_error", "message": type(exc).__name__}
                    )
                    error["cleanupVerified"] = cleanup_verified
                    try:
                        store.update(operation, state="failed", error=error)
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
                    raise ManagerUnresponsiveError(
                        "manager bootstrap 失败",
                        recommended_action="doctor",
                    ) from exc
        except OperationConflictError as exc:
            current = self._resolver().resolve()
            raise OperationConflictError(
                exc.message,
                diagnostics={"manager": current.public_dict()},
                recommended_action="status",
            ) from exc
