"""资源总账、admission、compact tombstone 与可恢复 GC。"""
from __future__ import annotations
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from .atomic import read_json_file
from .errors import ResourceBudgetError, ResourceUsageUnverifiableError, RuntimeRebuildRequiredError, StateError
from .logs import RESOURCE_CAPS, RuntimeAccountant, serialized_json
from .models import RUN_ID_RE, SERVICE_NAME_RE, empty_state, process_key
from .protocol import public_resource_summary
from .runtime import now_text
def _record_stamp(record: dict[str, Any]) -> str:
    return str(record.get("public", {}).get("finalizedAt") or record.get("updatedAt") or record.get("createdAt") or "")
def _record_time(record: dict[str, Any]) -> datetime:
    try:
        value = datetime.fromisoformat(_record_stamp(record))
    except (TypeError, ValueError) as exc:
        raise ResourceUsageUnverifiableError("terminal run timestamp 无法用于资源核算") from exc
    if value.tzinfo is None:
        raise ResourceUsageUnverifiableError("terminal run timestamp 缺少时区")
    return value.astimezone(timezone.utc)
class StateRebuilder:
    """从受限 run 目录重建中央索引，并保留冲突证据。"""
    def __init__(self, store: Any) -> None:
        self.store = store
    def run(self) -> dict[str, Any]:
        state, adapter, runs = empty_state(), self.store.adapter, self.store.paths.runs
        adapter.validate_runtime_path(runs)
        if not runs.exists():
            return state
        adapter.verify_directory(runs)
        candidates: list[dict[str, Any]] = []
        scanned = 0
        for service_dir in runs.iterdir():
            scanned += 1
            if scanned > 10000:
                raise StateError("run record 重建扫描超过 10000 项")
            if not SERVICE_NAME_RE.fullmatch(service_dir.name) or not adapter.validate_runtime_path(service_dir).is_dir():
                continue
            adapter.verify_directory(service_dir)
            for run_dir in service_dir.iterdir():
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
                    candidates.append(self.store.schema.validate_record(
                        process_key(service_dir.name, run_dir.name),
                        read_json_file(process_file, max_bytes=RESOURCE_CAPS["run"])))
                except RuntimeRebuildRequiredError:
                    raise
                except StateError as exc:
                    raise StateError(
                        "合法 run 路径中的 process record 损坏",
                        diagnostics={"processFile": process_file.name,
                                     "failure": type(exc).__name__}) from exc
        active_by_service: dict[str, list[dict[str, Any]]] = {}
        for record in candidates:
            key = str(record["processKey"])
            state["processes"][key] = record
            if record.get("status") in self.store.active_states:
                active_by_service.setdefault(str(record["service"]), []).append(record)
        state["workGeneration"] = sum(int(record["recordRevision"]) for record in candidates)
        for service, records in active_by_service.items():
            if len(records) != 1:
                raise StateError(
                    f"service 存在多个 active owner，拒绝丢弃清理证据: {service}",
                    diagnostics={"processKeys": sorted(str(record["processKey"]) for record in records)},
                )
            state["active"][service] = records[0]["processKey"]
        return state
