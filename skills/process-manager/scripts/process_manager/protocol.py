"""公共成功/失败 envelope。"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path
from socket import SHUT_WR
from typing import Any

from .atomic import read_json_file
from .errors import PMError, RuntimeCorruptError, RuntimeRebuildRequiredError, StateError
from .logs import RESOURCE_CAPS, serialized_json, write_capped_json
from .models import ACTIVE_STATES, RUN_ID_RE, SERVICE_NAME_RE, SESSION_ID_RE


CONTROL_BUSY_DOMAIN = "process-manager/control-busy"
CONTROL_BUSY_FIELDS = frozenset(
    "domain managerInstanceId issuedAtUnixMs validForMs retryAfterMs nonce code".split()
)
PENDING_PRUNE_KEYS = frozenset(
    "schema transactionId processKey source quarantine originalBytes phase keepRun cleanupPending".split()
)
TOMBSTONE_KEYS = frozenset(
    "schema kind key state createdAt updatedAt finalizedAt prunedAt bytes summary retainedPath".split()
)
PRUNE_PHASES = {"intent", "quarantined", "committed"}
PUBLIC_RESOURCE_KEYS = (
    "activeRuns terminatingRuns openSessions expiredSessions sessionRecords inactiveRuns "
    "pendingPrunes activeControlRequests usedBytes reservedBytes limitBytes cleanupPending overBudget"
).split()


def _relative_resource_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise StateError(f"{label} 必须是 canonical relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise StateError(f"{label} 必须是 canonical relative path")
    return value


def _run_parts(process_key: Any) -> tuple[str, str] | None:
    if not isinstance(process_key, str):
        return None
    match = re.fullmatch(r"(.+)\.(run-[0-9a-f]{32})", process_key)
    if match is None or SERVICE_NAME_RE.fullmatch(match.group(1)) is None:
        return None
    if RUN_ID_RE.fullmatch(match.group(2)) is None:
        return None
    return match.group(1), match.group(2)


def validate_resource_state(
    pending: Any, tombstones: Any, processes: Any, sessions: Any,
) -> None:
    if not all(isinstance(value, dict) for value in (pending, tombstones, processes, sessions)):
        raise StateError("resource state collection 必须是 object")
    resource_paths: set[str] = set()
    retained_paths: set[str] = set()
    for transaction_id, value in pending.items():
        parts = _run_parts(value.get("processKey")) if isinstance(value, dict) else None
        valid = (
            isinstance(transaction_id, str)
            and re.fullmatch(r"prune-[0-9a-f]{32}", transaction_id) is not None
            and isinstance(value, dict) and set(value) == PENDING_PRUNE_KEYS
            and value.get("schema") == "process-manager-prune"
            and value.get("transactionId") == transaction_id
            and parts is not None
            and value.get("phase") in PRUNE_PHASES
            and not isinstance(value.get("originalBytes"), bool)
            and isinstance(value.get("originalBytes"), int) and value["originalBytes"] >= 0
            and isinstance(value.get("keepRun"), bool)
            and isinstance(value.get("cleanupPending"), bool)
        )
        if not valid:
            raise StateError("pending prune 字段无效")
        source = _relative_resource_path(value.get("source"), "pending prune source")
        quarantine = _relative_resource_path(value.get("quarantine"), "pending prune quarantine")
        assert parts is not None
        expected_source = Path("runs", *parts).as_posix()
        expected_quarantine = (
            Path(expected_source, "process.pruned.json").as_posix()
            if value["keepRun"]
            else Path("tmp", "prune", transaction_id, *parts).as_posix()
        )
        if (
            source != expected_source
            or quarantine != expected_quarantine
            or source in resource_paths
            or quarantine in resource_paths
        ):
            raise StateError("pending prune 路径未绑定 exact transaction/process identity")
        resource_paths.update((source, quarantine))
    for tombstone_id, value in tombstones.items():
        kind = value.get("kind") if isinstance(value, dict) else None
        key = value.get("key") if isinstance(value, dict) else None
        summary = value.get("summary") if isinstance(value, dict) else None
        run_parts = _run_parts(key) if kind == "run" else None
        session_valid = kind == "session" and isinstance(key, str) and SESSION_ID_RE.fullmatch(key)
        run_summary = (
            isinstance(summary, dict)
            and set(summary) == {"service", "exitCode", "ownerEmpty", "cleanupVerified"}
            and run_parts is not None and summary.get("service") == run_parts[0]
            and (summary.get("exitCode") is None or (
                not isinstance(summary.get("exitCode"), bool)
                and isinstance(summary.get("exitCode"), int)
            ))
            and summary.get("ownerEmpty") is True
            and summary.get("cleanupVerified") is True
        )
        session_summary = (
            isinstance(summary, dict)
            and set(summary) == {"kind", "closingReason", "cleanupVerified"}
            and isinstance(summary.get("kind"), str) and bool(summary["kind"])
            and isinstance(summary.get("closingReason"), str) and bool(summary["closingReason"])
            and summary.get("cleanupVerified") is True
        )
        valid = (
            isinstance(tombstone_id, str) and isinstance(value, dict)
            and set(value) == TOMBSTONE_KEYS
            and value.get("schema") == "process-manager-tombstone"
            and kind in {"run", "session"}
            and tombstone_id == f"{kind}:{key}"
            and (run_summary if kind == "run" else session_valid and session_summary)
            and isinstance(value.get("state"), str) and bool(value["state"])
            and (value["state"] not in ACTIVE_STATES if kind == "run" else value["state"] == "closed")
            and all(isinstance(value.get(name), str) and value[name]
                    for name in ("createdAt", "updatedAt", "finalizedAt", "prunedAt"))
            and not isinstance(value.get("bytes"), bool)
            and isinstance(value.get("bytes"), int) and value["bytes"] >= 0
            and isinstance(value.get("summary"), dict)
        )
        if not valid:
            raise StateError("resource tombstone 字段无效")
        retained = value.get("retainedPath")
        if retained is not None:
            retained = _relative_resource_path(retained, "tombstone retainedPath")
            expected = Path("runs", *run_parts).as_posix() if run_parts is not None else None
            if retained != expected or retained in retained_paths:
                raise StateError("tombstone retainedPath 未绑定 exact run identity")
            retained_paths.add(retained)
        if len(serialized_json(value)) > RESOURCE_CAPS["tombstone"]:
            raise StateError("resource tombstone 超过 closed metadata cap")
    run_tombstones = {
        str(value["key"]) for value in tombstones.values()
        if isinstance(value, dict) and value.get("kind") == "run"
    }
    session_tombstones = {
        str(value["key"]) for value in tombstones.values()
        if isinstance(value, dict) and value.get("kind") == "session"
    }
    if run_tombstones.intersection(processes) or session_tombstones.intersection(sessions):
        raise StateError("resource tombstone 与 heavy record 同时存在")
    for journal in pending.values():
        key, phase = str(journal["processKey"]), str(journal["phase"])
        record = processes.get(key)
        tombstone = tombstones.get(f"run:{key}")
        expected_cleanup = phase == "committed" and not journal["keepRun"]
        if journal["cleanupPending"] is not expected_cleanup:
            raise StateError("pending prune cleanupPending 与 phase 不一致")
        if phase != "committed":
            public = record.get("public", {}) if isinstance(record, dict) else {}
            if (
                not isinstance(record, dict) or tombstone is not None
                or record.get("status") in ACTIVE_STATES or record.get("cleanupClaim") is not None
                or public.get("ownerEmpty") is not True or public.get("cleanupVerified") is not True
            ):
                raise StateError("pending prune 未绑定 cleanup-verified terminal record")
            continue
        expected_retained = journal["source"] if journal["keepRun"] else None
        if (
            record is not None or not isinstance(tombstone, dict)
            or tombstone.get("bytes") != journal["originalBytes"]
            or tombstone.get("retainedPath") != expected_retained
        ):
            raise StateError("committed prune 未绑定唯一 tombstone")


def public_resource_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in PUBLIC_RESOURCE_KEYS}


def public_session_tombstone(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "process-manager-session-tombstone", "sessionId": value["key"],
        "kind": value["summary"]["kind"], "state": "closed", "createdAt": value["createdAt"],
        "closingReason": value["summary"].get("closingReason"),
        "cleanup": {
            "ownerEmpty": True, "cleanupVerified": True,
            "closedAt": value["finalizedAt"], "failures": [],
        },
        "ownedRunCount": 0, "cleanupPending": False,
    }


def merge_rebuilt_resource_evidence(
    backup: dict[str, Any], rebuilt: dict[str, Any],
) -> dict[str, Any]:
    """恢复无法从 heavy records 重建的中央资源证据。"""

    recovered = {
        **rebuilt,
        "active": dict(rebuilt["active"]),
        "processes": dict(rebuilt["processes"]),
        "sessions": dict(rebuilt["sessions"]),
        "pendingPrunes": dict(backup["pendingPrunes"]),
        "tombstones": dict(backup["tombstones"]),
        "intakeFence": backup["intakeFence"],
        "stateRevision": max(backup["stateRevision"], rebuilt["stateRevision"]) + 1,
        "workGeneration": max(backup["workGeneration"], rebuilt["workGeneration"]) + 1,
    }
    for journal in recovered["pendingPrunes"].values():
        if journal["phase"] == "committed":
            continue
        key = str(journal["processKey"])
        record = backup["processes"].get(key)
        current = recovered["processes"].get(key)
        if not isinstance(record, dict) or current is not None and current != record:
            raise StateError("backup prune record 与 rebuilt evidence 冲突")
        recovered["processes"][key] = record
    return recovered


class RepositoryCommitter:
    """提交并重放中央状态、run 与 session record。"""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.path = store.paths.state_root / "processes.pending.json"

    def read(self) -> dict[str, Any] | None:
        path = self.store.adapter.validate_runtime_path(self.path)
        if not path.exists():
            return None
        self.store.adapter.verify_file(path)
        value = read_json_file(path, max_bytes=RESOURCE_CAPS["transaction"])
        keys = {"schema", "state", "records", "sessions", "deleteSessions"}
        if not isinstance(value, dict) or set(value) != keys:
            raise StateError("process state pending transaction 字段集合无效")
        if value.get("schema") != "process-manager-state-transaction":
            raise RuntimeRebuildRequiredError("process state pending transaction 使用旧或未知 schema")
        state = self.store.schema.validate_state(value.get("state"))
        records = value.get("records")
        sessions = value.get("sessions")
        deletions = value.get("deleteSessions")
        if (
            not isinstance(records, list) or len(records) > 1
            or not isinstance(sessions, list) or len(sessions) > 1
            or not isinstance(deletions, list) or len(deletions) > 1
        ):
            raise StateError("pending transaction record 数量无效")
        for record in records:
            key = record.get("processKey") if isinstance(record, dict) else None
            if not isinstance(key, str) or self.store.schema.validate_record(
                key, record
            ) != state["processes"].get(key):
                raise StateError("pending transaction run record 与中央状态不一致")
        for session in sessions:
            session_id = session.get("sessionId") if isinstance(session, dict) else None
            if not isinstance(session_id, str) or self.store.schema.validate_session(
                session_id, session
            ) != state["sessions"].get(session_id):
                raise StateError("pending transaction session record 与中央状态不一致")
        for session_id in deletions:
            tombstone = state["tombstones"].get(f"session:{session_id}")
            if (
                not isinstance(session_id, str)
                or SESSION_ID_RE.fullmatch(session_id) is None
                or session_id in state["sessions"]
                or not isinstance(tombstone, dict)
            ):
                raise StateError("pending transaction session deletion 与中央状态不一致")
        return {
            "schema": value["schema"], "state": state, "records": records,
            "sessions": sessions, "deleteSessions": deletions,
        }

    def apply(self, value: dict[str, Any]) -> None:
        for record in value["records"]:
            _, path = self.store.schema.run_paths(str(record["service"]), str(record["processId"]))
            self.store.adapter.secure_directory(path.parent.parent)
            self.store.adapter.secure_directory(path.parent)
            write_capped_json(self.store.adapter.validate_runtime_path(path), record, RESOURCE_CAPS["run"])
            self.store.adapter.secure_file(path)
        for session in value["sessions"]:
            path = self.store.schema.session_path(str(session["sessionId"]))
            write_capped_json(
                self.store.adapter.validate_runtime_path(path), session, RESOURCE_CAPS["session"]
            )
            self.store.adapter.secure_file(path)
        self.store._save(value["state"])  # noqa: SLF001
        for session_id in value["deleteSessions"]:
            path = self.store.adapter.validate_runtime_path(
                self.store.schema.session_path(session_id)
            )
            if path.exists():
                self.store.adapter.verify_file(path)
                path.unlink()
        self.store.adapter.validate_runtime_path(self.path).unlink(missing_ok=True)

    def commit(
        self, state: dict[str, Any], records: list[dict[str, Any]],
        sessions: list[dict[str, Any]], delete_sessions: list[str],
    ) -> None:
        state["stateRevision"] = int(state.get("stateRevision", 0)) + 1
        self.store.schema.validate_state(state)
        pending = {
            "schema": "process-manager-state-transaction", "state": state,
            "records": records, "sessions": sessions, "deleteSessions": delete_sessions,
        }
        path = self.store.adapter.validate_runtime_path(self.path)
        write_capped_json(path, pending, RESOURCE_CAPS["transaction"])
        self.store.adapter.secure_file(path)
        self.store._apply_pending_transaction(pending)  # noqa: SLF001


def _busy_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def control_busy_envelope(
    token: str, instance_id: str, *, retry_after_ms: int = 250,
    issued_at_ms: int | None = None, nonce: str | None = None,
) -> dict[str, Any]:
    evidence = {
        "domain": CONTROL_BUSY_DOMAIN, "managerInstanceId": instance_id,
        "issuedAtUnixMs": issued_at_ms if issued_at_ms is not None else time.time_ns() // 1_000_000,
        "validForMs": 5000, "retryAfterMs": retry_after_ms,
        "nonce": nonce or secrets.token_hex(16), "code": "control_busy",
    }
    signature = hmac.new(token.encode("utf-8"), _busy_bytes(evidence), hashlib.sha256).hexdigest()
    return {
        "ok": False, "operation": "control.busy",
        "error": {
            "code": "control_busy", "message": "manager 控制面已达到并发上限",
            "retryable": True, "recommendedAction": "wait",
        },
        "meta": {"managerInstanceId": instance_id},
        "busy": {**evidence, "signature": signature},
    }


def control_timeout_envelope(instance_id: str) -> dict[str, Any]:
    return {
        "ok": False, "operation": "control.timeout",
        "error": {
            "code": "control_timeout", "message": "manager 控制请求读取超时",
            "retryable": True, "recommendedAction": "retry",
        },
        "meta": {"managerInstanceId": instance_id},
    }


def verify_control_busy(
    value: dict[str, Any], token: str, instance_id: str, *, now_ms: int | None = None,
) -> dict[str, Any]:
    error, meta, signed = value.get("error"), value.get("meta"), value.get("busy")
    if (
        set(value) != {"ok", "operation", "error", "meta", "busy"}
        or value.get("ok") is not False or value.get("operation") != "control.busy"
        or not isinstance(error, dict) or error.get("code") != "control_busy"
        or error.get("retryable") is not True or error.get("recommendedAction") != "wait"
        or meta != {"managerInstanceId": instance_id} or not isinstance(signed, dict)
        or set(signed) != CONTROL_BUSY_FIELDS | {"signature"}
    ):
        raise RuntimeCorruptError("control_busy envelope 字段无效")
    evidence = {key: signed[key] for key in CONTROL_BUSY_FIELDS}
    issued, valid, retry = (
        evidence["issuedAtUnixMs"], evidence["validForMs"], evidence["retryAfterMs"]
    )
    if (
        evidence["domain"] != CONTROL_BUSY_DOMAIN
        or evidence["managerInstanceId"] != instance_id
        or evidence["code"] != "control_busy"
        or isinstance(issued, bool) or not isinstance(issued, int)
        or isinstance(valid, bool) or not isinstance(valid, int) or not 0 < valid <= 5000
        or isinstance(retry, bool) or not isinstance(retry, int) or not 0 < retry <= 1000
        or not isinstance(evidence["nonce"], str)
        or re.fullmatch(r"[0-9a-f]{32}", evidence["nonce"]) is None
        or not isinstance(signed["signature"], str)
    ):
        raise RuntimeCorruptError("control_busy evidence 无效")
    observed = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if issued > observed or observed > issued + valid:
        raise RuntimeCorruptError("control_busy evidence 已过期或来自未来")
    expected = hmac.new(token.encode("utf-8"), _busy_bytes(evidence), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signed["signature"].encode(), expected.encode()):
        raise RuntimeCorruptError("control_busy HMAC 校验失败")
    return evidence


class ControlRequestGate:
    """在创建 handler thread 前限制并发，并跟踪可排空请求。"""

    def __init__(self, limit: int, token: str, instance_id: str, *, timeout: float = 5.0) -> None:
        self._permits = threading.BoundedSemaphore(limit)
        self._condition = threading.Condition()
        self._active: set[int] = set()
        self.token, self.instance_id, self.timeout = token, instance_id, timeout

    @staticmethod
    def _send(request: Any, status: bytes, value: dict[str, Any]) -> None:
        body = _busy_bytes(value)
        response = (
            b"HTTP/1.1 " + status + b"\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Cache-Control: no-store\r\nConnection: close\r\n\r\n" + body
        )
        try:
            request.sendall(response)
            request.shutdown(SHUT_WR)
            request.settimeout(0.05)
            request.recv(4096)
        except (AttributeError, OSError):
            pass

    def acquire(self, request: Any) -> bool:
        request.settimeout(self.timeout)
        if not self._permits.acquire(blocking=False):
            self._send(
                request, b"503 Service Unavailable",
                control_busy_envelope(self.token, self.instance_id),
            )
            return False
        try:
            with self._condition:
                self._active.add(id(request))
            return True
        except BaseException:
            self._permits.release()
            raise

    def reject_timeout(self, request: Any) -> None:
        self._send(
            request, b"408 Request Timeout", control_timeout_envelope(self.instance_id)
        )

    def release(self, request: Any) -> None:
        with self._condition:
            active = id(request) in self._active
            self._active.discard(id(request))
            self._condition.notify_all()
        if active:
            self._permits.release()

    def active_count(self) -> int:
        with self._condition:
            return len(self._active)

    def drain(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True


def success(operation: str, data: Any, *, instance_id: str | None = None) -> dict[str, Any]:
    meta = {"managerInstanceId": instance_id} if instance_id else {}
    return {"ok": True, "operation": operation, "data": data, "meta": meta}


def failure(
    operation: str,
    error: Exception,
    *,
    instance_id: str | None = None,
    include_diagnostics: bool = True,
) -> dict[str, Any]:
    meta = {"managerInstanceId": instance_id} if instance_id else {}
    if isinstance(error, PMError):
        value = error.public_dict(include_diagnostics=include_diagnostics)
    else:
        value = {
            "code": "internal_error",
            "message": "process-manager 发生未分类错误",
            "retryable": False,
        }
    return {"ok": False, "operation": operation, "error": value, "meta": meta}


def print_json(value: Any, *, pretty: bool = True) -> None:
    if pretty:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)
