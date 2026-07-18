"""owner-first run finalization 与 manager-loss reconciliation。"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .atomic import read_json_file
from .errors import IdentityError, PMError, StateError, SupervisorError
from .logs import MAX_HOST_STATE_BYTES
from .platforms.base import OwnerInspection, PersistedOwnerEvidence, PlatformAdapter, RunOwner


OWNER_FORCE_SECONDS, OWNER_SETTLE_SECONDS = 5.0, 1.0


@dataclass(frozen=True)
class OwnerFinalization:
    owner_empty: bool
    cleanup_verified: bool
    graceful_signaled: bool
    force_required: bool
    force_signaled: bool
    accounting: dict[str, Any]
    error: str | None


@dataclass
class ManagedRun:
    service: Any
    owner: RunOwner
    capability: str
    capability_hash: str
    host_state: Path
    finalization_lock: Any = field(default_factory=threading.RLock)


class OwnerFinalizer:
    """统一收口内存 owner 与持久 owner，终态提交由 repository 负责。"""

    def __init__(self, adapter: PlatformAdapter, *, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.adapter = adapter
        self.sleeper = sleeper

    @staticmethod
    def _phase_deadline(timeout: float, deadline: float | None) -> float:
        phase = time.monotonic() + max(0.0, timeout)
        return phase if deadline is None else min(phase, deadline)

    def _wait_live(self, owner: RunOwner, timeout: float, deadline: float | None) -> bool:
        phase_deadline = self._phase_deadline(timeout, deadline)
        while time.monotonic() <= phase_deadline:
            if owner.is_empty():
                return True
            self.sleeper(min(0.1, max(0.0, phase_deadline - time.monotonic())))
        return owner.is_empty()

    def finalize_live(
        self,
        owner: RunOwner,
        *,
        grace_seconds: float,
        request_graceful: bool = True,
        deadline: float | None = None,
    ) -> OwnerFinalization:
        graceful_signaled = False
        force_required = False
        force_signaled = False
        error = None
        try:
            if request_graceful:
                graceful_signaled = owner.graceful_stop()
            owner_empty = self._wait_live(owner, grace_seconds, deadline)
            if not owner_empty:
                force_required = True
                force_signaled = owner.force_stop()
                owner_empty = self._wait_live(owner, OWNER_FORCE_SECONDS, deadline)
            cleanup_verified = owner_empty
            if owner_empty:
                try:
                    owner.close()
                except Exception:  # noqa: BLE001
                    cleanup_verified = False
                    error = "owner_release_failed"
            elif not force_signaled:
                error = "owner_force_signal_failed"
            else:
                error = "owner_not_empty"
        except Exception:  # noqa: BLE001
            owner_empty = False
            cleanup_verified = False
            error = "owner_cleanup_failed"
        return OwnerFinalization(
            owner_empty,
            cleanup_verified,
            graceful_signaled,
            force_required,
            force_signaled,
            {},
            error,
        )

    def _inspect(self, evidence: PersistedOwnerEvidence) -> OwnerInspection:
        try:
            return self.adapter.inspect_persisted_owner(evidence)
        except Exception:  # noqa: BLE001
            return OwnerInspection("unverifiable", False, {}, "owner_inspection_failed")

    def inspect(self, evidence: PersistedOwnerEvidence) -> OwnerInspection:
        return self._inspect(evidence)

    def _signal(self, evidence: PersistedOwnerEvidence, *, force: bool) -> bool:
        try:
            return self.adapter.signal_persisted_owner(evidence, force=force)
        except Exception:  # noqa: BLE001
            return False

    def _wait_persisted(
        self,
        evidence: PersistedOwnerEvidence,
        timeout: float,
        deadline: float | None,
    ) -> OwnerInspection:
        phase_deadline = self._phase_deadline(timeout, deadline)
        inspection = self._inspect(evidence)
        while not inspection.empty and inspection.state != "unverifiable" and time.monotonic() < phase_deadline:
            self.sleeper(min(0.1, max(0.0, phase_deadline - time.monotonic())))
            inspection = self._inspect(evidence)
        return inspection

    def finalize_persisted(
        self,
        evidence: PersistedOwnerEvidence,
        *,
        grace_seconds: float,
        deadline: float | None = None,
    ) -> OwnerFinalization:
        inspection = self._wait_persisted(evidence, OWNER_SETTLE_SECONDS, deadline)
        graceful_signaled = False
        force_required = False
        force_signaled = False
        if not inspection.empty and inspection.cleanup_supported:
            graceful_signaled = self._signal(evidence, force=False)
            inspection = self._wait_persisted(evidence, grace_seconds, deadline)
        if not inspection.empty and inspection.cleanup_supported:
            force_required = True
            force_signaled = self._signal(evidence, force=True)
            inspection = self._wait_persisted(evidence, OWNER_FORCE_SECONDS, deadline)
        owner_empty = inspection.empty
        cleanup_verified = owner_empty
        if owner_empty:
            try:
                cleanup_verified = self.adapter.release_persisted_owner(evidence)
            except Exception:  # noqa: BLE001
                cleanup_verified = False
        if not owner_empty:
            error = inspection.error or (
                "owner_force_signal_failed" if force_required and not force_signaled else "owner_not_empty"
            )
        elif not cleanup_verified:
            error = "owner_release_failed"
        else:
            error = None
        return OwnerFinalization(
            owner_empty,
            cleanup_verified,
            graceful_signaled,
            force_required,
            force_signaled,
            dict(inspection.accounting),
            error,
        )


class RunFinalizationCoordinator:
    """以短 claim、锁外 native cleanup 和 CAS terminal commit 收口 run。"""

    def __init__(self, state: Any, adapter: PlatformAdapter, manager_instance_id: str) -> None:
        self.state = state
        self.adapter = adapter
        self.manager_instance_id = manager_instance_id
        self.owner_finalizer = OwnerFinalizer(adapter)
        self._persisted_locks: dict[str, threading.RLock] = {}

    @staticmethod
    def _owner_evidence(record: dict[str, Any]) -> PersistedOwnerEvidence:
        internal = record.get("internal")
        if not isinstance(internal, dict):
            raise StateError("run internal evidence 缺失")
        owner = internal.get("owner")
        host_identity = internal.get("hostIdentity")
        target_identity = internal.get("targetIdentity")
        host_state_value = internal.get("hostState")
        capability_hash = internal.get("capabilityHash")
        run_id = record.get("processId")
        if (
            not isinstance(owner, dict)
            or not isinstance(host_identity, dict)
            or target_identity is not None
            and not isinstance(target_identity, dict)
            or not isinstance(capability_hash, str)
            or not capability_hash
            or not isinstance(run_id, str)
        ):
            raise StateError("run persisted owner evidence 不完整")
        host_state = Path(host_state_value) if isinstance(host_state_value, str) else None
        if host_state is not None:
            expected_host_state = Path(record["runDir"]) / "host-state.json"
            if (
                not host_state.is_absolute()
                or host_state != expected_host_state
                or host_state.is_symlink()
            ):
                raise StateError("run host-state recovery path 无效")
        return PersistedOwnerEvidence(
            run_id,
            capability_hash,
            owner,
            host_identity,
            target_identity,
            host_state,
        )

    def _enrich_evidence(self, record: dict[str, Any]) -> PersistedOwnerEvidence:
        evidence = self._owner_evidence(record)
        if evidence.target_identity is not None:
            return evidence
        if evidence.host_state is None:
            return evidence
        self.adapter.validate_runtime_path(evidence.host_state)
        if not evidence.host_state.is_file():
            return evidence
        self.adapter.verify_file(evidence.host_state)
        value = read_json_file(evidence.host_state, max_bytes=MAX_HOST_STATE_BYTES)
        target = value.get("target") if isinstance(value, dict) else None
        target_identity = value.get("targetIdentity") if isinstance(value, dict) else None
        owner_identity = value.get("ownerIdentity") if isinstance(value, dict) else None
        if (
            not isinstance(value, dict)
            or value.get("schema") != "process-manager"
            or value.get("runId") != evidence.run_id
            or value.get("capabilityHash") != evidence.capability_hash
            or value.get("hostPid") != evidence.host_identity.get("pid")
            or not isinstance(target, dict)
            or not isinstance(target.get("pid"), int)
            or not isinstance(target_identity, dict)
            or target_identity.get("pid") != target["pid"]
            or not isinstance(owner_identity, dict)
            or owner_identity.get("capabilityHash") != evidence.capability_hash
            or owner_identity.get("hostPid") != evidence.host_identity.get("pid")
            or any(
                name not in owner_identity or existing is not None and owner_identity[name] != existing
                for name, existing in evidence.owner.items()
            )
        ):
            raise IdentityError("host-state recovery evidence 不匹配")
        updated = self.state.update(
            str(record["processKey"]),
            status="terminating",
            internal_updates={"owner": owner_identity, "targetIdentity": target_identity},
            expected_revision=int(record["recordRevision"]),
        )
        return self._owner_evidence(updated)

    def _claim(self, record: dict[str, Any], *, reason: str) -> dict[str, Any]:
        existing = record.get("cleanupClaim")
        takeover_inspected = False
        if isinstance(existing, dict):
            try:
                expired = datetime.fromisoformat(str(existing["deadlineAt"])).astimezone(timezone.utc) <= datetime.now(
                    timezone.utc
                )
            except (TypeError, ValueError) as exc:
                raise StateError("run cleanup claim deadline 无效") from exc
            if expired:
                evidence = self._enrich_evidence(record)
                inspection = self.owner_finalizer.inspect(evidence)
                if inspection.state == "unverifiable":
                    raise StateError(
                        "过期 finalizer claim 的 owner 无法验证",
                        diagnostics={"processKey": record["processKey"], "error": inspection.error},
                    )
                takeover_inspected = True
        return self.state.claim_finalization(
            str(record["processKey"]),
            reason=reason,
            manager_instance_id=self.manager_instance_id,
            takeover_inspected=takeover_inspected,
        )

    def finalize(
        self,
        record: dict[str, Any],
        *,
        reason: str,
        terminal_status: str,
        live_run: ManagedRun | None = None,
        public_updates: dict[str, Any] | None = None,
        request_graceful: bool = True,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        key = str(record["processKey"])
        lock = live_run.finalization_lock if live_run is not None else self._persisted_locks.setdefault(key, threading.RLock())
        with lock:
            record = self.state.get(key=key)
            if record.get("status") not in self.state.active_states:
                return record
            claimed = self._claim(record, reason=reason)
            claim = claimed["cleanupClaim"]
            claim_id = str(claim["claimId"])
            if live_run is not None:
                internal = claimed.get("internal", {})
                if (
                    internal.get("capabilityHash") != live_run.capability_hash
                    or internal.get("owner") != live_run.owner.internal_identity()
                ):
                    raise IdentityError("run owner 内存 identity 不一致")
                grace_seconds = float(live_run.service.stop["graceSeconds"])
                result = self.owner_finalizer.finalize_live(
                    live_run.owner,
                    grace_seconds=grace_seconds,
                    request_graceful=request_graceful,
                    deadline=deadline,
                )
            else:
                stop = claimed.get("public", {}).get("serviceConfig", {}).get("stop", {})
                grace_seconds = float(stop.get("graceSeconds", 0))
                try:
                    evidence = self._enrich_evidence(claimed)
                    result = self.owner_finalizer.finalize_persisted(
                        evidence,
                        grace_seconds=grace_seconds,
                        deadline=deadline,
                    )
                except (IdentityError, StateError, TypeError, ValueError):
                    result = OwnerFinalization(False, False, False, False, False, {}, "owner_evidence_invalid")
            if terminal_status == "exited" and result.force_required:
                terminal_status = "contract_violation"
            return self.commit_result(
                claimed,
                terminal_status=terminal_status,
                result=result,
                claim_id=claim_id,
                public_updates=public_updates,
                request_graceful=request_graceful,
                grace_seconds=grace_seconds,
            )

    def commit_result(
        self,
        record: dict[str, Any],
        *,
        terminal_status: str,
        result: OwnerFinalization,
        claim_id: str | None = None,
        public_updates: dict[str, Any] | None = None,
        request_graceful: bool,
        grace_seconds: float,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if claim_id is None:
            if reason is None:
                raise StateError("直接提交 finalization result 时必须提供 reason")
            record = self._claim(record, reason=reason)
            claim_id = str(record["cleanupClaim"]["claimId"])
        return self.state.commit_finalization(
            str(record["processKey"]),
            terminal_status=terminal_status,
            result=result,
            claim_id=claim_id,
            public_updates={
                **(public_updates or {}),
                "stopResult": {
                    "gracefulRequested": request_graceful,
                    "gracefulSignaled": result.graceful_signaled,
                    "forceRequired": result.force_required,
                    "forceSignaled": result.force_signaled,
                    "graceSeconds": grace_seconds,
                    "ownerEmpty": result.owner_empty,
                },
            },
        )

    def reconcile_manager_loss(
        self,
        *,
        termination_operation_id: str | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        state = self.state.list_records()
        candidates = [
            str(key)
            for key, record in state["processes"].items()
            if record.get("status") in self.state.active_states
            and record.get("internal", {}).get("managerInstanceId") != self.manager_instance_id
        ]
        finalized: list[str] = []
        pending: list[str] = []
        failures: list[dict[str, str]] = []
        for key in candidates:
            if deadline is not None and time.monotonic() >= deadline:
                pending.append(key)
                failures.append({"processKey": key, "failure": "cleanup_deadline_exceeded"})
                continue
            try:
                record = self.state.get(key=key)
                committed = self.finalize(
                    record,
                    reason="manager_lost",
                    terminal_status="manager_lost",
                    public_updates=(
                        {"terminationOperationId": termination_operation_id}
                        if termination_operation_id is not None
                        else None
                    ),
                    deadline=deadline,
                )
                (finalized if committed["status"] == "manager_lost" else pending).append(key)
            except Exception as exc:  # noqa: BLE001
                pending.append(key)
                failures.append({"processKey": key, "failure": type(exc).__name__})
        return {
            "examined": len(candidates),
            "finalized": finalized,
            "pending": pending,
            "failures": failures,
            "cleanupVerified": not pending,
        }

    def shutdown_active(
        self,
        *,
        operation_id: str | None,
        finalize_record: Callable[..., dict[str, Any]],
        watchers: list[threading.Thread],
        deadline: float,
    ) -> dict[str, Any]:
        state = self.state.list_records()
        keys = sorted(
            str(key)
            for key, record in state["processes"].items()
            if record.get("status") in self.state.active_states
        )
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for key in keys:
            try:
                if time.monotonic() >= deadline:
                    raise SupervisorError("manager shutdown deadline 已耗尽")
                record = self.state.get(key=key)
                record = finalize_record(
                    record,
                    reason="manager_shutdown",
                    terminal_status="stopped",
                    public_updates=(
                        {"terminationOperationId": operation_id}
                        if operation_id is not None
                        else None
                    ),
                    deadline=deadline,
                )
                if not record.get("public", {}).get("cleanupVerified"):
                    raise SupervisorError("run owner 清理尚未完成")
                results.append(self.state.public_record(record))
            except Exception as exc:  # noqa: BLE001
                code = exc.code if isinstance(exc, PMError) else "internal_error"
                failures.append({"processKey": key, "code": code})
        live_watchers: list[str] = []
        for watcher in watchers:
            watcher.join(timeout=max(0.0, deadline - time.monotonic()))
            if watcher.is_alive():
                live_watchers.append(watcher.name)
        final_state = self.state.list_records()
        remaining = sorted(
            str(key)
            for key, record in final_state["processes"].items()
            if record.get("status") in self.state.active_states
        )
        cleanup_verified = not failures and not remaining and not live_watchers
        if not cleanup_verified:
            raise SupervisorError(
                "manager shutdown 未能清空全部 run owner",
                diagnostics={
                    "failures": failures,
                    "remainingRunKeys": remaining,
                    "liveWatchers": live_watchers,
                    "ownerEmpty": not remaining,
                },
            )
        return {
            "stopped": results,
            "stoppedRunKeys": [str(result["processKey"]) for result in results],
            "failures": failures,
            "ownerEmpty": True,
            "cleanupVerified": True,
        }
