"""Session lease、所有权索引与可恢复清理协调。"""
from __future__ import annotations
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from .atomic import read_json_file
from .errors import ConflictError, SessionCleanupPendingError, SessionExpiredError, SessionNotFoundError, StateError, SupervisorError, ValidationError
from .logs import RESOURCE_CAPS
from .models import SESSION_ACTIVE_STATES, SESSION_ID_RE
from .protocol import public_session_tombstone
from .resources import ResourceGovernor
from .runtime import now_text
DEFAULT_SESSION_TTL_SECONDS, MIN_SESSION_TTL_SECONDS, MAX_SESSION_TTL_SECONDS = 1800, 60, 86400
DEFAULT_SWEEP_INTERVAL_SECONDS, DEFAULT_SWEEP_BATCH = 1.0, 8
DEFAULT_CLOCK_DRIFT_TOLERANCE_SECONDS = 5.0
def restore_session_index(store: Any, state: dict[str, Any]) -> dict[str, Any]:
    """从受限 session 目录恢复中央索引，不猜测损坏记录。"""
    root = store.adapter.validate_runtime_path(store.paths.sessions)
    if not root.exists():
        return state
    store.adapter.verify_directory(root)
    scanned = 0
    for path in root.iterdir():
        scanned += 1
        if scanned > 10000:
            raise StateError("session record 重建扫描超过 10000 项")
        if not path.is_file() or path.suffix != ".json" or SESSION_ID_RE.fullmatch(path.stem) is None:
            raise StateError("sessions 目录包含未知 record")
        store.adapter.verify_file(path)
        session = store.schema.validate_session(
            path.stem, read_json_file(path, max_bytes=RESOURCE_CAPS["session"]))
        state["sessions"][path.stem] = session
        state["workGeneration"] += int(session["revision"])
    store.schema.validate_state(state)
    return state
def close_orphaned_sessions(state_store: Any, *, reason: str) -> dict[str, Any]:
    """在 run owners 已收口后关闭遗留 session。"""
    closed: list[str] = []
    pending: list[str] = []
    resources = ResourceGovernor(state_store)
    with state_store.transaction():
        state = state_store.load()
        for session_id, original in list(state["sessions"].items()):
            if original["state"] not in SESSION_ACTIVE_STATES:
                continue
            if original["runKeys"]:
                pending.append(session_id)
                continue
            session = dict(original)
            session.update({
                "revision": int(session["revision"]) + 1, "state": "closed",
                "closingReason": session.get("closingReason") or reason,
                "cleanup": {"ownerEmpty": True, "cleanupVerified": True,
                            "closedAt": now_text(), "failures": []}})
            state["sessions"][session_id] = session
            state["workGeneration"] += 1
            resources.compact_session(state, session)
            state_store.commit_repository(state, delete_sessions=[session_id])
            closed.append(session_id)
    return {"closedSessionIds": closed, "pendingSessionIds": pending, "cleanupVerified": not pending}
