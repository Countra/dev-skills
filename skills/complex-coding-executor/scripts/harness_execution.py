#!/usr/bin/env python3
"""executor preflight、status、transition、reconcile 和 final 核心规则。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness_attestation import validate_attestation
from harness_state import (
    commit_evidence_gaps,
    replay_events,
)
from harness_state_io import load_state, state_differences, write_state_atomic
from harness_state_schema import ReplayResult, StateError, read_events
from harness_task_bundle import (
    TaskBundle,
    TaskBundleError,
    load_json_object,
    validate_pointer,
)


class ExecutionError(Exception):
    """executor 门禁不满足。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def planner_checker_path() -> Path:
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "complex-coding-planner" / "scripts" / "harness_plan_check.py"


def run_planner_approval_check(bundle: TaskBundle) -> None:
    checker = planner_checker_path()
    if not checker.is_file():
        raise ExecutionError(
            "TASK_PLANNER_CHECKER_MISSING",
            f"缺少配套 planner checker：{checker}",
        )
    command = [
        sys.executable,
        "-X",
        "utf8",
        "-B",
        str(checker),
        "--task-dir",
        str(bundle.task_dir),
        "--mode",
        "approval",
        "--format",
        "json",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExecutionError(
            "TASK_PLANNER_CHECK_FAILED",
            f"无法运行 planner checker：{exc}",
        ) from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExecutionError(
            "TASK_PLANNER_CHECK_INVALID_OUTPUT",
            "planner checker 未返回合法 JSON。",
        ) from exc
    if result.returncode != 0 or not isinstance(payload, dict) or payload.get("valid") is not True:
        output = (result.stdout or result.stderr).strip()
        raise ExecutionError(
            "TASK_CONTRACT_REJECTED",
            f"planner approval checker 拒绝 task bundle：{output}",
        )


def replay_bundle(bundle: TaskBundle) -> tuple[ReplayResult, dict[str, Any]]:
    attestation = validate_attestation(bundle)
    events = read_events(bundle.ledger_path)
    try:
        replayed = replay_events(
            bundle.contract,
            events,
            initial_timestamp=str(attestation["approved_at"]),
        )
    except StateError as exc:
        raise ExecutionError(exc.code, exc.message) from exc
    return replayed, attestation


def load_snapshot(bundle: TaskBundle) -> dict[str, Any] | None:
    try:
        return load_state(bundle.run_state_path)
    except StateError as exc:
        raise ExecutionError(exc.code, exc.message) from exc


def status_payload(bundle: TaskBundle) -> dict[str, Any]:
    replayed, attestation = replay_bundle(bundle)
    snapshot = load_snapshot(bundle)
    differences = state_differences(snapshot, replayed.state)
    return {
        "task_id": bundle.task_id,
        "plan_revision": bundle.plan_revision,
        "lifecycle": replayed.state["lifecycle"],
        "current_stage_id": replayed.state["current_stage_id"],
        "completed_stage_ids": replayed.state["completed_stage_ids"],
        "remaining_stage_ids": replayed.state["remaining_stage_ids"],
        "stop_condition": replayed.state["stop_condition"],
        "next_action": replayed.state["next_action"],
        "reapproval_required": replayed.state["reapproval_required"],
        "last_event_seq": replayed.state["last_event_seq"],
        "snapshot_exists": snapshot is not None,
        "snapshot_drift": differences,
        "authorizations": attestation["authorizations"],
    }


def require_clean_snapshot(bundle: TaskBundle, replayed: ReplayResult) -> None:
    snapshot = load_snapshot(bundle)
    if replayed.state["last_event_seq"] == 0 and snapshot is None:
        return
    differences = state_differences(snapshot, replayed.state)
    if differences:
        raise ExecutionError(
            "RUN_STATE_DRIFT",
            f"run-state 与 ledger replay 不一致：{json.dumps(differences, ensure_ascii=False, sort_keys=True)}",
        )


def check_preflight(bundle: TaskBundle) -> dict[str, Any]:
    run_planner_approval_check(bundle)
    replayed, attestation = replay_bundle(bundle)
    require_clean_snapshot(bundle, replayed)
    state = replayed.state
    if state["reapproval_required"]:
        raise ExecutionError(
            "RUN_STATE_REAPPROVAL_REQUIRED",
            "任务需要 amendment approval。",
        )
    if state["lifecycle"] == "blocked":
        raise ExecutionError(
            "RUN_STATE_BLOCKED",
            f"任务已阻塞：{state['stop_condition']}",
        )
    if state["lifecycle"] in {"completed", "aborted"}:
        raise ExecutionError(
            "RUN_STATE_NOT_EXECUTABLE",
            f"任务 lifecycle={state['lifecycle']}。",
        )
    return attestation


def check_transition(bundle: TaskBundle) -> dict[str, Any]:
    attestation = check_preflight(bundle)
    replayed, _ = replay_bundle(bundle)
    state = replayed.state
    if state["current_stage_id"] is not None:
        raise ExecutionError(
            "RUN_STATE_STAGE_ACTIVE",
            f"当前 stage 尚未结束：{state['current_stage_id']}",
        )
    if state["lifecycle"] == "approved":
        raise ExecutionError(
            "RUN_STATE_NOT_STARTED",
            "先追加 execution_started。",
        )
    return attestation


def reconcile_snapshot(bundle: TaskBundle) -> dict[str, Any]:
    replayed, _ = replay_bundle(bundle)
    snapshot_error: str | None = None
    try:
        snapshot = load_state(bundle.run_state_path)
    except StateError as exc:
        snapshot = None
        snapshot_error = str(exc)
    if snapshot is not None:
        snapshot_seq = snapshot.get("last_event_seq")
        replay_seq = replayed.state["last_event_seq"]
        if isinstance(snapshot_seq, int) and snapshot_seq > replay_seq:
            raise ExecutionError(
                "RUN_STATE_AHEAD_OF_LEDGER",
                "snapshot.last_event_seq 领先合法 ledger，不能自动修复。",
            )
    differences = state_differences(snapshot, replayed.state)
    if differences or snapshot_error:
        try:
            write_state_atomic(bundle.run_state_path, replayed.state)
        except StateError as exc:
            raise ExecutionError(exc.code, exc.message) from exc
    return {
        "reconciled": bool(differences or snapshot_error),
        "previous_error": snapshot_error,
        "differences": differences,
        "state": replayed.state,
    }


def active_pointer_targets_bundle(bundle: TaskBundle) -> bool:
    if not bundle.pointer_path.is_file():
        return False
    try:
        pointer = load_json_object(
            bundle.pointer_path,
            "active task pointer",
            "TASK_POINTER",
        )
        validate_pointer(pointer, bundle.pointer_path)
    except (TaskBundleError, OSError) as exc:
        raise ExecutionError(
            "TASK_POINTER_INVALID",
            f"无法检查 active pointer closure：{exc}",
        ) from exc
    raw_task_dir = pointer.get("task_dir")
    if not isinstance(raw_task_dir, str):
        raise ExecutionError(
            "TASK_POINTER_INVALID",
            "active-task.task_dir 无效。",
        )
    pointed = Path(raw_task_dir)
    if not pointed.is_absolute():
        pointed = bundle.workspace / pointed
    return pointed.resolve() == bundle.task_dir


def check_final(bundle: TaskBundle) -> dict[str, Any]:
    run_planner_approval_check(bundle)
    replayed, attestation = replay_bundle(bundle)
    require_clean_snapshot(bundle, replayed)
    state = replayed.state
    if state["lifecycle"] != "completed":
        raise ExecutionError(
            "RUN_STATE_FINAL_INCOMPLETE",
            f"final 需要 completed，当前为 {state['lifecycle']}。",
        )
    if state["current_stage_id"] or state["remaining_stage_ids"]:
        raise ExecutionError(
            "RUN_STATE_FINAL_INCOMPLETE",
            "final 时仍有 current/remaining stage。",
        )
    expected_stages = {str(item["id"]) for item in bundle.contract["stages"]}
    if replayed.reviewed_stages != expected_stages:
        raise ExecutionError(
            "RUN_STATE_REVIEW_INCOMPLETE",
            "并非所有 stage 都有 passed review evidence。",
        )
    events = read_events(bundle.ledger_path)
    commit_events = [event for event in events if event.get("type") == "commit_recorded"]
    commit_authorized = attestation["authorizations"]["commit"]
    if commit_events and not commit_authorized:
        raise ExecutionError(
            "ATTESTATION_COMMIT_DENIED",
            "ledger 包含未授权 commit evidence。",
        )
    if commit_authorized:
        missing_stage_commits, missing_final_commit = commit_evidence_gaps(
            bundle.contract,
            events,
        )
        if missing_stage_commits or missing_final_commit:
            raise ExecutionError(
                "RUN_STATE_COMMIT_EVIDENCE_MISSING",
                "已授权提交，但 ledger 未覆盖 contract 的 stage/final commit expectation："
                f"missing stages={missing_stage_commits}, final={missing_final_commit}",
            )
    if active_pointer_targets_bundle(bundle):
        raise ExecutionError(
            "TASK_POINTER_NOT_CLOSED",
            "完成任务仍被 active-task.json 指向。",
        )
    return attestation
