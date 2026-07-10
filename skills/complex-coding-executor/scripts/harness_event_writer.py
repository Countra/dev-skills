#!/usr/bin/env python3
"""校验、追加一个 ledger event，并原子刷新 run-state。"""

from __future__ import annotations

from typing import Any

from harness_attestation import AttestationError, validate_attestation
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

    event = build_event(
        bundle.contract,
        len(events) + 1,
        event_type,
        stage_id=stage_id,
        attempt=attempt,
        payload=payload,
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