class SessionController:
    """线性化 session lease、run 绑定和统一 finalizer。"""
    def __init__(
        self, state: Any, *, manager_instance_id: str, workspace_digest: str,
        finalize_record: Callable[..., dict[str, Any]],
        wall_clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sweep_interval: float = DEFAULT_SWEEP_INTERVAL_SECONDS,
        sweep_batch: int = DEFAULT_SWEEP_BATCH,
        drift_tolerance: float = DEFAULT_CLOCK_DRIFT_TOLERANCE_SECONDS,
    ) -> None:
        if SESSION_ID_RE.fullmatch(manager_instance_id) is None:
            raise StateError("manager instance ID 不是 canonical UUID hex")
        self.state = state
        self.manager_instance_id = manager_instance_id
        self.workspace_digest = workspace_digest
        self.finalize_record = finalize_record
        self._resources = ResourceGovernor(state)
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sweep_interval = sweep_interval
        self.sweep_batch = sweep_batch
        self.drift_tolerance = drift_tolerance
        self._lock = threading.RLock()
        self._deadlines: dict[str, float] = {}
        self._anchor_wall = self._wall_now()
        self._anchor_monotonic = self.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._errors: list[dict[str, Any]] = []
        self._sweep_cursor: str | None = None
    def _wall_now(self) -> datetime:
        value = self.wall_clock()
        if value.tzinfo is None:
            raise StateError("session wall clock 缺少时区")
        return value.astimezone(timezone.utc)
    @staticmethod
    def _ttl(value: Any) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not MIN_SESSION_TTL_SECONDS <= value <= MAX_SESSION_TTL_SECONDS
        ):
            raise ValidationError(
                f"session TTL 必须是 {MIN_SESSION_TTL_SECONDS}-{MAX_SESSION_TTL_SECONDS} 范围内整数"
            )
        return value
    @staticmethod
    def ownership(session_id: str | None, persistent: bool) -> dict[str, Any]:
        if not isinstance(persistent, bool):
            raise ValidationError("persistent 必须是 boolean")
        if persistent == (session_id is not None):
            raise ValidationError("sessionId 与 persistent 必须且只能提供一个")
        if persistent:
            return {"kind": "persistent", "sessionId": None}
        if not isinstance(session_id, str) or SESSION_ID_RE.fullmatch(session_id) is None:
            raise ValidationError("sessionId 必须是 canonical UUID hex")
        return {"kind": "session", "sessionId": session_id}
    def _session(self, state: dict[str, Any], session_id: str) -> dict[str, Any]:
        session = state["sessions"].get(session_id)
        if not isinstance(session, dict):
            if self._closed(state, session_id) is not None:
                raise SessionExpiredError("session 已关闭")
            raise SessionNotFoundError("session 不存在")
        return session
    def _closed(self, state: dict[str, Any], session_id: str) -> dict[str, Any] | None:
        value = state["tombstones"].get(f"session:{session_id}")
        return public_session_tombstone(value) if isinstance(value, dict) else None
    def _anchor_valid(self, wall: datetime, monotonic_now: float) -> bool:
        wall_elapsed = (wall - self._anchor_wall).total_seconds()
        monotonic_elapsed = monotonic_now - self._anchor_monotonic
        return monotonic_elapsed >= 0 and abs(wall_elapsed - monotonic_elapsed) <= self.drift_tolerance
    def _expiry_reason(self, session: dict[str, Any], wall: datetime, monotonic_now: float) -> str | None:
        if session["managerInstanceId"] != self.manager_instance_id:
            return "manager_instance_changed"
        deadline = self._deadlines.get(str(session["sessionId"]))
        if deadline is None:
            return "monotonic_anchor_missing"
        if not self._anchor_valid(wall, monotonic_now):
            return "clock_anomaly"
        try:
            wall_deadline = datetime.fromisoformat(str(session["expiresAt"])).astimezone(timezone.utc)
        except (TypeError, ValueError) as exc:
            raise StateError("session expiresAt 无效") from exc
        if monotonic_now >= deadline or wall >= wall_deadline:
            return "lease_expired"
        return None
    @staticmethod
    def _set_closing(session: dict[str, Any], *, state: str, reason: str) -> dict[str, Any]:
        updated = dict(session)
        updated.update({
            "revision": int(session["revision"]) + 1, "state": state,
            "closingReason": session.get("closingReason") or reason, "cleanup": None,
        })
        return updated
    def _commit_session(
        self, state: dict[str, Any], session: dict[str, Any], *, work_delta: int = 0,
    ) -> None:
        state["sessions"][session["sessionId"]] = session
        state["workGeneration"] += work_delta
        self.state.commit_repository(state, sessions=[session])
    def _expire_session(
        self, state: dict[str, Any], session: dict[str, Any], reason: str,
    ) -> dict[str, Any]:
        expired = self._set_closing(session, state="expired", reason=reason)
        self._deadlines.pop(str(session["sessionId"]), None)
        self._commit_session(state, expired)
        return expired
    @staticmethod
    def _cleanup(verified: bool, failures: list[str]) -> dict[str, Any]:
        return {"ownerEmpty": verified, "cleanupVerified": verified,
                "closedAt": now_text(), "failures": failures}
    def open(self, *, kind: str, ttl_seconds: int, holder: str) -> dict[str, Any]:
        ttl = self._ttl(ttl_seconds)
        if kind not in {"validation", "task"}:
            raise ValidationError("session kind 只允许 validation 或 task")
        if not isinstance(holder, str) or not holder or len(holder.encode("utf-8")) > 256:
            raise ValidationError("session holder 必须是 1-256 bytes 非空标签")
        if any(ord(char) < 32 for char in holder):
            raise ValidationError("session holder 不能包含控制字符")
        session_id = uuid.uuid4().hex
        wall, monotonic_now = self._wall_now(), self.monotonic()
        timestamp = wall.isoformat()
        session = {
            "schema": "process-manager-session", "sessionId": session_id, "revision": 1,
            "holder": holder, "kind": kind, "state": "open",
            "workspaceDigest": self.workspace_digest, "managerInstanceId": self.manager_instance_id,
            "leaseDurationSeconds": ttl, "createdAt": timestamp, "renewedAt": timestamp,
            "expiresAt": (wall + timedelta(seconds=ttl)).isoformat(),
            "closingReason": None, "runKeys": [], "cleanup": None,
        }
        self._resources.automatic_gc(candidate_capacity=2 * RESOURCE_CAPS["session"])
        self.state.adapter.secure_directory(self.state.paths.sessions)
        with self._lock, self.state.transaction():
            state = self.state.load()
            if state["intakeFence"] is not None:
                raise ConflictError("manager intake 已关闭，拒绝创建 session")
            self._resources.admit_session(state)
            self._deadlines[session_id] = monotonic_now + ttl
            try:
                self._commit_session(state, session, work_delta=1)
            except Exception:
                self._deadlines.pop(session_id, None)
                raise
        return self._public(session)
    def renew(self, session_id: str, *, ttl_seconds: int) -> dict[str, Any]:
        ttl = self._ttl(ttl_seconds)
        wall, monotonic_now = self._wall_now(), self.monotonic()
        expired: dict[str, Any] | None = None
        with self._lock, self.state.transaction():
            state = self.state.load()
            session = self._session(state, session_id)
            if session["state"] != "open":
                raise SessionExpiredError("session 已关闭或正在清理")
            reason = self._expiry_reason(session, wall, monotonic_now)
            if reason is not None:
                expired = self._expire_session(state, session, reason)
            else:
                renewed = dict(session)
                renewed.update(
                    {
                        "revision": int(session["revision"]) + 1,
                        "leaseDurationSeconds": ttl,
                        "renewedAt": wall.isoformat(),
                        "expiresAt": (wall + timedelta(seconds=ttl)).isoformat(),
                    }
                )
                self._commit_session(state, renewed)
                self._deadlines[session_id] = monotonic_now + ttl
                return self._public(renewed)
        assert expired is not None
        self._finalize(session_id, deadline=None)
        raise SessionExpiredError(
            "session lease 已过期",
            diagnostics={"sessionId": session_id, "reason": expired["closingReason"]},
        )
    def reserve_run(
        self,
        service: Any,
        *,
        capability_hash: str,
        session_id: str | None,
        persistent: bool,
    ) -> dict[str, Any]:
        ownership = self.ownership(session_id, persistent)
        if persistent:
            return self.state.reserve(
                service,
                manager_instance_id=self.manager_instance_id,
                capability_hash=capability_hash,
                ownership=ownership,
            )
        assert session_id is not None
        wall, monotonic_now = self._wall_now(), self.monotonic()
        expired: dict[str, Any] | None = None
        with self._lock, self.state.transaction():
            state = self.state.load()
            session = self._session(state, session_id)
            if session["workspaceDigest"] != self.workspace_digest:
                raise StateError("session workspace identity 不匹配")
            if session["state"] != "open":
                raise SessionExpiredError("session 未处于 open 状态")
            reason = self._expiry_reason(session, wall, monotonic_now)
            if reason is not None:
                expired = self._expire_session(state, session, reason)
            else:
                return self.state.reserve(
                    service,
                    manager_instance_id=self.manager_instance_id,
                    capability_hash=capability_hash,
                    ownership=ownership,
                    expected_session_revision=int(session["revision"]),
                )
        assert expired is not None
        self._finalize(session_id, deadline=None)
        raise SessionExpiredError(
            "session lease 已过期",
            diagnostics={"sessionId": session_id, "reason": expired["closingReason"]},
        )
    def status(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            state = self.state.load()
            session = state["sessions"].get(session_id)
            if not isinstance(session, dict):
                closed = self._closed(state, session_id)
                if closed is not None:
                    return closed
                raise SessionNotFoundError("session 不存在")
            result = self._public(session)
            if session["state"] == "open":
                result["leaseExpired"] = self._expiry_reason(
                    session, self._wall_now(), self.monotonic()
                ) is not None
            return result
    def close(self, session_id: str, *, reason: str = "close_requested") -> dict[str, Any]:
        with self._lock, self.state.transaction():
            state = self.state.load()
            session = state["sessions"].get(session_id)
            if not isinstance(session, dict):
                result = self._closed(state, session_id)
                if result is None:
                    raise SessionNotFoundError("session 不存在")
                result["workGeneration"] = state["workGeneration"]
                return result
            if session["state"] in {"open", "cleanup_failed"}:
                session = self._set_closing(session, state="terminating", reason=reason)
                self._commit_session(state, session)
            self._deadlines.pop(session_id, None)
        result = self._finalize(session_id, deadline=None)
        result["workGeneration"] = self.state.work_summary()["workGeneration"]
        return result
    def _finalize(self, session_id: str, *, deadline: float | None) -> dict[str, Any]:
        state = self.state.load()
        session = state["sessions"].get(session_id)
        if not isinstance(session, dict):
            closed = self._closed(state, session_id)
            if closed is not None:
                return closed
            raise SessionNotFoundError("session 不存在")
        failures: list[str] = []
        for key in list(session["runKeys"]):
            try:
                record = self.state.get(key=key)
                committed = self.finalize_record(
                    record, reason=f"session_{session.get('closingReason') or 'closing'}",
                    terminal_status="stopped", deadline=deadline,
                )
                if not committed.get("public", {}).get("cleanupVerified"):
                    failures.append(f"{key}:cleanup_unverified")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{key}:{type(exc).__name__}")
        compacted: dict[str, Any] | None = None
        with self.state.transaction():
            state = self.state.load()
            session = state["sessions"].get(session_id)
            if not isinstance(session, dict):
                closed = self._closed(state, session_id)
                if closed is not None:
                    return closed
                raise SessionNotFoundError("session 不存在")
            if not session["runKeys"]:
                session = dict(session)
                session.update({
                    "revision": int(session["revision"]) + 1,
                    "state": "closed",
                    "cleanup": self._cleanup(True, []),
                })
                state["sessions"][session_id] = session
                state["workGeneration"] += 1
                tombstone = self._resources.compact_session(state, session)
                self.state.commit_repository(state, delete_sessions=[session_id])
                compacted = public_session_tombstone(tombstone)
            else:
                session = dict(session)
                session.update({
                    "revision": int(session["revision"]) + 1,
                    "state": "cleanup_failed",
                    "cleanup": self._cleanup(False, failures or ["owned_runs_remaining"]),
                })
                self._commit_session(state, session)
        if compacted is not None:
            self._resources.automatic_gc()
            return compacted
        raise SessionCleanupPendingError(
            "session owned run 清理尚未完成",
            diagnostics={"sessionId": session_id, "runKeys": list(session["runKeys"])},
            recommended_action="session_close",
        )
    @staticmethod
    def _public(session: dict[str, Any]) -> dict[str, Any]:
        value = dict(session)
        value["ownedRunCount"] = len(session["runKeys"])
        value["cleanupPending"] = session["state"] in {"terminating", "expired", "cleanup_failed"}
        return value
    def sweep_once(self) -> dict[str, Any]:
        state = self.state.load()
        wall, monotonic_now = self._wall_now(), self.monotonic()
        candidates: list[tuple[str, str | None]] = []
        with self._lock:
            session_ids = sorted(state["sessions"])
            start = session_ids.index(self._sweep_cursor) + 1 if self._sweep_cursor in session_ids else 0
            inspected = (session_ids[start:] + session_ids[:start])[: self.sweep_batch]
            self._sweep_cursor = inspected[-1] if inspected else None
            for session_id in inspected:
                session = state["sessions"][session_id]
                if session["state"] not in SESSION_ACTIVE_STATES:
                    continue
                reason = self._expiry_reason(session, wall, monotonic_now) if session["state"] == "open" else None
                if session["state"] != "open" or reason is not None:
                    candidates.append((session_id, reason))
        completed: list[str] = []
        for session_id, reason in candidates:
            try:
                if reason is not None:
                    with self._lock, self.state.transaction():
                        current = self.state.load()
                        session = self._session(current, session_id)
                        if session["state"] == "open":
                            current_reason = self._expiry_reason(
                                session, self._wall_now(), self.monotonic())
                            if current_reason is None:
                                continue
                            self._expire_session(current, session, current_reason)
                self._finalize(session_id, deadline=None)
                completed.append(session_id)
            except SessionCleanupPendingError as exc:
                self._record_error(session_id, exc)
            except Exception as exc:  # noqa: BLE001
                self._record_error(session_id, exc)
        return {"processed": len(candidates), "closedSessionIds": completed, "errors": list(self._errors)}
    def _record_error(self, session_id: str, exc: BaseException) -> None:
        code = getattr(exc, "code", type(exc).__name__)
        with self._lock:
            self._errors.append({"sessionId": session_id, "code": str(code), "at": now_text()})
            del self._errors[:-16]
    def reconcile_startup(self) -> dict[str, Any]:
        return self.sweep_once()
    def start_sweeper(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._sweep_loop, name="pm-session-sweeper", daemon=True)
            self._thread.start()
    def _sweep_loop(self) -> None:
        while not self._stop.wait(self.sweep_interval):
            try:
                self.sweep_once()
            except Exception as exc:  # noqa: BLE001
                self._record_error("*", exc)
    def stop_sweeper(self, *, deadline: float | None) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is None or thread is threading.current_thread():
            return
        timeout = None if deadline is None else max(0.0, deadline - self.monotonic())
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise SupervisorError("session sweeper 未在 deadline 内退出")
    def begin_shutdown(self, *, deadline: float | None) -> None:
        self.stop_sweeper(deadline=deadline)
        state = self.state.load()
        for session_id, session in list(state["sessions"].items()):
            if session["managerInstanceId"] == self.manager_instance_id and session["state"] in SESSION_ACTIVE_STATES:
                try:
                    with self._lock, self.state.transaction():
                        current = self.state.load()
                        value = self._session(current, session_id)
                        if value["state"] == "open":
                            value = self._set_closing(value, state="terminating", reason="manager_shutdown")
                            self._commit_session(current, value)
                            self._deadlines.pop(session_id, None)
                except SessionNotFoundError:
                    continue
    def finish_shutdown(self, *, deadline: float | None) -> dict[str, Any]:
        state = self.state.load()
        closed: list[str] = []
        pending: list[str] = []
        for session_id, session in list(state["sessions"].items()):
            if session["managerInstanceId"] != self.manager_instance_id or session["state"] not in SESSION_ACTIVE_STATES:
                continue
            try:
                self._finalize(session_id, deadline=deadline)
                closed.append(session_id)
            except SessionCleanupPendingError:
                pending.append(session_id)
        return {"closedSessionIds": closed, "pendingSessionIds": pending, "cleanupVerified": not pending}
    def diagnostics(self) -> dict[str, Any]:
        state = self.state.load()
        sessions = list(state["sessions"].values())
        with self._lock:
            thread = self._thread
            errors = list(self._errors)
        return {
            "open": sum(session["state"] == "open" for session in sessions),
            "cleanupPending": sum(session["state"] in {"terminating", "expired", "cleanup_failed"} for session in sessions),
            "records": len(sessions),
            "sweeperRunning": bool(thread and thread.is_alive()),
            "errors": errors,
        }