class ResourceGovernor:
    """在 repository revision 内计算总承诺并执行 mutation admission。"""
    def __init__(self, store: Any) -> None:
        self.store, self.config = store, store.config
    def _counts(self, state: dict[str, Any], active_control_requests: int) -> dict[str, int]:
        records, sessions = list(state["processes"].values()), list(state["sessions"].values())
        pending_delete = self.store._read_pending_transaction()  # noqa: SLF001
        pending_session_deletes = len(pending_delete["deleteSessions"]) if pending_delete else 0
        inactive = [record for record in records if record.get("status") not in self.store.active_states]
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.config.history_max_age_seconds)
        terminating = sum(record.get("status") == "terminating" for record in records)
        active_total = sum(record.get("status") in self.store.active_states for record in records)
        session_pending = sum(
            session.get("state") in {"terminating", "expired", "cleanup_failed"} for session in sessions
        )
        run_pending = sum(
            record.get("status") == "terminating"
            or record.get("public", {}).get("cleanupVerified") is False
            and record.get("status") not in self.store.active_states
            for record in records
        )
        return {
            "activeRuns": active_total - terminating,
            "terminatingRuns": terminating,
            "openSessions": sum(session.get("state") == "open" for session in sessions),
            "expiredSessions": session_pending,
            "sessionRecords": len(state["sessions"]),
            "inactiveRuns": len(inactive),
            "expiredHistoryRuns": sum(_record_time(record) <= cutoff for record in inactive),
            "pendingPrunes": len(state["pendingPrunes"]),
            "activeControlRequests": active_control_requests,
            "cleanupPending": session_pending + run_pending + pending_session_deletes
            + sum(bool(item["cleanupPending"]) for item in state["pendingPrunes"].values()),
        }
    def measure(self, state: dict[str, Any], *, active_control_requests: int = 0) -> dict[str, Any]:
        counts = self._counts(state, active_control_requests)
        usage = RuntimeAccountant(self.store, state).measure()
        limits = self.config.limits
        count_over = (
            counts["activeRuns"] + counts["terminatingRuns"] > limits["maxActiveRuns"]
            or counts["openSessions"] > limits["maxOpenSessions"]
            or counts["sessionRecords"] > limits["maxSessionRecords"]
            or counts["pendingPrunes"] > limits["maxPendingPrunes"]
            or counts["activeControlRequests"] > limits["maxConcurrentControlRequests"]
            or len(state["tombstones"]) > self.config.history_max_tombstones
            or counts["inactiveRuns"] > self.config.history_max_inactive
            or counts["expiredHistoryRuns"] > 0
        )
        details = {
            **counts,
            "usedBytes": usage.used,
            "reservedBytes": usage.reserved,
            "limitBytes": limits["maxRetainedBytes"],
            "overBudget": count_over
            or usage.used > usage.reserved
            or usage.reserved > limits["maxRetainedBytes"],
            "fixedActualBytes": usage.fixed,
            "metadataCapacityBytes": usage.metadata,
            "managerLogCapacityBytes": usage.manager_logs,
            "runCapacityBytes": usage.run_capacity,
            "tombstones": len(state["tombstones"]),
        }
        return details
    def summary(self, state: dict[str, Any] | None = None, *, active_control_requests: int = 0, strict: bool = True) -> dict[str, Any]:
        current = state if state is not None else self.store.load()
        try:
            details = self.measure(current, active_control_requests=active_control_requests)
            return public_resource_summary(details)
        except ResourceUsageUnverifiableError as exc:
            if strict:
                raise
            counts = self._counts(current, active_control_requests)
            return public_resource_summary({
                **counts, "usedBytes": None, "reservedBytes": None,
                "limitBytes": self.config.limits["maxRetainedBytes"],
                "overBudget": True,
            })
    def diagnostics(self, *, active_control_requests: int = 0) -> dict[str, Any]:
        state = self.store.load()
        try:
            return {**self.measure(state, active_control_requests=active_control_requests),
                    "limits": dict(self.config.limits)}
        except ResourceUsageUnverifiableError as exc:
            return {**self.summary(state, active_control_requests=active_control_requests, strict=False),
                    "limits": dict(self.config.limits), "error": exc.public_dict(include_diagnostics=True)}
    def _admit(self, state: dict[str, Any], candidate: int, *, kind: str) -> None:
        details = self.measure(state)
        projected = details["reservedBytes"] + candidate
        if details["overBudget"] or details["usedBytes"] > details["reservedBytes"] or (
            projected > details["limitBytes"]
        ):
            raise ResourceBudgetError(
                f"{kind} 超过 process-manager 资源预算",
                diagnostics={
                    "usedBytes": details["usedBytes"],
                    "reservedBytes": details["reservedBytes"],
                    "projectedReservedBytes": projected,
                    "limitBytes": details["limitBytes"],
                },
                recommended_action="prune",
            )
    def admit_session(self, state: dict[str, Any]) -> None:
        counts = self._counts(state, 0)
        if (
            counts["openSessions"] >= self.config.limits["maxOpenSessions"]
            or counts["sessionRecords"] >= self.config.limits["maxSessionRecords"]
        ):
            raise ResourceBudgetError("session count 已达到配置上限", recommended_action="session_close")
        self._admit(state, 2 * RESOURCE_CAPS["session"], kind="session open")
    def admit_start(self, state: dict[str, Any], service: Any) -> None:
        counts = self._counts(state, 0)
        if counts["activeRuns"] + counts["terminatingRuns"] >= self.config.limits["maxActiveRuns"]:
            raise ResourceBudgetError("active run count 已达到配置上限", recommended_action="process_stop")
        self._admit(state, self.start_capacity(service), kind="run start")
    @staticmethod
    def start_capacity(service: Any) -> int:
        logs = service.logs
        return 2 * (RESOURCE_CAPS["run"] + RESOURCE_CAPS["host"]) + 2 * int(logs["maxBytes"]) * (int(logs["backups"]) + 1)
    def admit_prune(self, state: dict[str, Any]) -> None:
        if len(state["pendingPrunes"]) >= self.config.limits["maxPendingPrunes"]:
            raise ResourceBudgetError("pending prune count 已达到配置上限", recommended_action="prune")
    def _trim_tombstones(self, state: dict[str, Any], *, incoming_id: str | None = None) -> int:
        pinned = {f"run:{item['processKey']}" for item in state["pendingPrunes"].values()}
        eligible = sorted(
            (str(item["prunedAt"]), key)
            for key, item in state["tombstones"].items()
            if item.get("retainedPath") is None and key != incoming_id and key not in pinned
        )
        target = self.config.history_max_tombstones - int(
            incoming_id is not None and incoming_id not in state["tombstones"])
        removed = 0
        while len(state["tombstones"]) > target and eligible:
            state["tombstones"].pop(eligible.pop(0)[1], None)
            removed += 1
        return removed
    def _add_tombstone(self, state: dict[str, Any], tombstone: dict[str, Any]) -> None:
        tombstone_id = f"{tombstone['kind']}:{tombstone['key']}"
        self._trim_tombstones(state, incoming_id=tombstone_id)
        if len(state["tombstones"]) + int(
            tombstone_id not in state["tombstones"]) > self.config.history_max_tombstones:
            raise ResourceBudgetError("compact tombstone count 已达到配置上限", recommended_action="prune")
        if len(serialized_json(tombstone)) > RESOURCE_CAPS["tombstone"]:
            raise ResourceBudgetError("compact tombstone 超过 metadata cap", recommended_action="doctor")
        state["tombstones"][tombstone_id] = tombstone
    def compact_session(self, state: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        path = self.store.schema.session_path(str(session["sessionId"]))
        self.store.adapter.verify_file(path)
        size = int(path.stat().st_size)
        if size > RESOURCE_CAPS["session"]:
            raise ResourceUsageUnverifiableError("session record 超过 closed metadata cap")
        closed_at = str(session.get("cleanup", {}).get("closedAt") or now_text())
        tombstone = {
            "schema": "process-manager-tombstone", "kind": "session",
            "key": session["sessionId"], "state": "closed", "createdAt": session["createdAt"], "updatedAt": session["renewedAt"],
            "finalizedAt": closed_at, "prunedAt": now_text(), "bytes": size,
            "summary": {
                "kind": session["kind"], "closingReason": session.get("closingReason"),
                "cleanupVerified": True,
            },
            "retainedPath": None,
        }
        self._add_tombstone(state, tombstone)
        state["sessions"].pop(str(session["sessionId"]), None)
        return tombstone
    def automatic_gc(self, *, candidate_capacity: int = 0) -> dict[str, Any]:
        with self.store.transaction():
            state = self.store.load()
            compacted = self._trim_tombstones(state)
            if compacted:
                self.store.save(state)
            details = self.measure(state)
        shortage = max(0, details["reservedBytes"] + max(0, candidate_capacity)
                       - details["limitBytes"])
        keep_runs = not self.config.history_delete_run_dirs
        result = PruneCoordinator(self.store).run(
            max_inactive=None, dry_run=False, keep_runs=keep_runs,
            required_bytes=0 if keep_runs else shortage, max_candidates=8,
        )
        return {**result, "tombstonesCompacted": compacted}
class PruneCoordinator:
    """以 central journal 唯一恢复 run history 的移动、提交和删除。"""
    def __init__(self, store: Any) -> None:
        self.store, self.governor = store, ResourceGovernor(store)
    @staticmethod
    def _eligible(record: dict[str, Any], active_states: set[str]) -> bool:
        public = record.get("public", {})
        return (
            record.get("status") not in active_states
            and record.get("cleanupClaim") is None
            and public.get("ownerEmpty") is True
            and public.get("cleanupVerified") is True
        )
    def _tree_bytes(self, record: dict[str, Any]) -> int:
        accountant = RuntimeAccountant(self.store, {"processes": {}, "sessions": {}, "tombstones": {},
                                                    "pendingPrunes": {}})
        return accountant.tree_bytes(Path(record["runDir"]))
    def _plan(
        self, state: dict[str, Any], *, limit: int, required_bytes: int, max_candidates: int,
    ) -> list[tuple[dict[str, Any], int]]:
        eligible = sorted(
            (record for record in state["processes"].values()
             if self._eligible(record, self.store.active_states)),
            key=lambda record: (_record_stamp(record), str(record["processKey"])),
        )
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.store.config.history_max_age_seconds)
        selected = [record for record in eligible if _record_time(record) <= cutoff]
        selected_keys = {str(record["processKey"]) for record in selected}
        remaining = [record for record in eligible if str(record["processKey"]) not in selected_keys]
        inactive_count = sum(record.get("status") not in self.store.active_states for record in state["processes"].values())
        overflow = max(0, inactive_count - len(selected) - limit)
        selected.extend(remaining[:overflow])
        sizes = [(record, self._tree_bytes(record)) for record in selected[:max_candidates]]
        freed = sum(size for _, size in sizes)
        if freed < required_bytes:
            for record in remaining[overflow:]:
                if len(sizes) >= max_candidates:
                    break
                size = self._tree_bytes(record)
                sizes.append((record, size))
                freed += size
                if freed >= required_bytes:
                    break
        return sizes
    def _relative(self, path: Path) -> str:
        checked = self.store.adapter.validate_runtime_path(path)
        return checked.relative_to(self.store.paths.state_root).as_posix()
    def _new_journal(self, record: dict[str, Any], size: int, keep_run: bool) -> dict[str, Any]:
        transaction_id = f"prune-{uuid.uuid4().hex}"
        source = Path(record["runDir"])
        quarantine = (
            source / "process.pruned.json"
            if keep_run
            else self.store.paths.tmp / "prune" / transaction_id / record["service"] / record["processId"]
        )
        return {
            "schema": "process-manager-prune", "transactionId": transaction_id,
            "processKey": record["processKey"], "source": self._relative(source),
            "quarantine": self._relative(quarantine), "originalBytes": size,
            "phase": "intent", "keepRun": keep_run, "cleanupPending": False,
        }
    def _save_intent(self, record: dict[str, Any], size: int, keep_run: bool) -> dict[str, Any]:
        with self.store.transaction():
            state = self.store.load()
            current = state["processes"].get(record["processKey"])
            if (not isinstance(current, dict) or not self._eligible(current, self.store.active_states)
                    or current.get("recordRevision") != record.get("recordRevision")):
                raise StateError("prune candidate 在 intent 提交前已变化")
            self.governor.admit_prune(state)
            journal = self._new_journal(current, size, keep_run)
            state["pendingPrunes"][journal["transactionId"]] = journal
            self.store.save(state)
            return journal
    def _paths(self, journal: dict[str, Any]) -> tuple[Path, Path]:
        root = self.store.paths.state_root
        return (
            self.store.adapter.validate_runtime_path(root / Path(journal["source"])),
            self.store.adapter.validate_runtime_path(root / Path(journal["quarantine"])),
        )
    def _move(self, journal: dict[str, Any]) -> None:
        source, quarantine = self._paths(journal)
        if journal["keepRun"]:
            process_file = source / "process.json"
            if process_file.exists() and not quarantine.exists():
                process_file.replace(quarantine)
            elif process_file.exists() or not quarantine.is_file():
                raise StateError("keep-run prune path 组合不一致")
        else:
            if source.is_dir() and not quarantine.exists():
                self.store.adapter.secure_directory(quarantine.parent)
                source.replace(quarantine)
            elif source.exists() or not quarantine.is_dir():
                raise StateError("delete-run prune path 组合不一致")
    def _phase(self, transaction_id: str, phase: str, *, cleanup_pending: bool = False) -> dict[str, Any]:
        with self.store.transaction():
            state = self.store.load()
            current = state["pendingPrunes"].get(transaction_id)
            if not isinstance(current, dict):
                raise StateError("pending prune journal 缺失")
            current = {**current, "phase": phase, "cleanupPending": cleanup_pending}
            state["pendingPrunes"][transaction_id] = current
            self.store.save(state)
            return current
    def _commit(self, journal: dict[str, Any]) -> dict[str, Any]:
        with self.store.transaction():
            state = self.store.load()
            current = state["pendingPrunes"].get(journal["transactionId"])
            if not isinstance(current, dict):
                raise StateError("pending prune journal 缺失")
            if current["phase"] == "committed":
                return current
            if current["phase"] != "quarantined":
                raise StateError("prune commit 只允许 quarantined phase")
            record = state["processes"].get(current["processKey"])
            if not isinstance(record, dict) or not self._eligible(record, self.store.active_states):
                raise StateError("prune commit 丢失 terminal record evidence")
            retained = current["source"] if current["keepRun"] else None
            tombstone = {
                "schema": "process-manager-tombstone", "kind": "run",
                "key": record["processKey"], "state": record["status"], "createdAt": record["createdAt"], "updatedAt": record.get("updatedAt", record["createdAt"]),
                "finalizedAt": _record_stamp(record), "prunedAt": now_text(),
                "bytes": current["originalBytes"],
                "summary": {
                    "service": record["service"],
                    "exitCode": record.get("public", {}).get("exitCode"),
                    "ownerEmpty": True, "cleanupVerified": True,
                },
                "retainedPath": retained,
            }
            self.governor._add_tombstone(state, tombstone)  # noqa: SLF001
            state["processes"].pop(record["processKey"], None)
            current = {**current, "phase": "committed", "cleanupPending": not current["keepRun"]}
            state["pendingPrunes"][current["transactionId"]] = current
            self.store.save(state)
            return current
    @staticmethod
    def _remove_empty(path: Path, *, required: bool) -> bool:
        try:
            if not path.exists():
                return True
            if next(path.iterdir(), None) is not None:
                return not required
            path.rmdir()
            return not path.exists()
        except OSError:
            return False
    def _cleanup(self, journal: dict[str, Any]) -> bool:
        source, quarantine = self._paths(journal)
        if not journal["keepRun"] and quarantine.exists():
            try:
                shutil.rmtree(quarantine)
            except OSError:
                self._phase(journal["transactionId"], "committed", cleanup_pending=True)
                return False
        if not journal["keepRun"] and (
            not self._remove_empty(quarantine.parent, required=True)
            or not self._remove_empty(quarantine.parent.parent, required=True)
            or not self._remove_empty(source.parent, required=False)
        ):
            self._phase(journal["transactionId"], "committed", cleanup_pending=True)
            return False
        with self.store.transaction():
            state = self.store.load()
            current = state["pendingPrunes"].get(journal["transactionId"])
            if not isinstance(current, dict) or current["phase"] != "committed":
                raise StateError("prune cleanup journal phase 无效")
            state["pendingPrunes"].pop(journal["transactionId"], None)
            self.store.save(state)
        return True
    def _resume(self, journal: dict[str, Any]) -> bool:
        current = journal
        if current["phase"] == "intent":
            self._move(current)
            current = self._phase(current["transactionId"], "quarantined")
        if current["phase"] == "quarantined":
            source, quarantine = self._paths(current)
            valid = quarantine.is_file() if current["keepRun"] else quarantine.is_dir() and not source.exists()
            if not valid:
                raise StateError("quarantined prune path 组合不一致")
            current = self._commit(current)
        if current["phase"] == "committed":
            tombstone_id = f"run:{current['processKey']}"
            state = self.store.load()
            if current["processKey"] in state["processes"] or tombstone_id not in state["tombstones"]:
                raise StateError("committed prune central evidence 不一致")
            return self._cleanup(current)
        raise StateError("pending prune phase 无法恢复")
    def recover_pending(self) -> dict[str, Any]:
        state = self.store.load()
        recovered, pending = [], []
        for transaction_id in sorted(state["pendingPrunes"]):
            journal = self.store.load()["pendingPrunes"].get(transaction_id)
            if not isinstance(journal, dict):
                continue
            if self._resume(journal):
                recovered.append(transaction_id)
            else:
                pending.append(transaction_id)
        return {"recovered": recovered, "pending": pending, "cleanupVerified": not pending}
    def run(self, *, max_inactive: int | None, dry_run: bool, keep_runs: bool,
            required_bytes: int = 0, max_candidates: int = 128) -> dict[str, Any]:
        limit = self.store.config.history_max_inactive if max_inactive is None else max_inactive
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 10000:
            raise StateError("maxInactive 必须是 0-10000 范围内整数")
        if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or not 1 <= max_candidates <= 128:
            raise StateError("maxCandidates 必须是 1-128 范围内整数")
        pending_ids = sorted(self.store.load()["pendingPrunes"])
        recovery = (
            {"recovered": [], "pending": pending_ids, "cleanupVerified": not pending_ids}
            if dry_run else self.recover_pending()
        )
        state = self.store.load()
        candidates = self._plan(
            state, limit=limit, required_bytes=required_bytes, max_candidates=max_candidates
        )
        preview = [
            {
                "service": record["service"], "processKey": record["processKey"],
                "state": record["status"], "runDir": record["runDir"], "bytes": size,
                "updatedAt": record.get("updatedAt", record["createdAt"]),
            }
            for record, size in candidates
        ]
        effective_keep = keep_runs or not self.store.config.history_delete_run_dirs
        if dry_run or not candidates:
            return {
                "dryRun": dry_run, "maxInactive": limit, "keepRuns": effective_keep,
                "candidateCount": len(candidates), "candidates": preview,
                "applied": False, "recovery": recovery,
            }
        cleaned = 0
        for record, size in candidates:
            journal = self._save_intent(record, size, effective_keep)
            cleaned += int(self._resume(journal))
        return {
            "dryRun": False, "maxInactive": limit, "keepRuns": effective_keep,
            "candidateCount": len(candidates), "candidates": preview, "applied": True,
            "prunedCount": len(candidates), "deletedRunDirs": 0 if effective_keep else cleaned,
            "cleanupVerified": cleaned == len(candidates) and recovery["cleanupVerified"],
            "cleanupFailures": [] if cleaned == len(candidates) else ["pending_prune_cleanup"],
            "recovery": recovery,
        }
