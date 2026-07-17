"""manager operation 的可恢复收敛状态机。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .atomic import InterProcessFileLock
from .bootstrap import ManagerBootstrap
from .client import ManagerClient, request_manager_shutdown
from .errors import (
    ConflictError,
    IdentityError,
    ManagerUnresponsiveError,
    OperationConflictError,
    RuntimeCorruptError,
    RuntimeUninitializedError,
)
from .manager_start import ManagerStartCoordinator
from .manager_state import (
    AdapterFactory,
    BootstrapFactory,
    ClientFactory,
    ManagerStateResolver,
    observed_manager_instance_id, operation_store,
    require_owned_run_confirmation,
    state_error,
)
from .platforms import select_platform_adapter
from .platforms.base import PlatformAdapter
from .run_finalization import RunFinalizationCoordinator
from .runtime import OperationStore, read_manager_identity_record, validate_operation_timeout
from .runtime_context import RuntimeContext
from .runtime_fingerprint import compute_runtime_fingerprint
from .state import StateStore

DEFAULT_START_TIMEOUT_SECONDS = 12.0
STOP_REQUEST_CHECKPOINTS = {"stop": "stop-requested", "restart": "restart-requested"}
STOP_PHASE_CHECKPOINTS = frozenset("stop-requested restart-requested intake-closed runs-terminating owners-empty manager-stopped bootstrap-cleaned".split())
RESTART_START_CHECKPOINTS = frozenset("runtime-verified bootstrap-launched identity-published endpoint-ready".split())
class ManagerConverger:
    def __init__(
        self,
        context: RuntimeContext,
        *,
        adapter_factory: AdapterFactory = select_platform_adapter,
        client_factory: ClientFactory = ManagerClient,
        bootstrap_factory: BootstrapFactory = ManagerBootstrap,
        manager_script: Path | None = None,
        fingerprint_factory: Callable[[], str] = compute_runtime_fingerprint,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.context = context
        self.adapter_factory = adapter_factory
        self.client_factory = client_factory
        self.bootstrap_factory = bootstrap_factory
        self.manager_script = manager_script or Path(__file__).resolve().parents[1] / "manager_server.py"
        self.fingerprint_factory = fingerprint_factory
        self.sleeper = sleeper

    def _resolver(self) -> ManagerStateResolver:
        return ManagerStateResolver(
            self.context,
            adapter_factory=self.adapter_factory,
            client_factory=self.client_factory,
            bootstrap_factory=self.bootstrap_factory,
            fingerprint_factory=self.fingerprint_factory,
        )

    @staticmethod
    def _remaining(deadline: float) -> float:
        return max(0.0, deadline - time.monotonic())

    def _runtime(self) -> tuple[Any, PlatformAdapter, OperationStore]:
        config = self.context.config
        if not self.context.initialized or config is None:
            raise RuntimeUninitializedError("runtime 尚未初始化", recommended_action="init")
        adapter = self.adapter_factory(config.workspace_root, config.state_root)
        return config, adapter, operation_store(self.context, adapter)

    def _start_coordinator(
        self,
        config: Any,
        adapter: PlatformAdapter,
        store: OperationStore,
    ) -> ManagerStartCoordinator:
        return ManagerStartCoordinator(
            config,
            adapter,
            store,
            bootstrap_factory=self.bootstrap_factory,
            manager_script=self.manager_script,
            resolver=self._resolver().resolve,
            state_error=state_error,
            fingerprint_factory=self.fingerprint_factory,
            sleeper=self.sleeper,
        )

    @staticmethod
    def _operation_conflict(store: OperationStore, operation: dict[str, Any]) -> OperationConflictError:
        return OperationConflictError(
            "存在其它 pending manager operation",
            diagnostics={"operation": store.public_summary(operation)},
            recommended_action="status",
        )

    def ensure(self, *, timeout: float = DEFAULT_START_TIMEOUT_SECONDS) -> dict[str, Any]:
        timeout = validate_operation_timeout(timeout)
        deadline = time.monotonic() + timeout
        if not self.context.initialized:
            raise RuntimeUninitializedError("runtime 尚未初始化", recommended_action="init")
        config, adapter, store = self._runtime()
        adapter.secure_directory(config.paths.control)
        store.prepare_lock()
        with InterProcessFileLock(config.paths.operation_lock, timeout=timeout + 1):
            state = StateStore(config, adapter)
            state.clear_terminal_intake_fence(store)
            current = self._resolver().resolve()
            operation = store.read()
            launch_authorized = False
            if current.state == "ready":
                operation_id = None
                if operation is not None and operation["state"] == "pending":
                    if operation["kind"] != "ensure":
                        raise self._operation_conflict(store, operation)
                    operation = store.complete_ensure(operation, str(current.manager_instance_id))
                    operation_id = operation["operationId"]
                return {
                    "state": "ready",
                    "changed": False,
                    "operationId": operation_id,
                    "manager": current.public_dict(),
                }
            if operation is not None and operation["state"] == "pending":
                if operation["kind"] != "ensure":
                    raise self._operation_conflict(store, operation)
                operation, launch_authorized = self._start_coordinator(config, adapter, store).recover(
                    operation,
                    timeout=timeout,
                    deadline=deadline,
                )
            else:
                if current.state != "absent":
                    raise state_error(current)
                operation = store.create(
                    "ensure",
                    timeout=timeout,
                    expected_runtime_fingerprint=self.fingerprint_factory(),
                    expected_work_generation=None,
                )
                store.write(operation)
                launch_authorized = True
            operation, current = self._start_coordinator(config, adapter, store).run(
                operation,
                deadline=deadline,
                launch_authorized=launch_authorized,
            )
            completed = store.complete_ensure(operation, str(current.manager_instance_id))
            manager = current.public_dict()
            manager["operation"] = store.public_summary(completed)
            return {
                **completed["outcome"],
                "operationId": completed["operationId"],
                "manager": manager,
            }

    def _destructive_operation(
        self,
        kind: str,
        store: OperationStore,
        state: StateStore,
        *,
        timeout: float,
        confirmed: bool, expected_instance_id: str | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        request_checkpoint = STOP_REQUEST_CHECKPOINTS[kind]
        with state.transaction():
            operation = store.read()
            if operation is not None and operation["state"] == "pending":
                if operation["kind"] != kind:
                    raise self._operation_conflict(store, operation)
                if operation["checkpoint"] != request_checkpoint:
                    summary = state.work_summary()
                    fence = summary["intakeFence"]
                    if (
                        operation["checkpoint"] == "bootstrap-cleaned"
                        and fence is None
                        and not summary["activeRunKeys"]
                    ):
                        return operation, []
                    if not isinstance(fence, dict) or fence.get("operationId") != operation["operationId"]:
                        raise RuntimeCorruptError("pending destructive operation 缺少匹配 intake fence")
                    if store.expired(operation):
                        operation = store.update(
                            operation,
                            deadlineAt=(datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat(),
                        )
                    return operation, list(summary["activeRunKeys"])
            summary = state.work_summary()
            affected = require_owned_run_confirmation(kind, state, confirmed=confirmed)
            generation = int(summary["workGeneration"])
            if operation is not None and operation["state"] == "pending":
                if operation["expectedWorkGeneration"] != generation:
                    store.update(
                        operation,
                        state="failed",
                        error={"code": "precondition_changed", "message": "work generation 已变化"},
                    )
                    raise OperationConflictError(
                        "destructive operation 前置状态已变化",
                        diagnostics={
                            "expectedWorkGeneration": operation["expectedWorkGeneration"],
                            "actualWorkGeneration": generation,
                        },
                        recommended_action="status",
                    )
                if store.expired(operation):
                    operation = store.update(
                        operation,
                        deadlineAt=(datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat(),
                    )
            else:
                operation = {**store.create(
                    kind,
                    timeout=timeout,
                    expected_runtime_fingerprint=self.fingerprint_factory() if kind == "restart" else None,
                    expected_work_generation=generation,
                ), "expectedInstanceId": expected_instance_id}
                store.write(operation)
            try:
                state.install_intake_fence(
                    operation_id=str(operation["operationId"]),
                    kind=kind,
                    expected_generation=generation,
                )
            except ConflictError as exc:
                store.update(
                    operation,
                    state="failed",
                    error={"code": "precondition_changed", "message": "work generation 已变化"},
                )
                raise OperationConflictError(
                    "destructive operation 前置状态已变化",
                    diagnostics=exc.diagnostics,
                    recommended_action="status",
                ) from exc
            return store.update(operation, checkpoint="intake-closed"), affected

    def _stop_exact_manager(
        self,
        operation: dict[str, Any],
        store: OperationStore,
        config: Any,
        adapter: PlatformAdapter,
        deadline: float,
    ) -> dict[str, Any]:
        manager_path = adapter.validate_runtime_path(config.paths.manager)
        if not manager_path.exists():
            return operation
        identity = read_manager_identity_record(config, adapter)
        expected_instance = operation.get("expectedInstanceId")
        if expected_instance is not None and identity["instanceId"] != expected_instance:
            raise IdentityError("manager identity 在 operation 内发生变化")
        if expected_instance is None:
            operation = store.update(operation, expectedInstanceId=identity["instanceId"])
        current = self._resolver().resolve(reconcile_operation_id=str(operation["operationId"]))
        exact_state = current.state
        if current.state == "stopping":
            if (
                current.evidence["processAlive"] is True
                and current.evidence["endpointReachable"] is True
                and current.evidence["instanceMatched"] is True
                and current.evidence["runtimeContractMatched"] is True
            ):
                exact_state = "ready"
            elif (
                current.evidence["processAlive"] is True
                and current.evidence["endpointReachable"] is False
            ):
                exact_state = "unresponsive"
        if exact_state not in {"ready", "stale", "unresponsive"}:
            raise state_error(current)
        request_shutdown = None
        if exact_state == "ready":
            remaining = self._remaining(deadline)
            if remaining <= 0:
                raise ManagerUnresponsiveError("manager stop deadline 已耗尽")
            request_shutdown = lambda: request_manager_shutdown(
                self.client_factory(config, adapter, timeout=remaining), str(operation["operationId"]), remaining)
        self.bootstrap_factory(config, adapter).stop_manager(
            identity,
            request_shutdown=request_shutdown,
            allow_terminate=exact_state in {"stale", "unresponsive"},
            timeout=self._remaining(deadline),
        )
        return operation

    def _stop_phase(
        self,
        kind: str,
        operation: dict[str, Any],
        store: OperationStore,
        state: StateStore,
        config: Any,
        adapter: PlatformAdapter,
        *,
        deadline: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        checkpoint = str(operation["checkpoint"])
        if checkpoint not in STOP_PHASE_CHECKPOINTS:
            raise RuntimeCorruptError("manager stop phase checkpoint 无效")
        if checkpoint == "intake-closed":
            operation = store.update(operation, checkpoint="runs-terminating")
            checkpoint = "runs-terminating"
        if checkpoint == "runs-terminating":
            operation = self._stop_exact_manager(operation, store, config, adapter, deadline)
            reconciliation = RunFinalizationCoordinator(
                state,
                adapter,
                f"control-{operation['operationId']}",
            ).reconcile_manager_loss(termination_operation_id=str(operation["operationId"]), deadline=deadline)
            if reconciliation["pending"]:
                raise ManagerUnresponsiveError(
                    "manager owned run 清理尚未完成",
                    diagnostics={"pendingRunKeys": reconciliation["pending"]},
                    recommended_action="status",
                )
            operation = store.update(operation, checkpoint="owners-empty")
            checkpoint = "owners-empty"
        if checkpoint == "owners-empty":
            if adapter.validate_runtime_path(config.paths.manager).exists():
                raise ManagerUnresponsiveError("manager identity 仍存在", recommended_action="doctor")
            operation = store.update(operation, checkpoint="manager-stopped")
            checkpoint = "manager-stopped"
        if checkpoint == "manager-stopped":
            if not self.bootstrap_factory(config, adapter).cleanup_residue():
                raise ManagerUnresponsiveError("manager bootstrap residue 清理未验证", recommended_action="doctor")
            operation = store.update(operation, checkpoint="bootstrap-cleaned")
            checkpoint = "bootstrap-cleaned"
        if checkpoint != "bootstrap-cleaned":
            raise RuntimeCorruptError("manager stop phase 未收敛")
        operation_id = str(operation["operationId"])
        return operation, {
            "oldManagerInstanceId": operation.get("expectedInstanceId"),
            "stoppedRunKeys": state.stopped_run_keys(operation_id),
            "cleanup": {
                "ownersEmpty": True,
                "managerStopped": True,
                "bootstrapCleaned": True,
            },
        }

    def stop(
        self,
        *,
        timeout: float = DEFAULT_START_TIMEOUT_SECONDS,
        confirm_stop_owned_runs: bool = False,
    ) -> dict[str, Any]:
        timeout = validate_operation_timeout(timeout)
        if not self.context.initialized:
            return {
                "state": "absent",
                "changed": False,
                "oldManagerInstanceId": None,
                "stoppedRunKeys": [],
                "cleanup": {"ownersEmpty": True, "managerStopped": True, "bootstrapCleaned": True},
            }
        deadline = time.monotonic() + timeout
        config, adapter, store = self._runtime()
        adapter.secure_directory(config.paths.control)
        store.prepare_lock()
        with InterProcessFileLock(config.paths.operation_lock, timeout=timeout + 1):
            state = StateStore(config, adapter)
            state.clear_terminal_intake_fence(store)
            current = self._resolver().resolve()
            existing = store.read()
            affected = state.work_summary()["activeRunKeys"]
            if current.state == "absent" and not affected and not (
                existing is not None and existing["state"] == "pending"
            ):
                return {
                    "state": "absent",
                    "changed": False,
                    "oldManagerInstanceId": None,
                    "stoppedRunKeys": [],
                    "cleanup": {"ownersEmpty": True, "managerStopped": True, "bootstrapCleaned": True},
                }
            operation, _ = self._destructive_operation(
                "stop",
                store,
                state,
                timeout=timeout, confirmed=confirm_stop_owned_runs,
                expected_instance_id=current.manager_instance_id,
            )
            operation, summary = self._stop_phase(
                "stop",
                operation,
                store,
                state,
                config,
                adapter,
                deadline=deadline,
            )
            outcome = {"state": "absent", "changed": True, **summary}
            completed = store.update(operation, state="succeeded", outcome=outcome)
            state.clear_terminal_intake_fence(store)
            return {**outcome, "operationId": completed["operationId"]}

    def restart(
        self,
        *,
        timeout: float = DEFAULT_START_TIMEOUT_SECONDS,
        confirm_stop_owned_runs: bool = False,
    ) -> dict[str, Any]:
        timeout = validate_operation_timeout(timeout)
        deadline = time.monotonic() + timeout
        config, adapter, store = self._runtime()
        adapter.secure_directory(config.paths.control)
        store.prepare_lock()
        with InterProcessFileLock(config.paths.operation_lock, timeout=timeout + 1):
            state = StateStore(config, adapter)
            state.clear_terminal_intake_fence(store)
            operation, _ = self._destructive_operation(
                "restart",
                store,
                state,
                timeout=timeout, confirmed=confirm_stop_owned_runs,
                expected_instance_id=observed_manager_instance_id(config, adapter),
            )
            launch_authorized = False
            if operation["checkpoint"] in RESTART_START_CHECKPOINTS or operation["checkpoint"] == "bootstrap-cleaned":
                def release_terminal_fence() -> int:
                    state.clear_terminal_intake_fence(store)
                    return int(state.work_summary()["workGeneration"])

                operation, launch_authorized = self._start_coordinator(config, adapter, store).recover(
                    operation,
                    timeout=timeout,
                    deadline=deadline,
                    release_terminal_fence=release_terminal_fence,
                )
                if operation["checkpoint"] == "restart-requested":
                    operation, _ = self._destructive_operation(
                        "restart",
                        store,
                        state,
                        timeout=timeout,
                        confirmed=confirm_stop_owned_runs,
                    )
            if operation["checkpoint"] in RESTART_START_CHECKPOINTS:
                summary = {
                    "oldManagerInstanceId": operation.get("expectedInstanceId"),
                    "stoppedRunKeys": state.stopped_run_keys(str(operation["operationId"])),
                    "cleanup": {
                        "ownersEmpty": True,
                        "managerStopped": True,
                        "bootstrapCleaned": True,
                    },
                }
            else:
                operation, summary = self._stop_phase(
                    "restart",
                    operation,
                    store,
                    state,
                    config,
                    adapter,
                    deadline=deadline,
                )
                launch_authorized = True
            operation, current = self._start_coordinator(config, adapter, store).run(
                operation,
                deadline=deadline,
                launch_authorized=launch_authorized,
            )
            new_instance = current.manager_instance_id
            old_instance = summary["oldManagerInstanceId"]
            if new_instance is None or old_instance is not None and new_instance == old_instance:
                raise IdentityError("restart 未形成新的 manager instance")
            replacement_instance = operation.get("replacementInstanceId")
            if replacement_instance is not None and replacement_instance != new_instance:
                raise IdentityError("restart replacement instance 与 receipt 不匹配")
            operation = store.update(operation, checkpoint="endpoint-ready", replacementInstanceId=new_instance)
            outcome = {
                "state": "ready",
                "changed": True,
                **summary,
                "newManagerInstanceId": new_instance,
                "servicesRestored": False,
            }
            completed = store.update(operation, state="succeeded", outcome=outcome)
            state.clear_terminal_intake_fence(store)
            return {**outcome, "operationId": completed["operationId"], "manager": current.public_dict()}
