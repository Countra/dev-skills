"""受管 run 的线性化生命周期核心。"""

from __future__ import annotations

import hashlib
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .atomic import read_json_file
from .config import load_service_config, resolve_service_environment
from .errors import ConflictError, IdentityError, NotFoundError, PMError, StateError, SupervisorError, ValidationError
from .launch import (
    MAX_HOST_MESSAGE_BYTES,
    build_host_spec,
    cleanup_failed_start,
    read_host_message,
    service_host_command,
    validate_target_handshake,
    write_host_spec,
)
from .logs import read_log_tail
from .models import ManagerConfig, ServiceConfig
from .platforms.base import PlatformAdapter, RunOwner
from .probes import wait_for_readiness
from .state import ACTIVE_STATES, StateStore


OWNER_FORCE_SECONDS = 5


@dataclass
class ManagedRun:
    service: ServiceConfig
    owner: RunOwner
    capability: str
    capability_hash: str
    host_state: Path
    finalization_lock: Any = field(default_factory=threading.RLock)


class ProcessManager:
    def __init__(
        self,
        config: ManagerConfig,
        adapter: PlatformAdapter,
        state: StateStore,
        instance_id: str,
        bootstrap_backend: str = "direct",
        bootstrap_selection_reason: str = "direct composition root",
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.state = state
        self.instance_id = instance_id
        self.bootstrap_backend = bootstrap_backend
        self.bootstrap_selection_reason = bootstrap_selection_reason
        self._runs: dict[str, ManagedRun] = {}
        self._watchers: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._accepting_starts = True
        self.reconciled_records = self.state.reconcile_manager_loss(instance_id)

    def health(self) -> dict[str, Any]:
        return {
            "managerReady": True,
            "supervisorReady": True,
            "instance": {"id": self.instance_id},
            "endpointHealthy": True,
        }

    def doctor(self) -> dict[str, Any]:
        return {
            "managerReady": True,
            "supervisorReady": True,
            "instance": {"id": self.instance_id},
            "diagnostics": {
                "bootstrapBackend": self.bootstrap_backend,
                "bootstrapSelectionReason": self.bootstrap_selection_reason,
                **self.adapter.diagnostics(),
                "reconciledManagerLostRecords": self.reconciled_records,
            },
        }


    def start(self, service_path: Path) -> dict[str, Any]:
        service = load_service_config(service_path, self.config)
        environment, secrets_to_redact = resolve_service_environment(service)
        with self._lock:
            if not self._accepting_starts:
                raise ConflictError("manager 正在关闭，不再接受新 start")
            capability = secrets.token_urlsafe(32)
            capability_hash = hashlib.sha256(capability.encode("utf-8")).hexdigest()
            record = self.state.reserve(
                service,
                manager_instance_id=self.instance_id,
                capability_hash=capability_hash,
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
            public_updates = {
                "state": "running",
                "logs": {
                    "stdout": str(Path(record["runDir"]) / "stdout.log"),
                    "stderr": str(Path(record["runDir"]) / "stderr.log"),
                },
            }
            internal_updates = {
                "owner": owner.internal_identity(),
                "hostIdentity": identities["hostIdentity"],
                "targetIdentity": identities["targetIdentity"],
                "hostState": str(host_state),
            }
            record = self.state.update(
                key,
                status="running",
                public_updates=public_updates,
                internal_updates=internal_updates,
            )
            run = ManagedRun(service, owner, capability, capability_hash, host_state)
            with self._lock:
                self._runs[key] = run
            self._start_completion_watcher(key, run)
            return self.state.public_record(record)
        except Exception as exc:
            cleanup_failures = cleanup_failed_start(owner, host)
            try:
                self.state.update(
                    key,
                    status="start_failed",
                    public_updates={
                        "failure": type(exc).__name__,
                        "cleanupVerified": not cleanup_failures,
                    },
                    clear_active=True,
                )
            except Exception as state_exc:  # noqa: BLE001
                cleanup_failures.append(f"state update: {type(state_exc).__name__}")
            if cleanup_failures and hasattr(exc, "add_note"):
                for failure in cleanup_failures:
                    exc.add_note(f"start cleanup warning: {failure}")
            raise

    def _host_state(self, run: ManagedRun) -> dict[str, Any] | None:
        if not run.host_state.exists():
            return None
        value = read_json_file(run.host_state, max_bytes=MAX_HOST_MESSAGE_BYTES)
        if not isinstance(value, dict) or value.get("capabilityHash") != run.capability_hash:
            raise IdentityError("host-state capability identity 不匹配")
        return value

    def _owned_run(self, record: dict[str, Any]) -> ManagedRun:
        key = str(record["processKey"])
        with self._lock:
            run = self._runs.get(key)
        internal = record.get("internal", {})
        if run is None or internal.get("managerInstanceId") != self.instance_id:
            raise IdentityError("run owner 不属于当前 manager")
        if internal.get("capabilityHash") != run.capability_hash:
            raise IdentityError("run capability 不匹配")
        return run

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
                        self.state.update(
                            key,
                            status="cleanup_unverified",
                            public_updates={"failure": type(exc).__name__, "cleanupVerified": False},
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
            host_state = self._host_state(run)
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
            force_required = False
            force_signaled = False
            owner_empty = run.owner.is_empty()
            if not owner_empty:
                if terminal_state == "exited":
                    terminal_state = "contract_violation"
                force_required = True
                force_signaled = run.owner.force_stop()
                owner_empty = self._wait_empty(run.owner, OWNER_FORCE_SECONDS)
            status = str(terminal_state) if owner_empty else "cleanup_unverified"
            record = self.state.update(
                key,
                status=status,
                public_updates={
                    "exitCode": exit_code,
                    "exitedAt": exited_at,
                    "completion": {
                        "forceRequired": force_required,
                        "forceSignaled": force_signaled,
                        "ownerEmpty": owner_empty,
                    },
                    "cleanupVerified": owner_empty,
                },
                clear_active=owner_empty,
            )
            if owner_empty:
                run.owner.close()
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
        run = self._owned_run(record)
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

    @staticmethod
    def _wait_empty(owner: RunOwner, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() <= deadline:
            if owner.is_empty():
                return True
            time.sleep(0.1)
        return owner.is_empty()

    def stop(self, *, service: str | None = None, process_key: str | None = None) -> dict[str, Any]:
        record = self.state.get(service=service, key=process_key)
        key = str(record["processKey"])
        run = self._owned_run(record)
        with run.finalization_lock:
            with self._lock:
                if self._runs.get(key) is not run:
                    return self.state.public_record(self.state.get(key=key))
            self.state.update(key, status="stopping")
            graceful_signaled = run.owner.graceful_stop()
            owner_empty = self._wait_empty(run.owner, float(run.service.stop["graceSeconds"]))
            force_required = False
            force_signaled = False
            if not owner_empty:
                force_required = True
                force_signaled = run.owner.force_stop()
                owner_empty = self._wait_empty(run.owner, OWNER_FORCE_SECONDS)
            host_state = self._host_state(run)
            status = "stopped" if owner_empty else "cleanup_unverified"
            record = self.state.update(
                key,
                status=status,
                public_updates={
                    "exitCode": host_state.get("exitCode") if host_state else None,
                    "exitedAt": host_state.get("exitedAt") if host_state else None,
                    "stopResult": {
                        "gracefulRequested": True,
                        "gracefulSignaled": graceful_signaled,
                        "forceRequired": force_required,
                        "forceSignaled": force_signaled,
                        "graceSeconds": run.service.stop["graceSeconds"],
                        "ownerEmpty": owner_empty,
                    },
                    "cleanupVerified": owner_empty,
                },
                clear_active=owner_empty,
            )
            if owner_empty:
                run.owner.close()
                with self._lock:
                    if self._runs.get(key) is run:
                        self._runs.pop(key, None)
                return self.state.public_record(record)
            raise SupervisorError(
                "run owner 在 graceful-force 生命周期后仍非空",
                diagnostics={"processKey": key, "ownerEmpty": False},
            )

    def restart(self, service_path: Path, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        service_config = load_service_config(service_path, self.config)
        if timeout_seconds is not None and service_config.readiness is None:
            raise ValidationError("restart --timeout 要求 service 配置 readiness")
        previous = None
        try:
            current = self.state.get(service=service_config.name)
            previous = self.stop(process_key=str(current["processKey"]))
            if not previous.get("cleanupVerified"):
                raise SupervisorError("旧 run owner 未清空，拒绝启动 replacement")
        except NotFoundError:
            previous = None
        started = self.start(service_path)
        readiness = None
        if timeout_seconds is not None:
            readiness = self.ready(process_key=started["processKey"], timeout_seconds=timeout_seconds)
        return {"previous": previous, "current": started, "readiness": readiness}

    def prune(
        self,
        *,
        max_inactive: int | None = None,
        dry_run: bool = True,
        keep_runs: bool = False,
    ) -> dict[str, Any]:
        return self.state.prune(max_inactive=max_inactive, dry_run=dry_run, keep_runs=keep_runs)

    def shutdown(self) -> dict[str, Any]:
        with self._lock:
            self._accepting_starts = False
            keys = list(self._runs)
        results: list[dict[str, Any]] = []
        failures: list[str] = []
        for key in keys:
            try:
                results.append(self.stop(process_key=key))
            except PMError as exc:
                failures.append(exc.code)
        with self._lock:
            watchers = list(self._watchers.values())
        for watcher in watchers:
            watcher.join(timeout=5)
        if failures:
            raise SupervisorError(
                "manager shutdown 未能清空全部 run owner",
                diagnostics={"failureCodes": failures, "ownerEmpty": False},
            )
        return {
            "stopped": results,
            "failures": failures,
            "ownerEmpty": not failures,
            "cleanupVerified": not failures,
        }
