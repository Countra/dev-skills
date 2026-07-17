"""manager runtime 的纯读 closed-state resolver。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .bootstrap import ManagerBootstrap
from .client import ManagerClient
from .errors import (
    EnvironmentUnverifiableError,
    ManagerStaleError,
    ManagerOfflineError,
    ManagerUnresponsiveError,
    PMError,
    RestartConfirmationRequiredError,
    RuntimeCorruptError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
    RuntimeUninitializedError,
    StopConfirmationRequiredError,
    SupervisorError,
    authenticated_health_error_state,
)
from .platforms import select_platform_adapter
from .platforms.base import PlatformAdapter
from .runtime import OperationStore, read_manager_identity_record, read_token
from .runtime_context import RuntimeContext
from .runtime_fingerprint import compute_runtime_fingerprint


MANAGER_STATES = frozenset(
    "ready absent starting stopping stale unresponsive runtime_insecure "
    "runtime_permission_denied environment_unverifiable corrupt".split()
)
RESTART_STOP_CHECKPOINTS = frozenset(
    "restart-requested intake-closed runs-terminating owners-empty manager-stopped bootstrap-cleaned".split()
)


def empty_evidence() -> dict[str, bool | str | None]:
    return {
        "runtimeReadable": False,
        "runtimeSecure": None,
        "identityPresent": False,
        "identityValid": None,
        "processAlive": None,
        "endpointReachable": None,
        "endpointState": None,
        "instanceMatched": None,
        "runtimeContractMatched": None,
        "bootstrapResidue": False,
    }


@dataclass(frozen=True)
class ManagerStateSnapshot:
    state: str
    initialized: bool
    operation: dict[str, Any] | None
    evidence: dict[str, bool | str | None]
    recommended_action: str
    retry_after_ms: int | None
    context: RuntimeContext
    manager_instance_id: str | None = None
    resources: dict[str, Any] | None = None

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
            "resources": self.resources,
        }


def state_error(state: ManagerStateSnapshot) -> PMError:
    if state.state == "stale":
        return ManagerStaleError("manager runtime 已过期", recommended_action="restart")
    if state.state == "unresponsive":
        return ManagerUnresponsiveError(
            "manager 进程存活但控制面不可达",
            recommended_action=state.recommended_action,
            retryable=state.recommended_action == "wait",
        )
    if state.state == "runtime_insecure":
        return RuntimeInsecureError("manager runtime 权限不安全", recommended_action="doctor")
    if state.state == "runtime_permission_denied":
        return RuntimePermissionDeniedError("manager runtime 访问被拒绝", recommended_action="doctor")
    if state.state == "environment_unverifiable":
        return EnvironmentUnverifiableError("当前环境无法验证 manager runtime", recommended_action="doctor")
    return RuntimeCorruptError("manager runtime 状态损坏", recommended_action="doctor")


def require_owned_run_confirmation(
    kind: str,
    state: Any,
    *,
    confirmed: bool,
) -> list[str]:
    summary = state.work_summary()
    affected = summary["activeRunKeys"]
    sessions = summary["activeSessionIds"]
    if (affected or sessions) and not confirmed:
        error_type = RestartConfirmationRequiredError if kind == "restart" else StopConfirmationRequiredError
        raise error_type(
            f"{kind} 将停止当前 live ownership，需要显式确认",
            diagnostics={"affectedRunKeys": affected, "affectedSessionIds": sessions},
            recommended_action=kind,
        )
    return affected


AdapterFactory = Callable[[Path, Path], PlatformAdapter]
ClientFactory = Callable[..., ManagerClient]
BootstrapFactory = Callable[[Any, PlatformAdapter], ManagerBootstrap]


def operation_store(context: RuntimeContext, adapter: PlatformAdapter) -> OperationStore:
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


def observed_manager_instance_id(config: Any, adapter: PlatformAdapter) -> str | None:
    path = adapter.validate_runtime_path(config.paths.manager)
    if not path.exists():
        return None
    return str(read_manager_identity_record(config, adapter)["instanceId"])


def runtime_failure_state(
    exc: BaseException,
    evidence: dict[str, bool | str | None],
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
        fingerprint_factory: Callable[[], str] = compute_runtime_fingerprint,
        probe_timeout: float = 0.5,
    ) -> None:
        self.context = context
        self.adapter_factory = adapter_factory
        self.client_factory = client_factory
        self.bootstrap_factory = bootstrap_factory
        self.fingerprint_factory = fingerprint_factory
        self.probe_timeout = probe_timeout

    def _snapshot(
        self,
        state: str,
        evidence: dict[str, bool | str | None],
        *,
        operation: dict[str, Any] | None = None,
        store: OperationStore | None = None,
        instance_id: str | None = None,
        retry_after_ms: int | None = None,
        resources: dict[str, Any] | None = None,
    ) -> ManagerStateSnapshot:
        if state not in MANAGER_STATES:
            raise AssertionError(f"未知 manager state: {state}")
        actions = {
            "ready": "none",
            "absent": "ensure" if self.context.initialized else "init",
            "starting": "wait",
            "stopping": "wait",
            "stale": "restart",
            "unresponsive": "wait" if retry_after_ms is not None else "restart",
            "runtime_insecure": "doctor",
            "runtime_permission_denied": "doctor",
            "environment_unverifiable": "doctor",
            "corrupt": "doctor",
        }
        retry_after = 250 if state in {"starting", "stopping"} else retry_after_ms
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
            resources,
        )

    @staticmethod
    def _pending_state(operation: dict[str, Any] | None) -> str:
        if operation is None or operation["state"] != "pending":
            return "starting"
        if operation["kind"] == "stop":
            return "stopping"
        if operation["kind"] == "restart" and operation["checkpoint"] in RESTART_STOP_CHECKPOINTS:
            return "stopping"
        return "starting"

    def _inspect_bootstrap_residue(
        self,
        config: Any,
        adapter: PlatformAdapter,
        evidence: dict[str, bool | str | None],
    ) -> str | None:
        try:
            evidence["bootstrapResidue"] = self.bootstrap_factory(config, adapter).residue_present()
        except (OSError, PMError) as exc:
            return runtime_failure_state(exc, evidence, default="environment_unverifiable")
        return None

    def _health_state(
        self,
        config: Any,
        adapter: PlatformAdapter,
        identity: dict[str, Any],
        current_fingerprint: str,
        evidence: dict[str, bool | str | None],
    ) -> tuple[str, int | None, dict[str, Any] | None]:
        try:
            status, response = self.client_factory(config, adapter, timeout=self.probe_timeout).request("GET", "/health")
        except ManagerUnresponsiveError as exc:
            retry = exc.diagnostics.get("retryAfterMs")
            evidence["endpointReachable"] = True
            if exc.diagnostics.get("endpointState") == "busy" and isinstance(retry, int):
                evidence["endpointState"] = "busy"
                evidence["instanceMatched"] = True
                return "unresponsive", retry, None
            evidence.update({"endpointState": "unresponsive", "instanceMatched": None})
            return "unresponsive", None, None
        except ManagerOfflineError:
            evidence.update({"endpointReachable": False, "instanceMatched": None})
            return "unresponsive", None, None
        except PMError:
            evidence.update({"endpointReachable": None, "instanceMatched": None})
            return "corrupt", None, None
        evidence["endpointReachable"] = True
        mapped = authenticated_health_error_state(status, response, identity["instanceId"])
        if mapped:
            state, secure = mapped
            evidence.update({"endpointState": "error", "instanceMatched": True, "runtimeSecure": secure})
            return state, None, None
        data = response.get("data")
        instance = data.get("instance") if isinstance(data, dict) else None
        instance_matched = (
            status == 200
            and response.get("ok") is True
            and isinstance(data, dict)
            and data.get("managerReady") is True
            and isinstance(instance, dict)
            and instance.get("id") == identity["instanceId"]
        )
        evidence["instanceMatched"] = instance_matched
        health_fingerprint = data.get("runtimeFingerprint") if isinstance(data, dict) else None
        health_operation_id = data.get("operationId") if isinstance(data, dict) else None
        if (
            not instance_matched
            or health_fingerprint != identity["runtimeFingerprint"]
            or health_operation_id != identity["operationId"]
        ):
            evidence["runtimeContractMatched"] = False
            return "corrupt", None, None
        evidence["runtimeContractMatched"] = health_fingerprint == current_fingerprint
        resources = data.get("resources") if isinstance(data.get("resources"), dict) else None
        return ("ready" if evidence["runtimeContractMatched"] else "stale"), None, resources

    def resolve(self, *, reconcile_operation_id: str | None = None) -> ManagerStateSnapshot:
        evidence = empty_evidence()
        if not self.context.initialized:
            return self._snapshot("absent", evidence)
        config = self.context.config
        assert config is not None
        try:
            adapter = self.adapter_factory(config.workspace_root, config.state_root)
            adapter.verify_directory(config.state_root)
            adapter.verify_file(config.config_path)
        except (OSError, PMError) as exc:
            return self._snapshot(runtime_failure_state(exc, evidence, default="corrupt"), evidence)
        evidence["runtimeReadable"] = True
        evidence["runtimeSecure"] = True
        store = operation_store(self.context, adapter)
        try:
            operation = store.read()
        except (OSError, PMError) as exc:
            return self._snapshot(runtime_failure_state(exc, evidence, default="corrupt"), evidence)
        pending = operation is not None and operation["state"] == "pending"
        expired = bool(pending and store.expired(operation))
        pending_state = self._pending_state(operation)
        try:
            identity_path = adapter.validate_runtime_path(config.paths.manager)
            identity_present = identity_path.exists()
        except (OSError, PMError) as exc:
            return self._snapshot(
                runtime_failure_state(exc, evidence, default="corrupt"),
                evidence,
                operation=operation,
                store=store,
            )
        evidence["identityPresent"] = identity_present
        current_fingerprint: str | None = None
        if identity_present or pending and operation["kind"] in {"ensure", "restart"}:
            try:
                current_fingerprint = self.fingerprint_factory()
            except PMError as exc:
                return self._snapshot(
                    runtime_failure_state(exc, evidence, default="environment_unverifiable"),
                    evidence,
                    operation=operation,
                    store=store,
                )
        if (
            pending
            and operation["kind"] in {"ensure", "restart"}
            and operation["expectedRuntimeFingerprint"] != current_fingerprint
        ):
            evidence["runtimeContractMatched"] = False
            return self._snapshot("stale", evidence, operation=operation, store=store)
        if not identity_present:
            residue_error = self._inspect_bootstrap_residue(config, adapter, evidence)
            if residue_error is not None:
                return self._snapshot(residue_error, evidence, operation=operation, store=store)
            if pending:
                owns_reconciliation = operation["operationId"] == reconcile_operation_id
                stop_checkpoint = pending_state == "stopping" and operation["checkpoint"] != (
                    "stop-requested" if operation["kind"] == "stop" else "restart-requested"
                )
                if owns_reconciliation and stop_checkpoint and not evidence["bootstrapResidue"]:
                    return self._snapshot("absent", evidence, operation=operation, store=store)
                return self._snapshot(
                    "stale" if expired else pending_state,
                    evidence,
                    operation=operation,
                    store=store,
                )
            if evidence["bootstrapResidue"]:
                return self._snapshot("stale", evidence, operation=operation, store=store)
            return self._snapshot("absent", evidence, operation=operation, store=store)

        try:
            token_path = adapter.validate_runtime_path(config.paths.token)
            token_present = token_path.exists()
        except (OSError, PMError) as exc:
            return self._snapshot(
                runtime_failure_state(exc, evidence, default="corrupt"),
                evidence,
                operation=operation,
                store=store,
            )
        if not token_present:
            return self._snapshot("corrupt", evidence, operation=operation, store=store)
        assert current_fingerprint is not None
        try:
            read_token(config, adapter)
            identity = read_manager_identity_record(config, adapter)
        except (OSError, PMError) as exc:
            state = runtime_failure_state(exc, evidence, default="corrupt")
            return self._snapshot(state, evidence, operation=operation, store=store)
        evidence["identityValid"] = True
        instance_id = str(identity["instanceId"])
        start_identity_expected = (
            pending
            and operation["kind"] in {"ensure", "restart"}
            and operation["checkpoint"] in {
                "runtime-verified",
                "bootstrap-launched",
                "identity-published",
                "endpoint-ready",
            }
        )
        if start_identity_expected and identity["operationId"] != operation["operationId"]:
            evidence["instanceMatched"] = False
            return self._snapshot(
                "corrupt",
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        if identity["runtimeFingerprint"] != current_fingerprint:
            evidence["runtimeContractMatched"] = False
            return self._snapshot(
                "stale",
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        if (
            operation is not None
            and operation["kind"] == "ensure"
            and operation.get("expectedInstanceId") is not None
            and operation["expectedInstanceId"] != instance_id
        ):
            evidence["instanceMatched"] = False
            return self._snapshot(
                "corrupt",
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        try:
            process_alive = adapter.identity_matches(identity["identity"])
        except (OSError, PMError) as exc:
            return self._snapshot(
                runtime_failure_state(exc, evidence, default="environment_unverifiable"),
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        evidence["processAlive"] = process_alive
        if not process_alive:
            residue_error = self._inspect_bootstrap_residue(config, adapter, evidence)
            state = residue_error or "stale"
            return self._snapshot(
                state,
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        health_state, retry_after, resources = self._health_state(
            config,
            adapter,
            identity,
            current_fingerprint,
            evidence,
        )
        if health_state == "ready":
            if pending and pending_state == "stopping" and not expired:
                return self._snapshot(
                    "stopping",
                    evidence,
                    operation=operation,
                    store=store,
                    instance_id=instance_id,
                    resources=resources,
                )
            return self._snapshot(
                "ready",
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
                resources=resources,
            )
        if health_state == "unresponsive" and pending and not expired:
            return self._snapshot(
                pending_state,
                evidence,
                operation=operation,
                store=store,
                instance_id=instance_id,
            )
        return self._snapshot(
            health_state,
            evidence,
            operation=operation,
            store=store,
            instance_id=instance_id,
            retry_after_ms=retry_after,
            resources=resources,
        )
