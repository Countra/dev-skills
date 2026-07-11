#!/usr/bin/env python3
"""ledger event 与 run-state 的封闭结构定义及基础校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness_time import parse_rfc3339


EVENT_FIELDS = {
    "seq",
    "event_id",
    "occurred_at",
    "task_id",
    "plan_revision",
    "stage_id",
    "type",
    "attempt",
    "payload",
    "evidence_refs",
}

EVENT_TYPES = {
    "execution_started",
    "stage_started",
    "attempt_failed",
    "validation_recorded",
    "review_recorded",
    "stage_completed",
    "blocked",
    "resumed",
    "research_drift",
    "amendment_requested",
    "amendment_approved",
    "commit_recorded",
    "completed",
    "aborted",
    "note",
    "heartbeat",
}

STATE_FIELDS = {
    "task_id",
    "plan_revision",
    "lifecycle",
    "current_stage_id",
    "completed_stage_ids",
    "remaining_stage_ids",
    "stop_condition",
    "next_action",
    "reapproval_required",
    "last_event_seq",
    "state_revision",
    "updated_at",
}

STAGE_EVENT_TYPES = {
    "stage_started",
    "attempt_failed",
    "validation_recorded",
    "review_recorded",
    "stage_completed",
}


class StateError(Exception):
    """ledger 或 run-state 违反状态机约束。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


@dataclass(frozen=True)
class ReplayResult:
    state: dict[str, Any]
    passed_validations: dict[str, set[str]]
    reviewed_stages: set[str]
    attempts: dict[str, int]


def parse_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise StateError("LEDGER_INVALID_TIMESTAMP", "occurred_at 必须是 RFC3339 字符串。")
    try:
        parse_rfc3339(value)
    except ValueError as exc:
        raise StateError("LEDGER_INVALID_TIMESTAMP", f"occurred_at 无效：{value}") from exc


def validate_event(
    event: dict[str, Any],
    expected_seq: int,
    contract: dict[str, Any],
    known_stages: set[str],
) -> None:
    unknown = sorted(set(event) - EVENT_FIELDS)
    missing = sorted(EVENT_FIELDS - set(event))
    if unknown:
        raise StateError(
            "LEDGER_UNKNOWN_FIELD",
            f"event {expected_seq} 包含未知字段：{', '.join(unknown)}",
        )
    if missing:
        raise StateError(
            "LEDGER_MISSING_FIELD",
            f"event {expected_seq} 缺少字段：{', '.join(missing)}",
        )
    if event.get("seq") != expected_seq:
        raise StateError(
            "LEDGER_SEQUENCE_GAP",
            f"期望 seq={expected_seq}，实际为 {event.get('seq')}。",
        )
    if event.get("event_id") != f"EVT-{expected_seq:06d}":
        raise StateError(
            "LEDGER_EVENT_ID_INVALID",
            f"seq={expected_seq} 的 event_id 必须是 EVT-{expected_seq:06d}。",
        )
    parse_timestamp(event.get("occurred_at"))
    if event.get("task_id") != contract.get("task_id"):
        raise StateError("LEDGER_TASK_MISMATCH", "event.task_id 与 contract 不一致。")
    if event.get("plan_revision") != contract.get("plan_revision"):
        raise StateError(
            "LEDGER_REVISION_MISMATCH",
            "event.plan_revision 与当前 contract 不一致。",
        )
    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise StateError("LEDGER_EVENT_TYPE_INVALID", f"未知 event type：{event_type}")
    stage_id = event.get("stage_id")
    if stage_id is not None and stage_id not in known_stages:
        raise StateError("LEDGER_STAGE_UNKNOWN", f"未知 stage_id：{stage_id}")
    if event_type in STAGE_EVENT_TYPES and stage_id is None:
        raise StateError("LEDGER_STAGE_REQUIRED", f"{event_type} 必须包含 stage_id。")
    attempt = event.get("attempt")
    if attempt is not None and (
        not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1
    ):
        raise StateError("LEDGER_ATTEMPT_INVALID", "attempt 必须是正整数或 null。")
    if event_type in {"stage_started", "attempt_failed"} and attempt is None:
        raise StateError("LEDGER_ATTEMPT_REQUIRED", f"{event_type} 必须包含 attempt。")
    if not isinstance(event.get("payload"), dict):
        raise StateError("LEDGER_PAYLOAD_INVALID", "payload 必须是 object。")
    refs = event.get("evidence_refs")
    if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
        raise StateError("LEDGER_EVIDENCE_INVALID", "evidence_refs 必须是字符串数组。")
    for ref in refs:
        path = Path(ref)
        if path.is_absolute() or ".." in path.parts:
            raise StateError(
                "LEDGER_EVIDENCE_INVALID",
                f"evidence ref 必须是 task-dir 内相对路径：{ref}",
            )


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise StateError("LEDGER_UNREADABLE", f"无法读取 ledger：{path}: {exc}") from exc
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateError(
                "LEDGER_INVALID_JSON",
                f"ledger line {line_no} 无效：{exc}",
            ) from exc
        if not isinstance(value, dict):
            raise StateError(
                "LEDGER_INVALID_TYPE",
                f"ledger line {line_no} 必须是 object。",
            )
        events.append(value)
    return events
