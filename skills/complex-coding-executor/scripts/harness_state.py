#!/usr/bin/env python3
"""维护 managed task 的唯一 compact 执行状态。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from harness_state_store import (
    StateError,
    TaskBundle,
    assert_approval_current,
    assert_identity,
    compact_summary,
    digest,
    load_bundle,
    load_state,
    next_stage,
    now,
    stage_signature,
    stage_order,
    write_state,
)


PLANNER_SCRIPTS = Path(__file__).resolve().parents[2] / "complex-coding-planner" / "scripts"
sys.path.insert(0, str(PLANNER_SCRIPTS))
from harness_contract import contract_maps  # noqa: E402


REVIEW_MODES = {"same-context", "independent"}
REVIEW_VERDICTS = {"passed", "changes-required", "blocked"}
VALIDATION_RESULTS = {"passed", "failed", "not-run"}
PERMISSION_ARGUMENTS = {
    "commit": "commit",
    "external_write": "external_write",
    "elevated_tool": "elevated_tool",
}


def _touch(state: dict[str, Any]) -> None:
    state["state_revision"] = int(state.get("state_revision", 0)) + 1


def _required_validations_passed(
    state: dict[str, Any],
    contract: dict[str, Any],
    stage_id: str,
) -> None:
    stages, validations = contract_maps(contract)
    records = state["validations"]
    for validation_id in stages[stage_id]["validation_ids"]:
        definition = validations[validation_id]
        if definition["required"] and records.get(validation_id, {}).get("result") != "passed":
            raise StateError(
                "TASK_VALIDATION_REQUIRED",
                f"{stage_id} 的必需验证 {validation_id} 尚未通过。",
            )


def _review_passed(
    state: dict[str, Any],
    requirement: str,
    scope: str,
) -> None:
    if requirement == "none":
        return
    review = state["reviews"].get(scope)
    if not isinstance(review, dict) or review.get("verdict") != "passed":
        raise StateError("TASK_REVIEW_REQUIRED", f"{scope} 尚无通过的审查。")
    if requirement == "independent" and review.get("mode") != "independent":
        raise StateError(
            "TASK_REVIEW_REQUIRED",
            f"{scope} 必须由 independent reviewer 审查。",
        )


def _assert_permissions_requested(
    contract: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    requested = contract["permissions_requested"]
    unplanned = [
        name
        for name, argument in PERMISSION_ARGUMENTS.items()
        if bool(getattr(args, argument, False)) and requested[name] is not True
    ]
    if unplanned:
        raise StateError(
            "TASK_PERMISSION_NOT_REQUESTED",
            "以下授权未写入批准计划：" + ", ".join(unplanned) + "。",
        )


def approve(bundle: TaskBundle, args: argparse.Namespace) -> dict[str, Any]:
    if not args.implementation:
        raise StateError(
            "TASK_APPROVAL_REQUIRED",
            "approve 必须由明确实施批准触发并传入 --implementation。",
        )
    if bundle.contract["risk"] == "high" and args.plan_review_mode != "independent":
        raise StateError(
            "TASK_REVIEW_REQUIRED",
            "高风险计划必须先完成 independent plan-review。",
        )
    _assert_permissions_requested(bundle.contract, args)

    previous = load_state(bundle.task_dir, required=False)
    if previous and previous.get("task_id") != bundle.contract["task_id"]:
        raise StateError(
            "TASK_ID_MISMATCH",
            "同一 task-dir 不能在新 revision 中更换 task_id。",
        )
    if (
        previous
        and previous.get("lifecycle") == "completed"
        and previous.get("plan_revision") == bundle.contract["plan_revision"]
    ):
        raise StateError("TASK_ALREADY_COMPLETED", "当前 revision 已完成，不能重新启动。")
    if previous and previous.get("plan_revision") == bundle.contract["plan_revision"]:
        try:
            assert_identity(previous, bundle)
            assert_approval_current(previous, bundle)
        except StateError as exc:
            if exc.code not in {"TASK_PLAN_STALE", "TASK_APPROVAL_REQUIRED"}:
                raise
            raise StateError(
                "TASK_REVISION_REQUIRED",
                "重新批准必须更新计划并递增 plan_revision。",
            ) from exc
        raise StateError(
            "TASK_ALREADY_APPROVED",
            "当前 revision 已获批准；继续、resume 或 authorize，而不是再次 approve。",
        )
    if previous and bundle.contract["plan_revision"] <= previous.get("plan_revision", 0):
        raise StateError(
            "TASK_REVISION_REQUIRED",
            "新 plan_revision 必须大于现有状态中的 revision。",
        )
    carry = set(args.carry_completed or [])
    stages, _ = contract_maps(bundle.contract)
    unknown = sorted(carry - set(stages))
    if unknown:
        raise StateError(
            "TASK_STAGE_UNKNOWN",
            f"无法 carry 未知阶段：{', '.join(unknown)}。",
        )
    previous_completed = set(previous.get("completed_stage_ids", [])) if previous else set()
    if not carry <= previous_completed:
        raise StateError(
            "TASK_STAGE_CARRY_INVALID",
            "只能 carry 先前已完成的阶段。",
        )

    carried_validations = {
        validation_id
        for stage_id in carry
        for validation_id in stages[stage_id]["validation_ids"]
    }
    previous_validations = previous.get("validations", {}) if previous else {}
    previous_reviews = previous.get("reviews", {}) if previous else {}
    previous_signatures = (
        previous.get("completed_stage_signatures", {}) if previous else {}
    )
    changed = sorted(
        stage_id
        for stage_id in carry
        if previous_signatures.get(stage_id)
        != stage_signature(bundle.contract, stage_id)
    )
    if changed:
        raise StateError(
            "TASK_STAGE_CARRY_INVALID",
            "以下阶段的执行边界已变化，不能沿用旧完成状态："
            + ", ".join(changed)
            + "。",
        )
    completed = [item for item in stage_order(bundle.contract) if item in carry]
    state = {
        "task_id": bundle.contract["task_id"],
        "plan_revision": bundle.contract["plan_revision"],
        "lifecycle": "approved",
        "approval": {
            "implementation": True,
            "approved_at": now(),
            "plan_sha256": digest(bundle.plan_path),
            "contract_sha256": digest(bundle.contract_path),
            "plan_review": {
                "mode": args.plan_review_mode,
                "summary": compact_summary(args.plan_review_summary, "plan-review summary"),
            },
        },
        "authorizations": {
            "commit": bool(args.commit),
            "external_write": bool(args.external_write),
            "elevated_tool": bool(args.elevated_tool),
        },
        "current_stage_id": None,
        "completed_stage_ids": completed,
        "completed_stage_signatures": {
            stage_id: previous_signatures[stage_id] for stage_id in completed
        },
        "validations": {
            key: value
            for key, value in previous_validations.items()
            if key in carried_validations
        },
        "reviews": {
            key: value for key, value in previous_reviews.items() if key in carry
        },
        "blocker": None,
        "next_action": "",
        "state_revision": int(previous.get("state_revision", -1)) + 1 if previous else 0,
        "updated_at": now(),
    }
    following = next_stage(bundle.contract, completed)
    state["next_action"] = (
        f"start {following}" if following else "run final integration review"
    )
    assert_identity(state, bundle)
    write_state(bundle.task_dir, state)
    return state


def _mutate(
    bundle: TaskBundle,
    command: str,
    operation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    state = load_state(bundle.task_dir)
    assert state is not None
    assert_identity(state, bundle)
    assert_approval_current(state, bundle)
    if state["lifecycle"] == "completed" and command != "authorize":
        raise StateError("TASK_ALREADY_COMPLETED", "任务已经完成。")
    if state["lifecycle"] == "blocked" and command not in {
        "authorize",
        "block",
        "resume",
        "reapproval",
    }:
        raise StateError("TASK_BLOCKED", "任务处于 blocked，先处理 blocker 并 resume。")
    operation(state)
    _touch(state)
    assert_identity(state, bundle)
    write_state(bundle.task_dir, state)
    return state


def status(bundle: TaskBundle) -> dict[str, Any]:
    state = load_state(bundle.task_dir, required=False)
    if state is None:
        return {
            "task_id": bundle.contract["task_id"],
            "lifecycle": "planning",
            "current_stage_id": None,
            "completed_stage_ids": [],
            "next_action": "wait for user approval",
            "blocker": None,
            "approval_current": False,
        }
    try:
        assert_identity(state, bundle)
    except StateError as exc:
        if exc.code != "TASK_PLAN_STALE":
            raise
        return {
            **state,
            "lifecycle": "awaiting_reapproval",
            "approval_current": False,
            "current_stage_id": None,
            "next_action": "review changed plan and request user approval",
        }
    current = True
    try:
        assert_approval_current(state, bundle)
    except StateError as exc:
        if exc.code not in {"TASK_PLAN_STALE", "TASK_APPROVAL_REQUIRED"}:
            raise
        current = False
    result = {**state, "approval_current": current}
    if not current:
        result["lifecycle"] = "awaiting_reapproval"
        result["next_action"] = "review changed plan and request user approval"
    return result


def _print_state(state: dict[str, Any]) -> None:
    print(f"Task: {state['task_id']}")
    print(f"Lifecycle: {state['lifecycle']}")
    print(f"Approval current: {'yes' if state.get('approval_current', True) else 'no'}")
    print(f"Current stage: {state.get('current_stage_id') or 'none'}")
    completed = state.get("completed_stage_ids", [])
    print(f"Completed: {', '.join(completed) if completed else 'none'}")
    print(f"Next: {state.get('next_action') or 'none'}")
    if state.get("blocker"):
        print(f"Blocker: {state['blocker']}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="维护 compact managed task 状态")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--task-dir")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")

    approval = commands.add_parser("approve")
    approval.add_argument("--implementation", action="store_true")
    approval.add_argument("--commit", action="store_true")
    approval.add_argument("--external-write", action="store_true")
    approval.add_argument("--elevated-tool", action="store_true")
    approval.add_argument("--plan-review-mode", choices=sorted(REVIEW_MODES), required=True)
    approval.add_argument("--plan-review-summary", required=True)
    approval.add_argument("--carry-completed", action="append")

    authorization = commands.add_parser("authorize")
    authorization.add_argument("--commit", action="store_true")
    authorization.add_argument("--external-write", action="store_true")
    authorization.add_argument("--elevated-tool", action="store_true")

    start = commands.add_parser("start")
    start.add_argument("--stage", required=True)
    validation = commands.add_parser("validate")
    validation.add_argument("--stage", required=True)
    validation.add_argument("--validation", required=True)
    validation.add_argument("--result", choices=sorted(VALIDATION_RESULTS), required=True)
    validation.add_argument("--exit-code", type=int)
    validation.add_argument("--duration-ms", type=int)
    validation.add_argument("--summary", required=True)
    review = commands.add_parser("review")
    review.add_argument("--scope", required=True)
    review.add_argument("--verdict", choices=sorted(REVIEW_VERDICTS), required=True)
    review.add_argument("--mode", choices=sorted(REVIEW_MODES), required=True)
    review.add_argument("--summary", required=True)
    finish = commands.add_parser("finish-stage")
    finish.add_argument("--stage", required=True)
    block = commands.add_parser("block")
    block.add_argument("--reason", required=True)
    block.add_argument("--next-action", required=True)
    resume = commands.add_parser("resume")
    resume.add_argument("--next-action", required=True)
    reapproval = commands.add_parser("reapproval")
    reapproval.add_argument("--reason", required=True)
    commands.add_parser("complete")
    return parser


def _operate(
    state: dict[str, Any],
    bundle: TaskBundle,
    args: argparse.Namespace,
) -> None:
    stages, validations = contract_maps(bundle.contract)
    if args.command == "authorize":
        if not (args.commit or args.external_write or args.elevated_tool):
            raise StateError(
                "TASK_AUTHORIZATION_INVALID",
                "authorize 至少需要一个明确授权。",
            )
        _assert_permissions_requested(bundle.contract, args)
        current = state["authorizations"]
        current["commit"] = current["commit"] or args.commit
        current["external_write"] = current["external_write"] or args.external_write
        current["elevated_tool"] = current["elevated_tool"] or args.elevated_tool
    elif args.command == "start":
        if args.stage not in stages:
            raise StateError("TASK_STAGE_UNKNOWN", f"未知阶段 {args.stage}。")
        if state["current_stage_id"] is not None:
            raise StateError("TASK_STAGE_ACTIVE", "已有进行中的阶段。")
        if args.stage in state["completed_stage_ids"]:
            raise StateError("TASK_STAGE_COMPLETED", f"{args.stage} 已完成。")
        missing = set(stages[args.stage]["depends_on"]) - set(state["completed_stage_ids"])
        if missing:
            raise StateError(
                "TASK_STAGE_DEPENDENCY",
                f"{args.stage} 仍缺少依赖：{', '.join(sorted(missing))}。",
            )
        state["current_stage_id"] = args.stage
        state["lifecycle"] = "in_progress"
        for validation_id in stages[args.stage]["validation_ids"]:
            state["validations"].pop(validation_id, None)
        state["reviews"].pop(args.stage, None)
        state["blocker"] = None
        state["next_action"] = f"implement and validate {args.stage}"
    elif args.command == "validate":
        if state["current_stage_id"] != args.stage:
            raise StateError("TASK_STAGE_NOT_ACTIVE", f"{args.stage} 不是当前阶段。")
        definition = validations.get(args.validation)
        if definition is None or definition["stage_id"] != args.stage:
            raise StateError(
                "TASK_VALIDATION_UNKNOWN",
                f"{args.validation} 不属于 {args.stage}。",
            )
        if args.result == "passed" and args.exit_code not in {None, 0}:
            raise StateError(
                "TASK_VALIDATION_RESULT_INVALID",
                "passed validation 的 exit code 必须为 0。",
            )
        if args.duration_ms is not None and args.duration_ms < 0:
            raise StateError(
                "TASK_VALIDATION_RESULT_INVALID",
                "duration-ms 不能为负数。",
            )
        state["validations"][args.validation] = {
            "result": args.result,
            "exit_code": args.exit_code,
            "duration_ms": args.duration_ms,
            "summary": compact_summary(args.summary, "validation summary"),
            "recorded_at": now(),
        }
        state["reviews"].pop(args.stage, None)
        state["next_action"] = (
            f"review {args.stage}"
            if args.result == "passed"
            else f"repair and rerun {args.validation}"
        )
    elif args.command == "review":
        if args.scope in stages:
            if state["current_stage_id"] != args.scope:
                raise StateError(
                    "TASK_STAGE_NOT_ACTIVE",
                    f"{args.scope} 不是当前阶段。",
                )
            _required_validations_passed(state, bundle.contract, args.scope)
            requirement = stages[args.scope]["review"]
        elif args.scope == "final":
            if set(state["completed_stage_ids"]) != set(stages):
                raise StateError(
                    "TASK_STAGE_REMAINING",
                    "所有阶段完成后才能记录 final review。",
                )
            requirement = bundle.contract["final_review"]
        else:
            raise StateError(
                "TASK_REVIEW_SCOPE_INVALID",
                "review scope 必须是阶段 ID 或 final。",
            )
        if requirement == "independent" and args.mode != "independent":
            raise StateError(
                "TASK_REVIEW_REQUIRED",
                f"{args.scope} 必须 independent review。",
            )
        state["reviews"][args.scope] = {
            "verdict": args.verdict,
            "mode": args.mode,
            "summary": compact_summary(args.summary, "review summary"),
            "recorded_at": now(),
        }
        if args.verdict == "blocked":
            state["lifecycle"] = "blocked"
            state["blocker"] = f"review blocked: {args.scope}"
        state["next_action"] = (
            f"finish {args.scope}"
            if args.verdict == "passed"
            else f"address review findings for {args.scope}"
        )
    elif args.command == "finish-stage":
        if state["current_stage_id"] != args.stage:
            raise StateError("TASK_STAGE_NOT_ACTIVE", f"{args.stage} 不是当前阶段。")
        _required_validations_passed(state, bundle.contract, args.stage)
        _review_passed(state, stages[args.stage]["review"], args.stage)
        state["completed_stage_ids"].append(args.stage)
        state["completed_stage_signatures"][args.stage] = stage_signature(
            bundle.contract,
            args.stage,
        )
        state["current_stage_id"] = None
        state["lifecycle"] = "approved"
        following = next_stage(bundle.contract, state["completed_stage_ids"])
        state["next_action"] = (
            f"start {following}" if following else "run final integration review"
        )
    elif args.command == "block":
        state["lifecycle"] = "blocked"
        state["blocker"] = compact_summary(args.reason, "blocker", limit=1000)
        state["next_action"] = compact_summary(args.next_action, "next action")
    elif args.command == "resume":
        if state["lifecycle"] != "blocked":
            raise StateError("TASK_NOT_BLOCKED", "只有 blocked 状态可以 resume。")
        state["lifecycle"] = "in_progress" if state["current_stage_id"] else "approved"
        state["blocker"] = None
        state["next_action"] = compact_summary(args.next_action, "next action")
    elif args.command == "reapproval":
        active_stage = state["current_stage_id"]
        if active_stage:
            for validation_id in stages[active_stage]["validation_ids"]:
                state["validations"].pop(validation_id, None)
            state["reviews"].pop(active_stage, None)
        state["lifecycle"] = "awaiting_reapproval"
        state["approval"] = None
        state["current_stage_id"] = None
        state["blocker"] = compact_summary(
            args.reason,
            "reapproval reason",
            limit=1000,
        )
        state["next_action"] = "update plan and request user approval"
    elif args.command == "complete":
        if state["current_stage_id"] is not None:
            raise StateError("TASK_STAGE_ACTIVE", "当前阶段尚未完成。")
        if set(state["completed_stage_ids"]) != set(stages):
            raise StateError("TASK_STAGE_REMAINING", "仍有未完成阶段。")
        _review_passed(state, bundle.contract["final_review"], "final")
        state["lifecycle"] = "completed"
        state["blocker"] = None
        state["next_action"] = "clear active pointer and deliver summary"


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        bundle = load_bundle(args.workspace, args.task_dir)
        if args.command == "status":
            state = status(bundle)
        elif args.command == "approve":
            state = approve(bundle, args)
        else:
            state = _mutate(
                bundle,
                args.command,
                lambda current: _operate(current, bundle, args),
            )
        _print_state(state)
        if args.command == "status" and state["lifecycle"] in {
            "blocked",
            "awaiting_reapproval",
        }:
            return 1
        return 0
    except StateError as exc:
        print(f"FAIL [{exc.code}]: {exc.message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
