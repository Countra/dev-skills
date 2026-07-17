"""受管 run 的线性化生命周期核心。"""
from __future__ import annotations
import hashlib
import math
import os
import secrets
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from .config import load_service_config, resolve_service_environment
from .errors import ConflictError, IdentityError, NotFoundError, PMError, StateError, SupervisorError, ValidationError
from .launch import (
    build_host_spec, cleanup_failed_start, owned_run, read_host_message, read_managed_host_state,
    service_host_command, validate_target_handshake, write_host_spec,
)
from .logs import read_log_tail
from .manager_start import StartDrainGate
from .models import ManagerConfig, ServiceConfig
from .platforms.base import PlatformAdapter, RunOwner
from .probes import wait_for_readiness
from .run_finalization import ManagedRun, OwnerFinalization, RunFinalizationCoordinator
from .sessions import SessionController
from .state import ACTIVE_STATES, StateStore
MANAGER_SHUTDOWN_SECONDS = 30.0
class ProcessManager:
    def __init__(
        self, config: ManagerConfig, adapter: PlatformAdapter, state: StateStore,
        instance_id: str, *, operation_id: str,
        runtime_fingerprint: str = "0" * 64,
        bootstrap_backend: str = "direct",
        bootstrap_selection_reason: str = "direct composition root",
        workspace_digest: str | None = None,
        session_sweeper: bool = True,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.state = state
        self.instance_id, self.operation_id = instance_id, operation_id
        self.runtime_fingerprint = runtime_fingerprint
        self.bootstrap_backend = bootstrap_backend
        self.bootstrap_selection_reason = bootstrap_selection_reason
        self._runs: dict[str, ManagedRun] = {}
        self._watchers: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._start_gate = StartDrainGate()
        self._finalization = RunFinalizationCoordinator(state, adapter, instance_id)
        digest = workspace_digest or hashlib.sha256(
            os.path.normcase(str(config.workspace_root.resolve())).encode()).hexdigest()
        self._sessions = SessionController(
            state, manager_instance_id=instance_id, workspace_digest=digest,
            finalize_record=self._finalize_run_record,
        )
        self._shutdown_operation_id: str | None = None
        self._shutdown_deadline: float | None = None
        self.reconciled_records = self._finalization.reconcile_manager_loss(deadline=time.monotonic() + MANAGER_SHUTDOWN_SECONDS)
        self.session_reconciliation = self._sessions.reconcile_startup()
        if session_sweeper:
            self._sessions.start_sweeper()
        self._start_gate.open()
    def health(self) -> dict[str, Any]:
        return {
            "managerReady": True, "supervisorReady": True,
            "instance": {"id": self.instance_id}, "operationId": self.operation_id,
            "runtimeFingerprint": self.runtime_fingerprint, "endpointHealthy": True,
        }
    def doctor(self) -> dict[str, Any]:
        return {
            "managerReady": True, "supervisorReady": True,
            "instance": {"id": self.instance_id}, "operationId": self.operation_id,
            "runtimeFingerprint": self.runtime_fingerprint,
            "diagnostics": {
                "bootstrapBackend": self.bootstrap_backend,
                "bootstrapSelectionReason": self.bootstrap_selection_reason,
                **self.adapter.diagnostics(),
                "managerLossReconciliation": self.reconciled_records,
                "sessionReconciliation": self.session_reconciliation, "sessions": self._sessions.diagnostics(),
            },
        }
    def start(
        self, service_path: Path, *, session_id: str | None = None, persistent: bool = False,
    ) -> dict[str, Any]:
        ownership = self._sessions.ownership(session_id, persistent)
        with self._start_gate.admit():
            return self._start(service_path, ownership)
    def _start(self, service_path: Path, ownership: dict[str, Any]) -> dict[str, Any]:
        service = load_service_config(service_path, self.config)
        environment, secrets_to_redact = resolve_service_environment(service)
        capability = secrets.token_urlsafe(32)
        capability_hash = hashlib.sha256(capability.encode("utf-8")).hexdigest()
        record = self._sessions.reserve_run(
            service, capability_hash=capability_hash, session_id=ownership["sessionId"],
            persistent=ownership["kind"] == "persistent",
        )
        key = str(record["processKey"])
        host_state = Path(record["runDir"]) / "host-state.json"
        owner: RunOwner | None = None
        host: subprocess.Popen[str] | None = None
        try:
            command, host_environment = service_host_command(host_state)
            host = self.adapter.spawn_service_host(command, cwd=self.config.workspace_root, environment=host_environment)
            ready = read_host_message(host)
            if ready.get("event") != "host_ready" or ready.get("pid") != host.pid:
                raise IdentityError("service-host ready identity 不匹配")
            owner = self.adapter.create_run_owner(record["processId"], host, capability_hash)
            record = self.state.update(
                key,
                status="starting",
                internal_updates={
                    "owner": owner.internal_identity(),
                    "hostIdentity": self.adapter.process_identity(host.pid),
                    "targetIdentity": None,
                    "hostState": str(host_state),
                },
            )
            spec = build_host_spec(
                self.instance_id,
                service,
                record,
                owner,
                capability,
                capability_hash,
                environment,
                secrets_to_redact,
            )
            write_host_spec(host, spec)
            identities = validate_target_handshake(self.adapter, owner, host, capability_hash)
            record = self.state.update(
                key,
                status="starting",
                internal_updates={
                    "owner": identities["ownerIdentity"],
                    "targetIdentity": identities["targetIdentity"],
                },
            )
            record = self.state.update(
                key,
                status="running",
                public_updates={
                    "logs": {
                        "stdout": str(Path(record["runDir"]) / "stdout.log"),
                        "stderr": str(Path(record["runDir"]) / "stderr.log"),
                    },
                },
            )
            run = ManagedRun(service, owner, capability, capability_hash, host_state)
            with self._lock:
                self._runs[key] = run
            self._start_completion_watcher(key, run)
            return self.state.public_record(record)
        except Exception as exc:
            if owner is not None:
                cleanup_result = self._finalization.owner_finalizer.finalize_live(
                    owner,
                    grace_seconds=0.0,
                    request_graceful=False,
                )
                if not cleanup_result.cleanup_verified:
                    cleanup_result = OwnerFinalization(
                        cleanup_result.owner_empty,
                        cleanup_result.cleanup_verified,
                        cleanup_result.graceful_signaled,
                        cleanup_result.force_required,
                        cleanup_result.force_signaled,
                        cleanup_result.accounting,
                        "start_cleanup_failed",
                    )
                cleanup_failures = [] if cleanup_result.cleanup_verified else [cleanup_result.error or "owner_cleanup_unverified"]
            else:
                cleanup_failures = cleanup_failed_start(None, host)
                cleanup_result = OwnerFinalization(
                    not cleanup_failures,
                    not cleanup_failures,
                    False,
                    False,
                    False,
                    {},
                    None if not cleanup_failures else "start_cleanup_failed",
                )
            try:
                current = self.state.get(key=key)
                self._finalization.commit_result(
                    current,
                    terminal_status="start_failed",
                    result=cleanup_result,
                    public_updates={"failure": type(exc).__name__},
                    request_graceful=False,
                    grace_seconds=0.0,
                    reason="start_failed",
                )
            except Exception as state_exc:  # noqa: BLE001
                cleanup_failures.append(f"state update: {type(state_exc).__name__}")
            if cleanup_failures and hasattr(exc, "add_note"):
                for failure in cleanup_failures:
                    exc.add_note(f"start cleanup warning: {failure}")
            raise
    def _start_completion_watcher(self, key: str, run: ManagedRun) -> None:
        def watch() -> None:
            try:
                run.owner.host.wait()
                record = self.state.get(key=key)
                self._refresh(key, record)
            except Exception as exc:  # noqa: BLE001
                try:
                    record = self.state.get(key=key)
                    if record.get("status") in ACTIVE_STATES:
                        self._finalization.finalize(
                            record,
                            reason="completion_watcher_failed",
                            terminal_status="host_failed",
                            live_run=run,
                            public_updates={"failure": type(exc).__name__},
                            request_graceful=False,
                        )
                except Exception:
                    pass
            finally:
                with self._lock:
                    if self._watchers.get(key) is threading.current_thread():
                        self._watchers.pop(key, None)
        watcher = threading.Thread(target=watch, name=f"pm-watch-{key[-12:]}", daemon=True)
        with self._lock:
            self._watchers[key] = watcher
        watcher.start()
    def _refresh(self, key: str, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(key)
        if run is None:
            return record
        with run.finalization_lock:
            with self._lock:
                if self._runs.get(key) is not run:
                    return self.state.get(key=key)
            host_state = read_managed_host_state(run, self.adapter)
            host_exited = run.owner.host.poll() is not None
            if host_state is None or host_state.get("state") == "running":
                if not host_exited:
                    return record
                terminal_state = "host_failed"
                exit_code = run.owner.host.poll()
                exited_at = None
            else:
                terminal_state = host_state.get("state")
                if terminal_state not in {"exited", "manager_lost", "contract_violation"}:
                    raise IdentityError("host-state terminal state 无效")
                exit_code = host_state.get("exitCode")
                exited_at = host_state.get("exitedAt")
            record = self._finalization.finalize(
                record,
                reason=f"host_{terminal_state}",
                terminal_status=str(terminal_state),
                live_run=run,
                request_graceful=False,
                public_updates={
                    "exitCode": exit_code,
                    "exitedAt": exited_at,
                },
            )
            if record["status"] not in ACTIVE_STATES:
                with self._lock:
                    if self._runs.get(key) is run:
                        self._runs.pop(key, None)
            return record
    def status(self, *, service: str | None = None, process_key: str | None = None) -> dict[str, Any]:
        record = self.state.get(service=service, key=process_key)
        record = self._refresh(str(record["processKey"]), record)
        return self.state.public_record(record)
    def list_processes(self, *, include_history: bool = False) -> dict[str, Any]:
        state = self.state.list_records()
        for key in list(state["active"].values()):
            record = state["processes"].get(key)
            if isinstance(record, dict):
                self._refresh(key, record)
        state = self.state.list_records()
        running = {
            key: self.state.public_record(record)
            for key, record in state["processes"].items()
            if record.get("status") in ACTIVE_STATES
        }
        result: dict[str, Any] = {"active": dict(state["active"]), "running": running}
        if include_history:
            result["processes"] = {
                key: self.state.public_record(record) for key, record in state["processes"].items()
            }
        return result
    def logs(
        self,
        *,
        service: str | None = None,
        process_key: str | None = None,
        stream: str = "stdout",
        tail_lines: int = 80,
        max_bytes: int = 262144,
    ) -> dict[str, Any]:
        if stream not in {"stdout", "stderr"}:
            raise ValidationError("stream 只允许 stdout 或 stderr")
        record = self.state.get(service=service, key=process_key)
        record = self._refresh(str(record["processKey"]), record)
        run_dir = Path(record["runDir"]).resolve()
        expected = run_dir / f"{stream}.log"
        configured = record.get("public", {}).get("logs", {}).get(stream)
        if configured != str(expected) or expected.is_symlink():
            raise IdentityError("日志路径与 run identity 不匹配")
        log_config = record.get("public", {}).get("serviceConfig", {}).get("logs", {})
        value = read_log_tail(
            expected,
            int(log_config.get("backups", 0)),
            tail_lines=tail_lines,
            max_bytes=max_bytes,
        )
        return {
            "service": record["service"],
            "processKey": record["processKey"],
            "state": record["status"],
            "stream": stream,
            **value,
        }
    def ready(
        self,
        *,
        service: str | None = None,
        process_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        record = self.state.get(service=service, key=process_key)
        key = str(record["processKey"])
        record = self._refresh(key, record)
        if record.get("status") != "running":
            raise ConflictError("只有 running process 可以执行 readiness")
        run = owned_run(self._runs, self._lock, record, self.instance_id)
        readiness = run.service.readiness
        if readiness is None:
            raise ValidationError("service 未配置 readiness，不能声明 ready")
        stream = str(readiness.get("stream", "stdout"))
        log_path = Path(record["runDir"]) / f"{stream}.log"
        def is_running() -> bool:
            try:
                current = self.state.get(key=key)
                current = self._refresh(key, current)
                return current.get("status") == "running"
            except PMError:
                return False
        result = wait_for_readiness(
            readiness,
            log_path=log_path,
            log_backups=run.service.logs["backups"],
            is_running=is_running,
            timeout_override=timeout_seconds,
        )
        with run.finalization_lock:
            current = self.state.get(key=key)
            current = self._refresh(key, current)
            if current.get("status") != "running":
                raise ConflictError("managed process 在 readiness 提交前退出")
            record = self.state.update(
                key,
                status="running",
                public_updates={"readiness": result, "observed": result["observed"]},
            )
        return {"processKey": key, **result, "state": record["status"]}
    def _finalize_run_record(
        self,
        record: dict[str, Any],
        *,
        reason: str,
        terminal_status: str,
        public_updates: dict[str, Any] | None = None,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        key = str(record["processKey"])
        if record.get("status") not in ACTIVE_STATES:
            return record
        with self._lock:
            run = self._runs.get(key)
        current = self.state.get(key=key)
        committed = self._finalization.finalize(
            current,
            reason=reason,
            terminal_status=terminal_status,
            live_run=run,
            public_updates=public_updates,
            deadline=deadline,
        )
        if committed.get("status") not in ACTIVE_STATES and run is not None:
            with self._lock:
                if self._runs.get(key) is run:
                    self._runs.pop(key, None)
        return committed
    def stop(self, *, service: str | None = None, process_key: str | None = None) -> dict[str, Any]:
        record = self.state.get(service=service, key=process_key)
        record = self._finalize_run_record(
            record,
            reason="stop_requested",
            terminal_status="stopped",
        )
        if record.get("public", {}).get("cleanupVerified"):
            return self.state.public_record(record)
        key = str(record["processKey"])
        raise SupervisorError(
            "run owner 清理尚未完成",
            diagnostics={
                "processKey": key,
                "ownerEmpty": record.get("public", {}).get("ownerEmpty", False),
                "cleanupError": record.get("public", {}).get("cleanupError"),
            },
        )
    def restart(
        self, service_path: Path, *, timeout_seconds: float | None = None,
        session_id: str | None = None, persistent: bool = False,
    ) -> dict[str, Any]:
        service_config = load_service_config(service_path, self.config)
        if timeout_seconds is not None and service_config.readiness is None:
            raise ValidationError("restart --timeout 要求 service 配置 readiness")
        previous = None
        requested = None
        if session_id is not None or persistent:
            requested = self._sessions.ownership(session_id, persistent)
        try:
            current = self.state.get(service=service_config.name)
            ownership = dict(current["ownership"])
            if requested is not None and requested != ownership:
                raise ValidationError("service restart 不能改变原 ownership")
            previous = self.stop(process_key=str(current["processKey"]))
            if not previous.get("cleanupVerified"):
                raise SupervisorError("旧 run owner 未清空，拒绝启动 replacement")
        except NotFoundError:
            previous = None
            ownership = requested or self._sessions.ownership(None, False)
        started = self.start(
            service_path, session_id=ownership["sessionId"],
            persistent=ownership["kind"] == "persistent")
        readiness = None
        if timeout_seconds is not None:
            readiness = self.ready(process_key=started["processKey"], timeout_seconds=timeout_seconds)
        return {"previous": previous, "current": started, "readiness": readiness}
    def open_session(self, *, kind: str, ttl_seconds: int, holder: str) -> dict[str, Any]:
        return self._sessions.open(kind=kind, ttl_seconds=ttl_seconds, holder=holder)
    def renew_session(self, session_id: str, *, ttl_seconds: int) -> dict[str, Any]:
        return self._sessions.renew(session_id, ttl_seconds=ttl_seconds)
    def session_status(self, session_id: str) -> dict[str, Any]:
        return self._sessions.status(session_id)
    def close_session(self, session_id: str) -> dict[str, Any]:
        return self._sessions.close(session_id)
    def prune(
        self, *, max_inactive: int | None = None, dry_run: bool = True,
        keep_runs: bool = False,
    ) -> dict[str, Any]:
        return self.state.prune(max_inactive=max_inactive, dry_run=dry_run, keep_runs=keep_runs)
    def accept_shutdown(
        self, *, operation_id: str, timeout_seconds: float = MANAGER_SHUTDOWN_SECONDS,
    ) -> dict[str, Any]:
        try:
            canonical_operation_id = uuid.UUID(operation_id).hex
        except (ValueError, AttributeError) as exc:
            raise ValidationError("manager shutdown operationId 无效") from exc
        if operation_id != canonical_operation_id:
            raise ValidationError("manager shutdown operationId 不是 canonical UUID")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or not 0 < timeout_seconds <= 3600
        ):
            raise ValidationError("manager shutdown timeoutSeconds 必须在 (0, 3600] 范围内")
        requested_deadline = time.monotonic() + float(timeout_seconds)
        with self._lock:
            if (
                self._shutdown_operation_id is not None
                and self._shutdown_operation_id != operation_id
            ):
                raise ConflictError("manager 已接受其它 shutdown operation")
            self._start_gate.close()
            self._shutdown_operation_id = operation_id
            if self._shutdown_deadline is None:
                self._shutdown_deadline = requested_deadline
            else:
                self._shutdown_deadline = min(self._shutdown_deadline, requested_deadline)
        return {"shutdownAccepted": True, "operationId": operation_id}
    def shutdown(self) -> dict[str, Any]:
        self._start_gate.close()
        with self._lock:
            operation_id = self._shutdown_operation_id
            deadline = self._shutdown_deadline or time.monotonic() + MANAGER_SHUTDOWN_SECONDS
            self._shutdown_deadline = deadline
        self._start_gate.wait_for_drain(deadline)
        with self._lock:
            watchers = list(self._watchers.values())
        self._sessions.begin_shutdown(deadline=deadline)
        session_result: dict[str, Any]
        try:
            result = self._finalization.shutdown_active(
                operation_id=operation_id, finalize_record=self._finalize_run_record,
                watchers=watchers, deadline=deadline)
        finally:
            session_result = self._sessions.finish_shutdown(deadline=deadline)
        if not session_result["cleanupVerified"]:
            raise SupervisorError("manager shutdown 后仍有 session cleanup pending", diagnostics=session_result)
        return {**result, "sessions": session_result}
