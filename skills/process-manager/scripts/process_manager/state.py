"""线程安全、可重建且不保存秘密值的状态存储。"""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .atomic import atomic_write_bytes, atomic_write_json, read_json_file
from .errors import ConflictError, NotFoundError, RuntimeRebuildRequiredError, StateError
from .models import ManagerConfig, ServiceConfig
from .platforms.base import PlatformAdapter
from .runtime import now_text


MAX_STATE_BYTES = 16 * 1024 * 1024
RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
ACTIVE_STATES = {"starting", "running", "stopping", "cleanup_unverified"}
STATE_KEYS = {"schema", "stateRevision", "active", "processes"}
RUN_RECORD_REQUIRED_KEYS = {
    "schema",
    "service",
    "processId",
    "processKey",
    "status",
    "runDir",
    "processFile",
    "createdAt",
    "public",
    "internal",
}
RUN_RECORD_OPTIONAL_KEYS = {"updatedAt"}


def empty_state() -> dict[str, Any]:
    return {"schema": "process-manager", "stateRevision": 0, "active": {}, "processes": {}}


def process_key(service: str, run_id: str) -> str:
    return f"{service}.{run_id}"


class StateStore:
    def __init__(self, config: ManagerConfig, adapter: PlatformAdapter) -> None:
        self.config = config
        self.adapter = adapter
        self.paths = config.paths
        self._lock = threading.RLock()

    def _run_paths(self, service: str, run_id: str) -> tuple[Path, Path]:
        if not SERVICE_NAME_RE.fullmatch(service) or not RUN_ID_RE.fullmatch(run_id):
            raise StateError("run identity 格式无效")
        run_dir = (self.paths.runs / service / run_id).resolve()
        expected_parent = (self.paths.runs / service).resolve()
        if run_dir.parent != expected_parent or run_dir == self.paths.runs.resolve():
            raise StateError("run path 越过 runtime 边界")
        return run_dir, run_dir / "process.json"

    def _validate_record(self, key: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("schema") != "process-manager":
            raise RuntimeRebuildRequiredError("run record 使用旧或未知 runtime schema")
        fields = set(value)
        if not RUN_RECORD_REQUIRED_KEYS <= fields or fields - RUN_RECORD_REQUIRED_KEYS - RUN_RECORD_OPTIONAL_KEYS:
            raise StateError("run record 字段集合无效")
        service = value.get("service")
        run_id = value.get("processId")
        if (
            not isinstance(service, str)
            or not isinstance(run_id, str)
            or key != process_key(service, run_id)
            or value.get("processKey") != key
        ):
            raise StateError("run record identity 不一致")
        run_dir, process_file = self._run_paths(service, run_id)
        if value.get("runDir") != str(run_dir) or value.get("processFile") != str(process_file):
            raise StateError("run record path 不一致")
        if not isinstance(value.get("public"), dict) or not isinstance(value.get("internal"), dict):
            raise StateError("run record public/internal 必须是 object")
        return value

    def _validate_state(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("schema") != "process-manager":
            raise RuntimeRebuildRequiredError("process state 使用旧或未知 runtime schema")
        if set(value) != STATE_KEYS:
            raise StateError("process state 字段集合无效")
        active = value.get("active")
        processes = value.get("processes")
        revision = value.get("stateRevision")
        if not isinstance(active, dict) or not isinstance(processes, dict) or not isinstance(revision, int):
            raise StateError("process state 结构无效")
        for key, record in processes.items():
            self._validate_record(key, record)
        for service, key in active.items():
            if not isinstance(service, str) or not isinstance(key, str) or key not in processes:
                raise StateError("active 索引引用无效")
            record = processes[key]
            if record.get("service") != service or record.get("status") not in ACTIVE_STATES:
                raise StateError("active 索引与 run record 不一致")
        return value

    def _read_candidate(self, path: Path) -> dict[str, Any]:
        return self._validate_state(read_json_file(path, max_bytes=MAX_STATE_BYTES))

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.paths.processes.exists():
                rebuilt = self.rebuild()
                self._save(rebuilt, backup=False)
                return rebuilt
            try:
                return self._read_candidate(self.paths.processes)
            except RuntimeRebuildRequiredError:
                raise
            except StateError:
                backup = None
                if self.paths.processes_backup.exists():
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
        self._validate_state(state)
        if backup and self.paths.processes.exists():
            try:
                current = self._read_candidate(self.paths.processes)
            except StateError:
                current = None
            if current is not None:
                data = (json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
                atomic_write_bytes(self.paths.processes_backup, data)
                self.adapter.secure_file(self.paths.processes_backup)
        atomic_write_json(self.paths.processes, state)
        self.adapter.secure_file(self.paths.processes)

    def save(self, state: dict[str, Any]) -> None:
        with self._lock:
            state["stateRevision"] = int(state.get("stateRevision", 0)) + 1
            self._save(state)

    def rebuild(self) -> dict[str, Any]:
        state = empty_state()
        if not self.paths.runs.exists():
            return state
        candidates: list[dict[str, Any]] = []
        scanned = 0
        for service_dir in sorted(self.paths.runs.iterdir()):
            if service_dir.is_symlink() or not service_dir.is_dir() or not SERVICE_NAME_RE.fullmatch(service_dir.name):
                continue
            for run_dir in sorted(service_dir.iterdir()):
                scanned += 1
                if scanned > 10000:
                    raise StateError("run record 重建扫描超过 10000 项")
                if run_dir.is_symlink() or not run_dir.is_dir() or not RUN_ID_RE.fullmatch(run_dir.name):
                    continue
                process_file = run_dir / "process.json"
                if not process_file.is_file():
                    continue
                try:
                    record = self._validate_record(
                        process_key(service_dir.name, run_dir.name),
                        read_json_file(process_file, max_bytes=MAX_STATE_BYTES),
                    )
                except RuntimeRebuildRequiredError:
                    raise
                except StateError:
                    continue
                candidates.append(record)
        active_by_service: dict[str, list[dict[str, Any]]] = {}
        for record in candidates:
            key = str(record["processKey"])
            state["processes"][key] = record
            if record.get("status") in ACTIVE_STATES:
                active_by_service.setdefault(str(record["service"]), []).append(record)
        for service, records in active_by_service.items():
            if len(records) == 1:
                state["active"][service] = records[0]["processKey"]
                continue
            for record in records:
                record["status"] = "recovery_conflict"
                record["public"]["state"] = "recovery_conflict"
                atomic_write_json(Path(record["processFile"]), record)
                self.adapter.secure_file(Path(record["processFile"]))
        return state

    def reserve(
        self,
        service: ServiceConfig,
        *,
        manager_instance_id: str,
        capability_hash: str,
    ) -> dict[str, Any]:
        with self._lock:
            state = self.load()
            existing_key = state["active"].get(service.name)
            if existing_key:
                existing = state["processes"].get(existing_key, {})
                raise ConflictError(
                    f"service 已有 active run: {service.name}",
                    diagnostics={"processKey": existing_key, "state": existing.get("status")},
                )
            run_id = f"run-{uuid.uuid4().hex}"
            key = process_key(service.name, run_id)
            run_dir, process_file = self._run_paths(service.name, run_id)
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
            atomic_write_json(process_file, record)
            self.adapter.secure_file(process_file)
            state["active"][service.name] = key
            state["processes"][key] = record
            self.save(state)
            return record

    def update(
        self,
        key: str,
        *,
        status: str,
        public_updates: dict[str, Any] | None = None,
        internal_updates: dict[str, Any] | None = None,
        clear_active: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            state = self.load()
            record = state["processes"].get(key)
            if not isinstance(record, dict):
                raise StateError(f"processKey 不存在: {key}")
            record["status"] = status
            record["updatedAt"] = now_text()
            record["public"]["state"] = status
            record["public"].update(public_updates or {})
            record["internal"].update(internal_updates or {})
            if clear_active and state["active"].get(record["service"]) == key:
                state["active"].pop(record["service"], None)
            atomic_write_json(Path(record["processFile"]), record)
            self.adapter.secure_file(Path(record["processFile"]))
            state["processes"][key] = record
            self.save(state)
            return record

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

    def _prune_preview(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "service": record["service"],
                "processKey": record["processKey"],
                "state": record["status"],
                "runDir": record["runDir"],
                "updatedAt": record.get("updatedAt", record["createdAt"]),
            }
            for record in records
        ]

    def _validate_prune_path(self, record: dict[str, Any]) -> tuple[Path, Path]:
        run_dir, process_file = self._run_paths(str(record["service"]), str(record["processId"]))
        if run_dir != Path(record["runDir"]).resolve() or process_file != Path(record["processFile"]).resolve():
            raise StateError("prune run path identity 不一致")
        if run_dir.is_symlink() or not run_dir.is_dir() or not process_file.is_file():
            raise StateError("prune 只允许现存非 symlink 精确 runDir")
        return run_dir, process_file

    def _write_current_backup(self, state: dict[str, Any]) -> None:
        data = (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        atomic_write_bytes(self.paths.processes_backup, data)
        self.adapter.secure_file(self.paths.processes_backup)

    def prune(
        self,
        *,
        max_inactive: int | None = None,
        dry_run: bool = True,
        keep_runs: bool = False,
    ) -> dict[str, Any]:
        limit = self.config.history_max_inactive if max_inactive is None else max_inactive
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 10000:
            raise StateError("maxInactive 必须是 0-10000 范围内整数")
        with self._lock:
            state = self.load()
            inactive = [
                record
                for record in state["processes"].values()
                if isinstance(record, dict) and record.get("status") not in ACTIVE_STATES
            ]
            inactive.sort(
                key=lambda record: (str(record.get("updatedAt", record.get("createdAt", ""))), str(record["processKey"])),
                reverse=True,
            )
            candidates = inactive[limit:]
            preview = self._prune_preview(candidates)
            effective_keep = keep_runs or not self.config.history_delete_run_dirs
            if dry_run or not candidates:
                return {
                    "dryRun": dry_run,
                    "maxInactive": limit,
                    "keepRuns": effective_keep,
                    "candidateCount": len(candidates),
                    "candidates": preview,
                    "applied": False,
                }
            original = deepcopy(state)
            transaction = f"prune-{uuid.uuid4().hex}"
            moved: list[tuple[str, Path, Path]] = []
            state_committed = False
            try:
                for record in candidates:
                    run_dir, process_file = self._validate_prune_path(record)
                    if effective_keep:
                        archived = run_dir / "process.pruned.json"
                        if archived.exists():
                            raise StateError("prune archive 已存在")
                        process_file.replace(archived)
                        moved.append(("record", process_file, archived))
                    else:
                        quarantine_parent = self.paths.tmp / "prune" / transaction / str(record["service"])
                        self.adapter.secure_directory(quarantine_parent)
                        quarantine = quarantine_parent / str(record["processId"])
                        run_dir.replace(quarantine)
                        moved.append(("run", run_dir, quarantine))
                    state["processes"].pop(str(record["processKey"]), None)
                self.save(state)
                state_committed = True
                self._write_current_backup(state)
            except Exception as exc:
                rollback_failures: list[str] = []
                if not state_committed:
                    try:
                        current = self._read_candidate(self.paths.processes)
                        state_committed = set(current["processes"]) == set(state["processes"])
                    except Exception:
                        state_committed = False
                if state_committed:
                    try:
                        self._save(original, backup=False)
                        self._write_current_backup(original)
                    except Exception as rollback_exc:  # noqa: BLE001
                        rollback_failures.append(f"state:{type(rollback_exc).__name__}")
                for _, original_path, moved_path in reversed(moved):
                    try:
                        if moved_path.exists() and not original_path.exists():
                            original_path.parent.mkdir(parents=True, exist_ok=True)
                            moved_path.replace(original_path)
                    except OSError as rollback_exc:
                        rollback_failures.append(f"filesystem:{type(rollback_exc).__name__}")
                raise StateError(
                    "prune transaction 失败",
                    diagnostics={"rollbackFailures": rollback_failures},
                ) from exc
            cleanup_failures: list[str] = []
            deleted_run_dirs = 0
            if not effective_keep:
                for _, original_path, quarantine in moved:
                    try:
                        shutil.rmtree(quarantine)
                        deleted_run_dirs += 1
                        try:
                            original_path.parent.rmdir()
                        except OSError:
                            pass
                    except OSError:
                        cleanup_failures.append(str(quarantine))
            return {
                "dryRun": False,
                "maxInactive": limit,
                "keepRuns": effective_keep,
                "candidateCount": len(candidates),
                "candidates": preview,
                "applied": True,
                "prunedCount": len(candidates),
                "deletedRunDirs": deleted_run_dirs,
                "cleanupVerified": not cleanup_failures,
                "cleanupFailures": cleanup_failures,
            }

    def reconcile_manager_loss(self, current_instance_id: str) -> int:
        with self._lock:
            state = self.load()
            changed = 0
            for key, record in state["processes"].items():
                owner = record.get("internal", {}).get("managerInstanceId")
                if record.get("status") in ACTIVE_STATES and owner != current_instance_id:
                    record["status"] = "manager_lost"
                    record["public"]["state"] = "manager_lost"
                    record["updatedAt"] = now_text()
                    if state["active"].get(record["service"]) == key:
                        state["active"].pop(record["service"], None)
                    atomic_write_json(Path(record["processFile"]), record)
                    self.adapter.secure_file(Path(record["processFile"]))
                    changed += 1
            if changed:
                self.save(state)
            return changed

    @staticmethod
    def public_record(record: dict[str, Any]) -> dict[str, Any]:
        return dict(record.get("public", {}))
