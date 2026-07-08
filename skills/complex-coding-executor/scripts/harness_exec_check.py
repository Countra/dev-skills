#!/usr/bin/env python3
"""检查 complex-coding-executor 执行前、阶段转移和最终交付状态。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from harness_ledger_summary import read_events, summarize
from harness_task_resolver import ResolverError, resolve_task


REQUIRED_PLAN_TERMS = [
    "执行契约",
    "Goal Condition",
    "Planning Loop Protocol",
    "Executor Work Loop",
    "方案批准",
    "执行控制",
    "Git",
    "Process Manager Gate",
    "验证",
    "提交",
    "恢复摘要",
]

CONTRACT_REQUIRED_FIELDS = [
    "contract_version",
    "task_id",
    "execution_mode",
    "overall_status",
    "approval_status",
    "approved_contract_hash",
    "current_stage_id",
    "remaining_stage_ids",
    "stop_condition",
    "commit_authorization",
    "ledger_policy",
    "single_writer",
    "reapproval_required",
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def section(text: str, name: str) -> str:
    match = re.search(rf"^##+\s+.*{re.escape(name)}.*$", text, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end]


def extract_first_json_block(text: str) -> dict[str, Any] | None:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_approved(plan: str) -> bool:
    approval = section(plan, "方案批准")
    if not approval:
        return False
    lowered = approval.lower()
    if "awaiting" in lowered or "not_requested" in lowered:
        return False
    return "approved" in lowered or "已批准" in approval or "批准按" in approval


def has_open_decision(task_dir: Path) -> bool:
    pending = task_dir / "pending-decisions.md"
    if not pending.exists():
        return False
    text = read_text(pending)
    return bool(re.search(r"状态.*open|Status.*open", text, re.IGNORECASE))


def remaining_stages(active: dict[str, Any]) -> list[str]:
    value = active.get("remaining_stages", [])
    return value if isinstance(value, list) else []


def check_contract(active: dict[str, Any], plan: str) -> list[str]:
    errors: list[str] = []
    contract = extract_first_json_block(section(plan, "执行契约"))
    if contract is None:
        return ["Execution Contract must include a valid json block"]

    for field in CONTRACT_REQUIRED_FIELDS:
        if field not in contract:
            errors.append(f"Execution Contract missing field: {field}")

    comparisons = [
        ("task_id", "task_id"),
        ("execution_mode", "execution_mode"),
        ("overall_status", "overall_status"),
        ("current_stage", "current_stage_id"),
        ("stop_condition", "stop_condition"),
    ]
    for active_key, contract_key in comparisons:
        active_value = active.get(active_key)
        contract_value = contract.get(contract_key)
        if active_value is not None and contract_value is not None and str(active_value) != str(contract_value):
            errors.append(f"active-task {active_key} does not match Execution Contract {contract_key}")

    contract_remaining = contract.get("remaining_stage_ids")
    if isinstance(contract_remaining, list) and remaining_stages(active) != contract_remaining:
        errors.append("active-task remaining_stages does not match Execution Contract remaining_stage_ids")

    if is_approved(plan) and str(contract.get("approval_status", "")).lower() != "approved":
        errors.append("approved plan must set Execution Contract approval_status to approved")

    if "Plan Amendment Gate" not in section(plan, "执行契约"):
        errors.append("Execution Contract must mention Plan Amendment Gate")

    return errors


def check_attestation(plan_path: Path, task_dir: Path) -> list[str]:
    path = task_dir / "attestation.json"
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"attestation is invalid: {exc}"]
    if not isinstance(payload, dict):
        return ["attestation root must be an object"]
    if payload.get("sha256") != sha256_file(plan_path):
        return ["plan hash does not match attestation"]
    return []


def basic_checks(active: dict[str, Any], plan: str, task_dir: Path) -> list[str]:
    errors: list[str] = []
    if not is_approved(plan):
        errors.append("plan is not approved for implementation")
    if has_open_decision(task_dir):
        errors.append("pending-decisions.md contains open decisions")
    for term in REQUIRED_PLAN_TERMS:
        if term not in plan:
            errors.append(f"plan missing required term: {term}")
    if active.get("state_source") and active.get("state_source") != "execution-plan.md":
        errors.append("active-task state_source must be execution-plan.md")
    errors.extend(check_contract(active, plan))
    return errors


def check_preflight(active: dict[str, Any], plan: str, task_dir: Path, plan_path: Path) -> list[str]:
    errors = basic_checks(active, plan, task_dir)
    if active.get("overall_status") not in {"in_progress", "approved"}:
        errors.append("active-task overall_status is not executable")
    if not active.get("current_stage"):
        errors.append("active-task current_stage is empty")
    errors.extend(check_attestation(plan_path, task_dir))
    return errors


def check_transition(active: dict[str, Any], plan: str, task_dir: Path, plan_path: Path) -> list[str]:
    errors = basic_checks(active, plan, task_dir)
    remaining = remaining_stages(active)
    stop = str(active.get("stop_condition", "none")).lower()
    next_action = str(active.get("next_automatic_action", ""))
    if remaining and stop in {"none", ""} and not next_action.lower().startswith("continue"):
        errors.append("remaining stages exist; next_automatic_action must continue the next stage")
    if remaining and "final" in next_action.lower():
        errors.append("cannot enter final delivery while remaining stages exist")
    errors.extend(check_attestation(plan_path, task_dir))
    return errors


def check_final(active: dict[str, Any], plan: str, task_dir: Path, plan_path: Path) -> list[str]:
    errors = basic_checks(active, plan, task_dir)
    if remaining_stages(active):
        errors.append("final delivery blocked: remaining_stages is not empty")
    for term in ["验证证据", "代码审查", "提交记录", "最终交付"]:
        if term not in plan:
            errors.append(f"final delivery evidence missing term: {term}")
    events, parse_errors = read_events(task_dir / "ledger.jsonl")
    if parse_errors:
        errors.append("ledger contains parse errors")
    completed_events = {
        str(event.get("stage"))
        for event in events
        if event.get("event") == "stage_completed" and event.get("stage")
    }
    required_completed = {
        str(stage)
        for stage in active.get("completed_stages", [])
        if re.fullmatch(r"Stage \d+", str(stage))
    }
    missing_completed = sorted(required_completed - completed_events)
    if missing_completed:
        errors.append(f"final delivery blocked: ledger missing stage_completed evidence: {', '.join(missing_completed)}")
    errors.extend(check_attestation(plan_path, task_dir))
    return errors


def check_loop_tick(active: dict[str, Any], plan: str, task_dir: Path, plan_path: Path) -> list[str]:
    errors = check_transition(active, plan, task_dir, plan_path)
    remaining = remaining_stages(active)
    if remaining and not str(active.get("next_automatic_action", "")).lower().startswith("continue"):
        errors.append("loop tick must continue the next remaining stage")
    return errors


def build_status(active: dict[str, Any], plan: str, task_dir: Path, plan_path: Path) -> dict[str, Any]:
    events, parse_errors = read_events(task_dir / "ledger.jsonl")
    ledger_summary = summarize(events, parse_errors)
    return {
        "task_id": active.get("task_id"),
        "status": active.get("status"),
        "overall_status": active.get("overall_status"),
        "execution_mode": active.get("execution_mode"),
        "current_stage": active.get("current_stage"),
        "remaining_stages": remaining_stages(active),
        "remaining_stage_count": len(remaining_stages(active)),
        "next_automatic_action": active.get("next_automatic_action"),
        "stop_condition": active.get("stop_condition"),
        "plan_exists": plan_path.is_file(),
        "ledger_exists": (task_dir / "ledger.jsonl").is_file(),
        "attestation_exists": (task_dir / "attestation.json").is_file(),
        "open_decision": has_open_decision(task_dir),
        "approval_status": "approved" if is_approved(plan) else "not_approved",
        "ledger_summary": ledger_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 complex-coding-executor 的执行状态")
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument("--task-dir", help="任务目录，可为相对 workspace 的路径；省略时读取 active-task.json")
    parser.add_argument(
        "--mode",
        choices=["preflight", "transition", "final", "status", "loop-tick"],
        default="preflight",
    )
    args = parser.parse_args()

    if os.environ.get("HARNESS_DISABLED") == "1":
        print(f"PASS: {args.mode} skipped because HARNESS_DISABLED=1")
        return 0

    try:
        resolved = resolve_task(
            args.workspace,
            args.task_dir,
            require_executable=args.mode in {"preflight", "transition", "loop-tick"},
        )
    except ResolverError as exc:
        print(f"FAIL: {exc}")
        return 2

    active = resolved.active
    plan = read_text(resolved.plan_path)
    if args.mode == "status":
        print(json.dumps(build_status(active, plan, resolved.task_dir, resolved.plan_path), ensure_ascii=False, indent=2))
        return 0

    checks = {
        "preflight": check_preflight,
        "transition": check_transition,
        "final": check_final,
        "loop-tick": check_loop_tick,
    }
    errors = checks[args.mode](active, plan, resolved.task_dir, resolved.plan_path)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: {args.mode} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
