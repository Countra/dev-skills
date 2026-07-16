#!/usr/bin/env python3
"""ledger event 与 run-state 的封闭结构定义及基础校验。"""

from __future__ import annotations

import json
import re
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
    "stage_completed",
}

REVIEW_RECORD_FIELDS = {
    "result",
    "review_id",
    "profile",
    "scope",
    "target_digest",
    "verdict",
    "report_ref",
    "open_counts",
    "summary",
}
REVIEW_COUNT_FIELDS = {"blocking", "major", "minor", "advisory", "total"}
REVIEW_VERDICTS = {"passed", "changes_required", "blocked"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
    stage_reviews: dict[str, dict[str, Any]]
    final_review: dict[str, Any] | None
    carried_stage_ids: set[str]
    attempts: dict[str, int]


def _require_review(
    condition: bool,
    code: str,
    message: str,
) -> None:
    if not condition:
        raise StateError(code, message)


def _validate_review_scope(
    scope: Any,
    *,
    stage_id: str | None,
    attempt: int | None,
) -> dict[str, Any]:
    _require_review(
        isinstance(scope, dict),
        "RUN_STATE_REVIEW_SCOPE_INVALID",
        "review payload scope 必须是 object。",
    )
    assert isinstance(scope, dict)
    kind = scope.get("kind")
    if kind == "stage-delta":
        expected_fields = {"kind", "stage_id", "attempt"}
        _require_review(
            set(scope) == expected_fields,
            "RUN_STATE_REVIEW_SCOPE_INVALID",
            "stage-delta scope 必须只包含 kind、stage_id、attempt。",
        )
        _require_review(
            stage_id is not None
            and attempt is not None
            and scope.get("stage_id") == stage_id
            and scope.get("attempt") == attempt,
            "RUN_STATE_REVIEW_SCOPE_MISMATCH",
            "stage-delta scope 必须与 event 的 stage_id/attempt 一致。",
        )
        return scope
    if kind == "final-integration":
        _require_review(
            set(scope) == {"kind"} and stage_id is None and attempt is None,
            "RUN_STATE_REVIEW_SCOPE_MISMATCH",
            "final-integration review 不得绑定 stage_id 或 attempt。",
        )
        return scope
    raise StateError(
        "RUN_STATE_REVIEW_SCOPE_INVALID",
        "managed executor 只接受 stage-delta 或 final-integration review。",
    )


def validate_review_record(
    payload: Any,
    *,
    stage_id: str | None,
    attempt: int | None,
) -> dict[str, Any]:
    """校验 ledger 中由 Reviewer 公共校验器派生的紧凑回执。"""

    _require_review(
        isinstance(payload, dict),
        "RUN_STATE_REVIEW_PAYLOAD_INVALID",
        "review payload 必须是 object。",
    )
    assert isinstance(payload, dict)
    unknown = sorted(set(payload) - REVIEW_RECORD_FIELDS)
    missing = sorted(REVIEW_RECORD_FIELDS - set(payload))
    _require_review(
        not unknown and not missing,
        "RUN_STATE_REVIEW_PAYLOAD_INVALID",
        f"review payload 字段不封闭：unknown={unknown}, missing={missing}",
    )
    _require_review(
        payload.get("profile") == "code-review",
        "RUN_STATE_REVIEW_PROFILE_INVALID",
        "executor review profile 必须是 code-review。",
    )
    scope = _validate_review_scope(
        payload.get("scope"),
        stage_id=stage_id,
        attempt=attempt,
    )
    for field in ("review_id", "report_ref", "summary"):
        value = payload.get(field)
        _require_review(
            isinstance(value, str) and bool(value.strip()),
            "RUN_STATE_REVIEW_PAYLOAD_INVALID",
            f"review payload.{field} 必须是非空字符串。",
        )
    report_ref_text = str(payload["report_ref"])
    report_ref = Path(report_ref_text)
    _require_review(
        not report_ref.is_absolute()
        and "\\" not in report_ref_text
        and ".." not in report_ref.parts
        and tuple(report_ref.parts[:2]) == ("artifacts", "reviews"),
        "RUN_STATE_REVIEW_REPORT_INVALID",
        "review report_ref 必须位于 task-dir 的 artifacts/reviews 下。",
    )
    digest = payload.get("target_digest")
    _require_review(
        isinstance(digest, str) and SHA256.fullmatch(digest) is not None,
        "RUN_STATE_REVIEW_TARGET_INVALID",
        "review target_digest 必须是小写 SHA-256。",
    )
    verdict = payload.get("verdict")
    _require_review(
        verdict in REVIEW_VERDICTS,
        "RUN_STATE_REVIEW_VERDICT_INVALID",
        "review verdict 无效。",
    )
    result = payload.get("result")
    expected_result = "passed" if verdict == "passed" else "failed"
    _require_review(
        result == expected_result,
        "RUN_STATE_REVIEW_RESULT_INVALID",
        f"review result 必须由 verdict 派生为 {expected_result}。",
    )
    counts = payload.get("open_counts")
    _require_review(
        isinstance(counts, dict) and set(counts) == REVIEW_COUNT_FIELDS,
        "RUN_STATE_REVIEW_COUNTS_INVALID",
        "review open_counts 字段不完整。",
    )
    assert isinstance(counts, dict)
    _require_review(
        all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in counts.values()
        )
        and counts["total"]
        == sum(counts[severity] for severity in ("blocking", "major", "minor", "advisory")),
        "RUN_STATE_REVIEW_COUNTS_INVALID",
        "review open_counts 必须是自洽的非负整数。",
    )
    _require_review(
        result != "passed"
        or (counts["blocking"] == 0 and counts["major"] == 0),
        "RUN_STATE_REVIEW_COUNTS_INVALID",
        "passed review 不得包含开放 blocking 或 major finding。",
    )
    return {**payload, "scope": scope}


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
