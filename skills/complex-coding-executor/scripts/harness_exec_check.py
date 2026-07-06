#!/usr/bin/env python3
"""检查 complex-coding-executor 执行前、阶段转移和最终交付状态。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_PLAN_TERMS = [
    "方案批准",
    "执行控制",
    "Git",
    "Process Manager Gate",
    "验证",
    "提交",
    "恢复摘要",
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
    return errors


def check_preflight(active: dict[str, Any], plan: str, task_dir: Path) -> list[str]:
    errors = basic_checks(active, plan, task_dir)
    if active.get("overall_status") not in {"in_progress", "approved"}:
        errors.append("active-task overall_status is not executable")
    if not active.get("current_stage"):
        errors.append("active-task current_stage is empty")
    return errors


def check_transition(active: dict[str, Any], plan: str, task_dir: Path) -> list[str]:
    errors = basic_checks(active, plan, task_dir)
    remaining = remaining_stages(active)
    stop = str(active.get("stop_condition", "none")).lower()
    next_action = str(active.get("next_automatic_action", ""))
    if remaining and stop in {"none", ""} and not next_action.lower().startswith("continue"):
        errors.append("remaining stages exist; next_automatic_action must continue the next stage")
    if remaining and "final" in next_action.lower():
        errors.append("cannot enter final delivery while remaining stages exist")
    return errors


def check_final(active: dict[str, Any], plan: str, task_dir: Path) -> list[str]:
    errors = basic_checks(active, plan, task_dir)
    if remaining_stages(active):
        errors.append("final delivery blocked: remaining_stages is not empty")
    for term in ["验证证据", "代码审查", "提交记录", "最终交付"]:
        if term not in plan:
            errors.append(f"final delivery evidence missing term: {term}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 complex-coding-executor 的执行状态")
    parser.add_argument("--workspace", required=True, help="workspace 根目录")
    parser.add_argument("--task-dir", required=True, help="任务目录，可为相对 workspace 的路径")
    parser.add_argument("--mode", choices=["preflight", "transition", "final"], default="preflight")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    task_dir = Path(args.task_dir)
    if not task_dir.is_absolute():
        task_dir = workspace / task_dir
    active_path = workspace / ".harness" / "active-task.json"
    plan_path = task_dir / "execution-plan.md"

    if not active_path.is_file():
        print(f"FAIL: active-task not found: {active_path}")
        return 2
    if not plan_path.is_file():
        print(f"FAIL: execution-plan not found: {plan_path}")
        return 2

    active = load_json(active_path)
    plan = read_text(plan_path)
    checks = {
        "preflight": check_preflight,
        "transition": check_transition,
        "final": check_final,
    }
    errors = checks[args.mode](active, plan, task_dir)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: {args.mode} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
