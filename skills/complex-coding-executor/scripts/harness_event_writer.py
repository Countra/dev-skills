#!/usr/bin/env python3
"""校验、追加一个 ledger event，并原子刷新 run-state。"""

from __future__ import annotations

from typing import Any

from harness_attestation import AttestationError, validate_attestation
from harness_review import ReviewGateError, validate_review_gate
from harness_state import (
    commit_evidence_gaps,
    replay_events,
)
from harness_state_io import (
    append_event,
    build_event,
    load_state,
    state_differences,
    write_state_atomic,
)
from harness_state_schema import StateError, read_events
from harness_task_bundle import TaskBundle


class EventWriteError(Exception):
    """候选事件或持久化动作失败。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def append_event_and_update(
    bundle: TaskBundle,
    event_type: str,
    *,
    stage_id: str | None = None,
    attempt: int | None = None,
    payload: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    occurred_at: str | None = None,
    amendment_activation: bool = False,
) -> dict[str, Any]:
    try:
        attestation = validate_attestation(bundle)
        events = read_events(bundle.ledger_path)
        existing = replay_events(
            bundle.contract,
            events,
            initial_timestamp=str(attestation["approved_at"]),
        )
        snapshot = load_state(bundle.run_state_path)
    except (AttestationError, StateError) as exc:
        raise EventWriteError(exc.code, exc.message) from exc

    if event_type == "commit_recorded" and not attestation["authorizations"]["commit"]:
        raise EventWriteError(
            "ATTESTATION_COMMIT_DENIED",
            "用户未授权 commit，不能记录 commit evidence。",
        )
    if event_type == "amendment_approved" and not amendment_activation:
        raise EventWriteError(
            "AMENDMENT_EVENT_REQUIRES_ACTIVATION",
            "amendment_approved 只能由经过归档校验的 activate-amendment 写入。",
        )
    if event_type == "completed" and attestation["authorizations"]["commit"]:
        missing_stages, missing_final = commit_evidence_gaps(
            bundle.contract,
            events,
        )
        if missing_stages or missing_final:
            raise EventWriteError(
                "RUN_STATE_COMMIT_EVIDENCE_MISSING",
                "completed 前缺少已授权的 stage/final commit evidence："
                f"missing stages={missing_stages}, final={missing_final}",
            )
    event_payload = payload or {}
    if event_type == "review_recorded":
        report_ref = event_payload.get("report_ref")
        if not isinstance(report_ref, str) or report_ref not in (evidence_refs or []):
            raise EventWriteError(
                "RUN_STATE_REVIEW_EVIDENCE_MISSING",
                "review_recorded.evidence_refs 必须包含 payload.report_ref。",
            )
    if event_type == "validation_recorded" and event_payload.get("result") == "passed":
        if not evidence_refs:
            raise EventWriteError(
                "RUN_STATE_VALIDATION_EVIDENCE_MISSING",
                "passed validation_recorded 必须引用至少一个 task-local evidence 文件。",
            )
    for ref in evidence_refs or []:
        candidate = (bundle.task_dir / ref).resolve()
        try:
            candidate.relative_to(bundle.task_dir)
        except ValueError as exc:
            raise EventWriteError(
                "LEDGER_EVIDENCE_INVALID",
                f"evidence ref 越出 task-dir：{ref}",
            ) from exc
        if not candidate.is_file():
            raise EventWriteError(
                "LEDGER_EVIDENCE_MISSING",
                f"evidence ref 不存在或不是文件：{ref}",
            )

    if events or snapshot is not None:
        differences = state_differences(snapshot, existing.state)
        if differences:
            raise EventWriteError(
                "RUN_STATE_DRIFT",
                "append 前 snapshot 与 ledger 不一致；先运行 reconcile。",
            )

    try:
        final_commit_recorded = any(
            item.get("type") == "commit_recorded" and item.get("stage_id") is None
            for item in events
        )
        if event_type == "review_recorded":
            validate_review_gate(
                bundle,
                event_payload,
                stage_id=stage_id,
                attempt=attempt,
                final_commit_recorded=final_commit_recorded,
                require_lifecycle_baseline=True,
            )
        elif event_type == "stage_completed" and stage_id is not None:
            stage_review = existing.stage_reviews.get(stage_id)
            if stage_review is not None:
                validate_review_gate(
                    bundle,
                    stage_review,
                    stage_id=stage_id,
                    attempt=existing.attempts.get(stage_id),
                )
        elif event_type == "completed" and existing.final_review is not None:
            validate_review_gate(
                bundle,
                existing.final_review,
                stage_id=None,
                attempt=None,
                final_commit_recorded=final_commit_recorded,
                require_lifecycle_baseline=True,
            )
    except ReviewGateError as exc:
        raise EventWriteError(exc.code, exc.message) from exc

    event = build_event(
        bundle.contract,
        len(events) + 1,
        event_type,
        stage_id=stage_id,
        attempt=attempt,
        payload=event_payload,
        evidence_refs=evidence_refs,
        occurred_at=occurred_at,
    )
    try:
        candidate = replay_events(
            bundle.contract,
            [*events, event],
            initial_timestamp=str(attestation["approved_at"]),
        )
        append_event(bundle.ledger_path, event)
        write_state_atomic(bundle.run_state_path, candidate.state)
    except StateError as exc:
        raise EventWriteError(exc.code, exc.message) from exc
    return {"event": event, "state": candidate.state}
