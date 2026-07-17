"""线程安全、可重建且不保存秘密值的状态存储。"""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .atomic import InterProcessFileLock, atomic_write_bytes, atomic_write_json, read_json_file
from .errors import (
    ConflictError,
    NotFoundError,
    OperationConflictError,
    RuntimeRebuildRequiredError,
    StateError,
)
from .models import (
    ACTIVE_STATES,
    ManagerConfig,
    ServiceConfig,
    StateSchema,
    process_key,
)
from .platforms.base import PlatformAdapter
from .resources import PruneCoordinator, StateRebuilder
from .runtime import now_text, prepare_runtime_lock


MAX_STATE_BYTES = 16 * 1024 * 1024
MAX_STATE_TRANSACTION_BYTES = 32 * 1024 * 1024
STATE_TRANSACTION_KEYS = {"schema", "state", "records"}


class StateStore:
    _lock_guard = threading.Lock()
    _repository_locks: dict[str, threading.RLock] = {}

    def __init__(self, config: ManagerConfig, adapter: PlatformAdapter) -> None:
        self.config = config
        self.adapter = adapter
        self.paths = config.paths
        self.schema = StateSchema(self.paths)
        lock_key = str(config.paths.repository_lock.resolve())
        with self._lock_guard:
            self._lock = self._repository_locks.setdefault(lock_key, threading.RLock())
        self._transaction_state = threading.local()

    @property
    def active_states(self) -> set[str]:
        return ACTIVE_STATES

    @property
    def max_state_bytes(self) -> int:
        return MAX_STATE_BYTES

    @property
    def _pending_transaction(self) -> Path:
        return self.paths.state_root / "processes.pending.json"

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            depth = int(getattr(self._transaction_state, "depth", 0))
            if depth:
                self._transaction_state.depth = depth + 1
                try:
                    yield
                finally:
                    self._transaction_state.depth = depth
                return
            self._transaction_state.depth = 1
            try:
                prepare_runtime_lock(self.paths.repository_lock, self.adapter)
                with InterProcessFileLock(self.paths.repository_lock, timeout=10):
                    self._recover_pending_transaction()
                    yield
            finally:
                self._transaction_state.depth = 0

    def _read_candidate(self, path: Path) -> dict[str, Any]:
        self.adapter.verify_file(path)
        return self.schema.validate_state(read_json_file(path, max_bytes=MAX_STATE_BYTES))

    def _read_pending_transaction(self) -> dict[str, Any] | None:
        path = self.adapter.validate_runtime_path(self._pending_transaction)
        if not path.exists():
            return None
        self.adapter.verify_file(path)
        value = read_json_file(path, max_bytes=MAX_STATE_TRANSACTION_BYTES)
        if not isinstance(value, dict) or set(value) != STATE_TRANSACTION_KEYS:
            raise StateError("process state pending transaction 字段集合无效")
        if value.get("schema") != "process-manager-state-transaction":
            raise RuntimeRebuildRequiredError("process state pending transaction 使用旧或未知 schema")
        state = self.schema.validate_state(value.get("state"))
        records = value.get("records")
        if not isinstance(records, list) or len(records) != 1:
            raise StateError("process state pending transaction record 数量无效")
        record = records[0]
        key = record.get("processKey") if isinstance(record, dict) else None
        if not isinstance(key, str) or self.schema.validate_record(key, record) != state["processes"].get(key):
            raise StateError("process state pending transaction record 与中央状态不一致")
        return {"schema": value["schema"], "state": state, "records": records}

    def _apply_pending_transaction(self, value: dict[str, Any]) -> None:
        for record in value["records"]:
            _, process_file = self.schema.run_paths(str(record["service"]), str(record["processId"]))
            atomic_write_json(self.adapter.validate_runtime_path(process_file), record)
            self.adapter.secure_file(process_file)
        self._save(value["state"])
        self.adapter.validate_runtime_path(self._pending_transaction).unlink(missing_ok=True)

    def _recover_pending_transaction(self) -> None:
        pending = self._read_pending_transaction()
        if pending is not None:
            self._apply_pending_transaction(pending)

    def _commit_record(self, state: dict[str, Any], record: dict[str, Any]) -> None:
        state["stateRevision"] = int(state.get("stateRevision", 0)) + 1
        self.schema.validate_state(state)
        pending = {
            "schema": "process-manager-state-transaction",
            "state": state,
            "records": [record],
        }
        path = self.adapter.validate_runtime_path(self._pending_transaction)
        atomic_write_json(path, pending)
        self.adapter.secure_file(path)
        self._apply_pending_transaction(pending)

    def load(self) -> dict[str, Any]:
        with self._lock:
            pending = self._read_pending_transaction()
            if pending is not None:
                return pending["state"]
            if not self.adapter.validate_runtime_path(self.paths.processes).exists():
                rebuilt = self.rebuild()
                self._save(rebuilt, backup=False)
                return rebuilt
            try:
                return self._read_candidate(self.paths.processes)
            except RuntimeRebuildRequiredError:
                raise
            except StateError:
                backup = None
                if self.adapter.validate_runtime_path(self.paths.processes_backup).exists():
                    try:
                        backup = self._read_candidate(self.paths.processes_backup)
                    except RuntimeRebuildRequiredError:
                        raise
                    except StateError:
                        backup = None
                rebuilt = self.rebuild()
                recovered = rebuilt if rebuilt["processes"] or backup is None else backup
                self._save(recovered, backup=False)
                return recovered

    def _save(self, state: dict[str, Any], *, backup: bool = True) -> None:
        self.schema.validate_state(state)
        if backup and self.adapter.validate_runtime_path(self.paths.processes).exists():
            try:
                current = self._read_candidate(self.paths.processes)
            except StateError:
                current = None
            if current is not None:
                data = (json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
                atomic_write_bytes(self.adapter.validate_runtime_path(self.paths.processes_backup), data)
                self.adapter.secure_file(self.paths.processes_backup)
        atomic_write_json(self.adapter.validate_runtime_path(self.paths.processes), state)
        self.adapter.secure_file(self.paths.processes)

    def save(self, state: dict[str, Any]) -> None:
        with self.transaction():
            state["stateRevision"] = int(state.get("stateRevision", 0)) + 1
            self._save(state)

    def rebuild(self) -> dict[str, Any]:
        return StateRebuilder(self).run()

    def reserve(
        self,
        service: ServiceConfig,
        *,
        manager_instance_id: str,
        capability_hash: str,
    ) -> dict[str, Any]:
        with self.transaction():
            state = self.load()
            if state["intakeFence"] is not None:
                raise ConflictError(
                    "manager intake 已关闭，拒绝创建新 run",
                    diagnostics={"intakeFence": dict(state["intakeFence"])},
                )
            existing_key = state["active"].get(service.name)
            if existing_key:
                existing = state["processes"].get(existing_key, {})
                raise ConflictError(
                    f"service 已有 active run: {service.name}",
                    diagnostics={"processKey": existing_key, "state": existing.get("status")},
                )
            run_id = f"run-{uuid.uuid4().hex}"
            key = process_key(service.name, run_id)
            run_dir, process_file = self.schema.run_paths(service.name, run_id)
            self.adapter.secure_directory(run_dir.parent)
            self.adapter.secure_directory(run_dir)
            record = {
                "schema": "process-manager",
                "service": service.name,
                "processId": run_id,
                "processKey": key,
                "status": "starting",
                "runDir": str(run_dir),
                "processFile": str(process_file),
                "createdAt": now_text(),
                "recordRevision": 1,
                "cleanupClaim": None,
                "public": {
                    "service": service.name,
                    "processKey": key,
                    "state": "starting",
                    "serviceConfig": service.public_summary(),
                },
                "internal": {
                    "managerInstanceId": manager_instance_id,
                    "capabilityHash": capability_hash,
                    "servicePath": str(service.source_path),
                },
            }
            state["active"][service.name] = key
            state["processes"][key] = record
            state["workGeneration"] += 1
            self._commit_record(state, record)
            return record

    def update(
        self,
        key: str,
        *,
        status: str,
        public_updates: dict[str, Any] | None = None,
        internal_updates: dict[str, Any] | None = None,
        record_updates: dict[str, Any] | None = None,
        clear_active: bool = False,
        expected_revision: int | None = None,
        expected_claim_id: str | None = None,
    ) -> dict[str, Any]:
        with self.transaction():
            state = self.load()
            record = state["processes"].get(key)
            if not isinstance(record, dict):
                raise StateError(f"processKey 不存在: {key}")
            if expected_revision is not None and record.get("recordRevision") != expected_revision:
                raise ConflictError(
                    "run record revision 已变化",
                    diagnostics={
                        "processKey": key,
                        "expectedRevision": expected_revision,
                        "actualRevision": record.get("recordRevision"),
                    },
                )
            claim = record.get("cleanupClaim")
            if expected_claim_id is not None and (
                not isinstance(claim, dict) or claim.get("claimId") != expected_claim_id
            ):
                raise ConflictError("run cleanup claim 已变化", diagnostics={"processKey": key})
            was_active = record.get("status") in ACTIVE_STATES
            record["status"] = status
            record["updatedAt"] = now_text()
            record["recordRevision"] = int(record["recordRevision"]) + 1
            record["public"]["state"] = status
            record["public"].update(public_updates or {})
            record["internal"].update(internal_updates or {})
            for name, value in (record_updates or {}).items():
                if name not in {"cleanupClaim"}:
                    raise StateError(f"不允许更新 run 顶层字段: {name}")
                record[name] = value
            is_active = status in ACTIVE_STATES
            if clear_active and is_active:
                raise StateError("active 状态不能清除 active 索引")
            if clear_active and state["active"].get(record["service"]) == key:
                state["active"].pop(record["service"], None)
            if was_active != is_active:
                state["workGeneration"] += 1
            state["processes"][key] = record
            self._commit_record(state, record)
            return record

    def claim_finalization(
        self,
        key: str,
        *,
        reason: str,
        manager_instance_id: str,
        claim_seconds: float = 30.0,
        takeover_inspected: bool = False,
    ) -> dict[str, Any]:
        with self.transaction():
            record = self.get(key=key)
            if record.get("status") not in ACTIVE_STATES:
                return record
            existing = record.get("cleanupClaim")
            now = datetime.now(timezone.utc)
            if isinstance(existing, dict):
                try:
                    deadline = datetime.fromisoformat(str(existing["deadlineAt"])).astimezone(timezone.utc)
                except (ValueError, TypeError) as exc:
                    raise StateError("run cleanup claim deadline 无效") from exc
                if existing.get("managerInstanceId") == manager_instance_id and deadline > now:
                    return record
                if deadline > now or not takeover_inspected:
                    raise ConflictError(
                        "run 已由另一个 finalizer claim",
                        diagnostics={
                            "processKey": key,
                            "claimId": existing.get("claimId"),
                            "deadlineAt": existing.get("deadlineAt"),
                        },
                    )
            attempt = record.get("public", {}).get("cleanupAttempt", 0)
            if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
                raise StateError("run cleanupAttempt 无效")
            claim = {
                "claimId": uuid.uuid4().hex,
                "managerInstanceId": manager_instance_id,
                "claimedAt": now.isoformat(),
                "deadlineAt": (now + timedelta(seconds=max(1.0, claim_seconds))).isoformat(),
            }
            return self.update(
                key,
                status="terminating",
                public_updates={
                    "terminationReason": reason,
                    "cleanupAttempt": attempt + 1,
                    "cleanupError": None,
                    "ownerEmpty": False,
                    "cleanupVerified": False,
                    "finalizedAt": None,
                },
                record_updates={"cleanupClaim": claim},
                expected_revision=int(record["recordRevision"]),
            )

    def commit_finalization(
        self,
        key: str,
        *,
        terminal_status: str,
        result: Any,
        claim_id: str,
        public_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(terminal_status, str) or not terminal_status or terminal_status in ACTIVE_STATES:
            raise StateError("run terminal status 无效")
        completed = result.owner_empty and result.cleanup_verified
        updates = {
            **(public_updates or {}),
            "cleanupError": result.error,
            "ownerEmpty": result.owner_empty,
            "cleanupVerified": result.cleanup_verified,
            "finalizedAt": now_text() if completed else None,
        }
        return self.update(
            key,
            status=terminal_status if completed else "terminating",
            public_updates=updates,
            internal_updates={"ownerAccounting": result.accounting},
            record_updates={"cleanupClaim": None},
            clear_active=completed,
            expected_claim_id=claim_id,
        )

    def get(self, *, service: str | None = None, key: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self.load()
            selected = key or (state["active"].get(service) if service else None)
            if not selected or selected not in state["processes"]:
                raise NotFoundError("未找到 managed process")
            return state["processes"][selected]

    def list_records(self) -> dict[str, Any]:
        with self._lock:
            return self.load()

    def work_summary(self) -> dict[str, Any]:
        state = self.load()
        active_keys = sorted(
            str(key)
            for key, record in state["processes"].items()
            if record.get("status") in ACTIVE_STATES
        )
        return {
            "workGeneration": state["workGeneration"],
            "intakeFence": dict(state["intakeFence"]) if state["intakeFence"] else None,
            "activeRunKeys": active_keys,
        }

    def stopped_run_keys(self, operation_id: str) -> list[str]:
        records = self.list_records()["processes"]
        return sorted(
            str(key)
            for key, record in records.items()
            if record.get("public", {}).get("terminationOperationId") == operation_id
        )

    def install_intake_fence(
        self,
        *,
        operation_id: str,
        kind: str,
        expected_generation: int,
    ) -> dict[str, Any]:
        with self.transaction():
            state = self.load()
            existing = state["intakeFence"]
            if existing is not None:
                if (
                    existing.get("operationId") == operation_id
                    and existing.get("kind") == kind
                    and existing.get("expectedWorkGeneration") == expected_generation
                ):
                    return dict(existing)
                raise ConflictError("存在其它 intake fence", diagnostics={"intakeFence": existing})
            if state["workGeneration"] != expected_generation:
                raise ConflictError(
                    "destructive operation 的 work generation 已变化",
                    diagnostics={
                        "expectedWorkGeneration": expected_generation,
                        "actualWorkGeneration": state["workGeneration"],
                    },
                )
            fence = {
                "operationId": operation_id,
                "kind": kind,
                "expectedWorkGeneration": expected_generation,
                "installedAt": now_text(),
            }
            state["intakeFence"] = fence
            self.save(state)
            return dict(fence)

    def clear_intake_fence(self, operation_id: str) -> None:
        with self.transaction():
            state = self.load()
            fence = state["intakeFence"]
            if fence is None:
                return
            if fence.get("operationId") != operation_id:
                raise ConflictError(
                    "拒绝清除 foreign intake fence",
                    diagnostics={"intakeFence": fence},
                )
            state["intakeFence"] = None
            self.save(state)

    def clear_terminal_intake_fence(self, operations: Any) -> None:
        """仅在匹配 operation 已终态且 owner 为空时清除 fence。"""

        with self.transaction():
            summary = self.work_summary()
            fence = summary["intakeFence"]
            if fence is None:
                return
            operation = operations.read()
            if operation is None or operation["operationId"] != fence["operationId"]:
                raise OperationConflictError(
                    "intake fence 与当前 operation 不匹配",
                    diagnostics={"intakeFence": fence},
                    recommended_action="doctor",
                )
            if operation["state"] == "pending":
                return
            if summary["activeRunKeys"]:
                raise OperationConflictError(
                    "terminal operation 尚有 active run，拒绝清除 intake fence",
                    diagnostics={"intakeFence": fence, "activeRunKeys": summary["activeRunKeys"]},
                    recommended_action="doctor",
                )
            self.clear_intake_fence(str(operation["operationId"]))

    def prune(
        self,
        *,
        max_inactive: int | None = None,
        dry_run: bool = True,
        keep_runs: bool = False,
    ) -> dict[str, Any]:
        return PruneCoordinator(self).run(
            max_inactive=max_inactive,
            dry_run=dry_run,
            keep_runs=keep_runs,
        )

    @staticmethod
    def public_record(record: dict[str, Any]) -> dict[str, Any]:
        return dict(record.get("public", {}))
