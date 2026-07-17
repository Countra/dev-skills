"""既有 history prune 事务的独立实现。"""

from __future__ import annotations

import json
import shutil
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .atomic import atomic_write_bytes, read_json_file
from .errors import RuntimeRebuildRequiredError, StateError
from .models import RUN_ID_RE, SERVICE_NAME_RE, empty_state, process_key


class StateRebuilder:
    """从受限 run 目录重建中央索引，并保留冲突证据。"""

    def __init__(self, store: Any) -> None:
        self.store = store

    def run(self) -> dict[str, Any]:
        state = empty_state()
        adapter = self.store.adapter
        runs = self.store.paths.runs
        adapter.validate_runtime_path(runs)
        if not runs.exists():
            return state
        adapter.verify_directory(runs)
        candidates: list[dict[str, Any]] = []
        scanned = 0
        for service_dir in sorted(runs.iterdir()):
            if not SERVICE_NAME_RE.fullmatch(service_dir.name) or not adapter.validate_runtime_path(service_dir).is_dir():
                continue
            adapter.verify_directory(service_dir)
            for run_dir in sorted(service_dir.iterdir()):
                scanned += 1
                if scanned > 10000:
                    raise StateError("run record 重建扫描超过 10000 项")
                if not RUN_ID_RE.fullmatch(run_dir.name) or not adapter.validate_runtime_path(run_dir).is_dir():
                    continue
                adapter.verify_directory(run_dir)
                process_file = run_dir / "process.json"
                if not adapter.validate_runtime_path(process_file).is_file():
                    continue
                try:
                    adapter.verify_file(process_file)
                    record = self.store.schema.validate_record(
                        process_key(service_dir.name, run_dir.name),
                        read_json_file(process_file, max_bytes=self.store.max_state_bytes),
                    )
                except RuntimeRebuildRequiredError:
                    raise
                except StateError as exc:
                    raise StateError(
                        "合法 run 路径中的 process record 损坏",
                        diagnostics={"processFile": str(process_file), "failure": type(exc).__name__},
                    ) from exc
                candidates.append(record)
        active_by_service: dict[str, list[dict[str, Any]]] = {}
        for record in candidates:
            key = str(record["processKey"])
            state["processes"][key] = record
            if record.get("status") in self.store.active_states:
                active_by_service.setdefault(str(record["service"]), []).append(record)
        state["workGeneration"] = sum(int(record["recordRevision"]) for record in candidates)
        for service, records in active_by_service.items():
            if len(records) == 1:
                state["active"][service] = records[0]["processKey"]
                continue
            keys = sorted(str(record["processKey"]) for record in records)
            raise StateError(
                f"service 存在多个 active owner，拒绝丢弃清理证据: {service}",
                diagnostics={"processKeys": keys},
            )
        return state


class PruneCoordinator:
    """保持既有 prune 行为，资源配额与 GC 在后续阶段实现。"""

    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def _preview(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    def _validate_path(self, record: dict[str, Any]) -> tuple[Path, Path]:
        run_dir, process_file = self.store.schema.run_paths(
            str(record["service"]),
            str(record["processId"]),
        )
        if run_dir != Path(record["runDir"]) or process_file != Path(record["processFile"]):
            raise StateError("prune run path identity 不一致")
        run_dir = self.store.adapter.validate_runtime_path(run_dir)
        process_file = self.store.adapter.validate_runtime_path(process_file)
        if not run_dir.is_dir() or not process_file.is_file():
            raise StateError("prune 只允许现存非 symlink 精确 runDir")
        return run_dir, process_file

    def _write_backup(self, state: dict[str, Any]) -> None:
        data = (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        path = self.store.adapter.validate_runtime_path(self.store.paths.processes_backup)
        atomic_write_bytes(path, data)
        self.store.adapter.secure_file(self.store.paths.processes_backup)

    def run(
        self,
        *,
        max_inactive: int | None,
        dry_run: bool,
        keep_runs: bool,
    ) -> dict[str, Any]:
        limit = self.store.config.history_max_inactive if max_inactive is None else max_inactive
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 10000:
            raise StateError("maxInactive 必须是 0-10000 范围内整数")
        with self.store.transaction():
            state = self.store.load()
            inactive = [
                record
                for record in state["processes"].values()
                if isinstance(record, dict) and record.get("status") not in self.store.active_states
            ]
            inactive.sort(
                key=lambda record: (
                    str(record.get("updatedAt", record.get("createdAt", ""))),
                    str(record["processKey"]),
                ),
                reverse=True,
            )
            candidates = inactive[limit:]
            preview = self._preview(candidates)
            effective_keep = keep_runs or not self.store.config.history_delete_run_dirs
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
                    run_dir, process_file = self._validate_path(record)
                    if effective_keep:
                        archived = run_dir / "process.pruned.json"
                        if archived.exists():
                            raise StateError("prune archive 已存在")
                        process_file.replace(archived)
                        moved.append(("record", process_file, archived))
                    else:
                        quarantine_parent = self.store.paths.tmp / "prune" / transaction / str(record["service"])
                        self.store.adapter.secure_directory(quarantine_parent)
                        quarantine = quarantine_parent / str(record["processId"])
                        run_dir.replace(quarantine)
                        moved.append(("run", run_dir, quarantine))
                    state["processes"].pop(str(record["processKey"]), None)
                self.store.save(state)
                state_committed = True
                self._write_backup(state)
            except Exception as exc:
                rollback_failures: list[str] = []
                if not state_committed:
                    try:
                        current = self.store._read_candidate(self.store.paths.processes)  # noqa: SLF001
                        state_committed = set(current["processes"]) == set(state["processes"])
                    except Exception:
                        state_committed = False
                if state_committed:
                    try:
                        self.store._save(original, backup=False)  # noqa: SLF001
                        self._write_backup(original)
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
