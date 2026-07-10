#!/usr/bin/env python3
"""顺序 ledger、状态 reducer 和原子 snapshot helpers。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_state_schema import (
    ReplayResult,
    StateError,
    validate_event,
)


def stage_definitions(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stages = contract.get("stages")
    if not isinstance(stages, list):
        raise StateError("TASK_CONTRACT_INVALID_FIELD", "contract.stages 必须是数组。")
    result: dict[str, dict[str, Any]] = {}
    for item in stages:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise StateError("TASK_CONTRACT_INVALID_FIELD", "每个 stage 必须包含字符串 id。")
        result[item["id"]] = item
    if not result:
        raise StateError("TASK_CONTRACT_INVALID_FIELD", "contract.stages 不能为空。")
    return result


def stage_order(contract: dict[str, Any]) -> list[str]:
    definitions = stage_definitions(contract)
    remaining = set(definitions)
    ordered: list[str] = []
    while remaining:
        ready = sorted(
            stage_id
            for stage_id in remaining
            if set(definitions[stage_id].get("depends_on", [])) <= set(ordered)
        )
        if not ready:
            raise StateError("TASK_CONTRACT_STAGE_CYCLE", "Stage DAG 无法拓扑排序。")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def required_validation_ids(contract: dict[str, Any]) -> set[str]:
    validations = contract.get("validations")
    if not isinstance(validations, list):
        raise StateError(
            "TASK_CONTRACT_INVALID_FIELD",
            "contract.validations 必须是数组。",
        )
    return {
        str(item["id"])
        for item in validations
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item.get("required") is True
    }


def initial_state(
    contract: dict[str, Any],
    *,
    updated_at: str | None = None,
) -> dict[str, Any]:
    ordered_stages = stage_order(contract)
    return {
        "task_id": contract["task_id"],
        "plan_revision": contract["plan_revision"],
        "lifecycle": "approved",
        "current_stage_id": None,
        "completed_stage_ids": [],
        "remaining_stage_ids": ordered_stages,
        "stop_condition": None,
        "next_action": f"start {ordered_stages[0]}",
        "reapproval_required": False,
        "last_event_seq": 0,
        "state_revision": 0,
        "updated_at": updated_at,
    }


def next_ready_stage(
    state: dict[str, Any],
    definitions: dict[str, dict[str, Any]],
) -> str | None:
    completed = set(state["completed_stage_ids"])
    for stage_id in state["remaining_stage_ids"]:
        dependencies = set(definitions[stage_id].get("depends_on", []))
        if dependencies <= completed:
            return stage_id
    return None


def update_next_action(
    state: dict[str, Any],
    definitions: dict[str, dict[str, Any]],
) -> None:
    if state["lifecycle"] == "blocked":
        state["next_action"] = "await resolution or amendment approval"
    elif state["lifecycle"] in {"completed", "aborted"}:
        state["next_action"] = None
    elif state["current_stage_id"]:
        state["next_action"] = f"continue {state['current_stage_id']}"
    else:
        ready = next_ready_stage(state, definitions)
        state["next_action"] = f"start {ready}" if ready else "finalize task"


def commit_evidence_gaps(
    contract: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[list[str], bool]:
    stage_expected = {
        str(item["id"])
        for item in contract.get("stages", [])
        if isinstance(item, dict)
        and item.get("commit_expectation") == "stage"
    }
    final_expected = any(
        isinstance(item, dict) and item.get("commit_expectation") == "final"
        for item in contract.get("stages", [])
    )
    commit_events = [
        event for event in events if event.get("type") == "commit_recorded"
    ]
    committed_stage_ids = {
        str(event["stage_id"])
        for event in commit_events
        if event.get("stage_id") is not None
    }
    final_recorded = any(
        event.get("stage_id") is None for event in commit_events
    )
    return sorted(stage_expected - committed_stage_ids), (
        final_expected and not final_recorded
    )


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise StateError(code, message)


def require_payload_strings(
    payload: dict[str, Any],
    event_type: str,
    fields: tuple[str, ...],
) -> None:
    for field in fields:
        value = payload.get(field)
        require(
            isinstance(value, str) and bool(value.strip()),
            "RUN_STATE_EVENT_EVIDENCE_INVALID",
            f"{event_type}.payload.{field} 必须是非空字符串。",
        )


def apply_event(
    state: dict[str, Any],
    event: dict[str, Any],
    definitions: dict[str, dict[str, Any]],
    passed_validations: dict[str, set[str]],
    reviewed_stages: set[str],
    attempts: dict[str, int],
    required_validations: set[str],
) -> None:
    event_type = str(event["type"])
    stage_id = event.get("stage_id")
    payload = event["payload"]

    require(
        state["lifecycle"] not in {"completed", "aborted"},
        "RUN_STATE_TERMINAL",
        f"终态 {state['lifecycle']} 不允许追加事件。",
    )

    if event_type == "execution_started":
        require(
            state["lifecycle"] == "approved",
            "RUN_STATE_ILLEGAL_TRANSITION",
            "execution_started 只允许从 approved 开始。",
        )
        state["lifecycle"] = "in_progress"
    elif event_type == "stage_started":
        require(
            state["lifecycle"] == "in_progress",
            "RUN_STATE_ILLEGAL_TRANSITION",
            "stage_started 只允许在 in_progress。",
        )
        require(
            state["current_stage_id"] is None,
            "RUN_STATE_STAGE_ALREADY_ACTIVE",
            f"当前仍在执行 {state['current_stage_id']}。",
        )
        require(
            stage_id in state["remaining_stage_ids"],
            "RUN_STATE_STAGE_NOT_REMAINING",
            f"stage 不在 remaining：{stage_id}",
        )
        dependencies = set(definitions[str(stage_id)].get("depends_on", []))
        require(
            dependencies <= set(state["completed_stage_ids"]),
            "RUN_STATE_STAGE_DEPENDENCY",
            f"stage 依赖尚未完成：{stage_id}",
        )
        expected_attempt = attempts.get(str(stage_id), 0) + 1
        require(
            event["attempt"] == expected_attempt,
            "RUN_STATE_ATTEMPT_SEQUENCE",
            f"{stage_id} 期望 attempt={expected_attempt}。",
        )
        attempts[str(stage_id)] = expected_attempt
        if expected_attempt > 1:
            passed_validations.pop(str(stage_id), None)
            reviewed_stages.discard(str(stage_id))
        state["current_stage_id"] = stage_id
    elif event_type == "attempt_failed":
        require(
            state["current_stage_id"] == stage_id,
            "RUN_STATE_STAGE_MISMATCH",
            "attempt_failed 必须对应当前 stage。",
        )
        require(
            event["attempt"] == attempts.get(str(stage_id)),
            "RUN_STATE_ATTEMPT_SEQUENCE",
            "attempt_failed.attempt 与当前 attempt 不一致。",
        )
        require_payload_strings(
            payload,
            event_type,
            ("reason", "impact", "next_strategy"),
        )
        passed_validations.pop(str(stage_id), None)
        reviewed_stages.discard(str(stage_id))
        state["current_stage_id"] = None
    elif event_type == "validation_recorded":
        require(
            state["current_stage_id"] == stage_id,
            "RUN_STATE_STAGE_MISMATCH",
            "validation_recorded 必须对应当前 stage。",
        )
        validation_id = payload.get("validation_id")
        allowed_ids = set(definitions[str(stage_id)].get("validation_ids", []))
        require(
            validation_id in allowed_ids,
            "RUN_STATE_VALIDATION_UNKNOWN",
            f"stage 未声明 validation：{validation_id}",
        )
        result = payload.get("result")
        require(
            result in {"passed", "failed"},
            "RUN_STATE_VALIDATION_RESULT_INVALID",
            "validation result 必须是 passed 或 failed。",
        )
        if result == "passed":
            require_payload_strings(payload, event_type, ("summary",))
            passed_validations.setdefault(str(stage_id), set()).add(validation_id)
        else:
            require_payload_strings(payload, event_type, ("reason",))
            passed_validations.setdefault(str(stage_id), set()).discard(validation_id)
            reviewed_stages.discard(str(stage_id))
    elif event_type == "review_recorded":
        require(
            state["current_stage_id"] == stage_id,
            "RUN_STATE_STAGE_MISMATCH",
            "review_recorded 必须对应当前 stage。",
        )
        result = payload.get("result")
        require(
            result in {"passed", "failed"},
            "RUN_STATE_REVIEW_RESULT_INVALID",
            "review result 必须是 passed 或 failed。",
        )
        if result == "passed":
            require_payload_strings(payload, event_type, ("summary",))
            require(
                payload.get("development_quality") == "passed",
                "RUN_STATE_DEVELOPMENT_QUALITY_INCOMPLETE",
                "passed review 必须记录 development_quality=passed。",
            )
            reviewed_stages.add(str(stage_id))
        else:
            require_payload_strings(payload, event_type, ("finding",))
            reviewed_stages.discard(str(stage_id))
    elif event_type == "stage_completed":
        require(
            state["current_stage_id"] == stage_id,
            "RUN_STATE_STAGE_MISMATCH",
            "stage_completed 必须对应当前 stage。",
        )
        required_ids = set(
            definitions[str(stage_id)].get("validation_ids", [])
        ) & required_validations
        require(
            required_ids <= passed_validations.get(str(stage_id), set()),
            "RUN_STATE_VALIDATION_INCOMPLETE",
            f"stage 必需验证未全部通过：{stage_id}",
        )
        require(
            str(stage_id) in reviewed_stages,
            "RUN_STATE_REVIEW_INCOMPLETE",
            f"stage review 尚未通过：{stage_id}",
        )
        state["current_stage_id"] = None
        state["completed_stage_ids"].append(stage_id)
        state["remaining_stage_ids"].remove(stage_id)
    elif event_type == "blocked":
        require(
            state["lifecycle"] in {"approved", "in_progress"},
            "RUN_STATE_ILLEGAL_TRANSITION",
            "blocked 只允许从 approved 或 in_progress 进入。",
        )
        require_payload_strings(payload, event_type, ("reason",))
        reason = str(payload["reason"])
        state["lifecycle"] = "blocked"
        state["stop_condition"] = reason
    elif event_type in {"research_drift", "amendment_requested"}:
        require(
            state["lifecycle"] in {"approved", "in_progress", "blocked"},
            "RUN_STATE_ILLEGAL_TRANSITION",
            f"{event_type} 不允许从 {state['lifecycle']} 进入。",
        )
        required_fields = (
            ("reason", "source", "impact")
            if event_type == "research_drift"
            else ("reason",)
        )
        require_payload_strings(payload, event_type, required_fields)
        state["lifecycle"] = "blocked"
        state["reapproval_required"] = True
        state["stop_condition"] = str(payload.get("reason") or event_type)
    elif event_type == "resumed":
        require(
            state["lifecycle"] == "blocked",
            "RUN_STATE_ILLEGAL_TRANSITION",
            "resumed 只允许从 blocked 进入。",
        )
        require(
            not state["reapproval_required"],
            "RUN_STATE_REAPPROVAL_REQUIRED",
            "需要 amendment approval，不能直接 resumed。",
        )
        require_payload_strings(payload, event_type, ("resolution",))
        state["lifecycle"] = "in_progress"
        state["stop_condition"] = None
    elif event_type == "amendment_approved":
        require(
            state["lifecycle"] == "approved" and state["last_event_seq"] == 0,
            "RUN_STATE_ILLEGAL_TRANSITION",
            "amendment_approved 必须是新 revision ledger 的首条事件。",
        )
        previous_revision = payload.get("previous_revision")
        require(
            isinstance(previous_revision, int)
            and previous_revision == state["plan_revision"] - 1,
            "RUN_STATE_AMENDMENT_LINK_INVALID",
            "previous_revision 必须紧邻当前 plan_revision。",
        )
        archive_path = payload.get("previous_archive")
        require(
            isinstance(archive_path, str)
            and archive_path
            and not Path(archive_path).is_absolute()
            and ".." not in Path(archive_path).parts,
            "RUN_STATE_AMENDMENT_LINK_INVALID",
            "previous_archive 必须是安全相对路径。",
        )
        ledger_hash = payload.get("previous_ledger_sha256")
        require(
            isinstance(ledger_hash, str) and len(ledger_hash) == 64,
            "RUN_STATE_AMENDMENT_LINK_INVALID",
            "previous_ledger_sha256 必须是 SHA-256。",
        )
        carried = payload.get("carried_completed_stage_ids")
        require(
            isinstance(carried, list)
            and all(isinstance(item, str) for item in carried),
            "RUN_STATE_AMENDMENT_CARRY_INVALID",
            "carried_completed_stage_ids 必须是字符串数组。",
        )
        carried_set = set(carried)
        require(
            len(carried_set) == len(carried) and carried_set <= set(definitions),
            "RUN_STATE_AMENDMENT_CARRY_INVALID",
            "继承 stages 重复或不属于当前 contract。",
        )
        for carried_stage in carried_set:
            dependencies = set(definitions[carried_stage].get("depends_on", []))
            require(
                dependencies <= carried_set,
                "RUN_STATE_AMENDMENT_CARRY_INVALID",
                f"继承 stage 缺少依赖：{carried_stage}",
            )
        ordered = [item for item in state["remaining_stage_ids"] if item in carried_set]
        state["completed_stage_ids"] = ordered
        state["remaining_stage_ids"] = [
            item for item in state["remaining_stage_ids"] if item not in carried_set
        ]
        for carried_stage in carried_set:
            reviewed_stages.add(carried_stage)
            passed_validations[carried_stage] = set(
                definitions[carried_stage].get("validation_ids", [])
            )
        state["lifecycle"] = "in_progress"
        state["reapproval_required"] = False
        state["stop_condition"] = None
    elif event_type == "commit_recorded":
        require(
            state["lifecycle"] == "in_progress",
            "RUN_STATE_ILLEGAL_TRANSITION",
            "commit_recorded 只允许在 completed 事件之前记录。",
        )
        commit = payload.get("commit")
        require(
            isinstance(commit, str)
            and 7 <= len(commit) <= 64
            and all(character in "0123456789abcdefABCDEF" for character in commit),
            "RUN_STATE_COMMIT_EVIDENCE_INVALID",
            "commit_recorded.payload.commit 必须是 7-64 位十六进制 hash。",
        )
        require_payload_strings(payload, event_type, ("repository",))
        if stage_id is None:
            final_expected = any(
                item.get("commit_expectation") == "final"
                for item in definitions.values()
            )
            require(
                final_expected
                and state["current_stage_id"] is None
                and not state["remaining_stage_ids"],
                "RUN_STATE_COMMIT_TIMING_INVALID",
                "final commit 必须在所有 stage 完成后按 contract 记录。",
            )
        else:
            require(
                definitions[str(stage_id)].get("commit_expectation") == "stage"
                and stage_id in state["completed_stage_ids"],
                "RUN_STATE_COMMIT_TIMING_INVALID",
                "stage commit 必须在对应 stage 完成后按 contract 记录。",
            )
    elif event_type == "completed":
        require(
            state["lifecycle"] == "in_progress"
            and state["current_stage_id"] is None
            and not state["remaining_stage_ids"],
            "RUN_STATE_FINAL_INCOMPLETE",
            "仍有未完成 stage，不能 completed。",
        )
        state["lifecycle"] = "completed"
    elif event_type == "aborted":
        require(
            state["lifecycle"] != "completed",
            "RUN_STATE_ILLEGAL_TRANSITION",
            "completed task 不能 aborted。",
        )
        require_payload_strings(payload, event_type, ("reason",))
        state["lifecycle"] = "aborted"


def replay_events(
    contract: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    initial_timestamp: str | None = None,
) -> ReplayResult:
    state = initial_state(contract, updated_at=initial_timestamp)
    definitions = stage_definitions(contract)
    passed_validations: dict[str, set[str]] = {}
    reviewed_stages: set[str] = set()
    attempts: dict[str, int] = {}
    required_validations = required_validation_ids(contract)
    for expected_seq, event in enumerate(events, start=1):
        validate_event(event, expected_seq, contract, set(definitions))
        apply_event(
            state,
            event,
            definitions,
            passed_validations,
            reviewed_stages,
            attempts,
            required_validations,
        )
        state["last_event_seq"] = expected_seq
        state["state_revision"] = expected_seq
        state["updated_at"] = event["occurred_at"]
        update_next_action(state, definitions)
    return ReplayResult(state, passed_validations, reviewed_stages, attempts)
