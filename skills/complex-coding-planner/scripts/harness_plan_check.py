#!/usr/bin/env python3
"""校验 managed plan 中真正影响执行与恢复的边界。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from harness_contract import ContractIssue, contract_maps, load_contract


TEMPLATE_MARKERS = (
    "<task-id>",
    "<任务名称>",
    "<阶段名称>",
    "<stage title>",
    "<approved path or module>",
    "<deterministic command or tool>",
)


def _read_plan(path: Path, mode: str) -> tuple[str, list[ContractIssue]]:
    issues: list[ContractIssue] = []
    try:
        plan = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", [
            ContractIssue("error", "PLAN_DOCUMENT_MISSING", "缺少 execution-plan.md。")
        ]
    except (OSError, UnicodeError) as exc:
        return "", [
            ContractIssue(
                "error",
                "PLAN_DOCUMENT_INVALID",
                f"无法读取 execution-plan.md：{exc}",
            )
        ]
    if not plan.strip():
        issues.append(
            ContractIssue("error", "PLAN_DOCUMENT_EMPTY", "execution-plan.md 不能为空。")
        )
        return plan, issues
    if not re.search(r"^#\s+\S", plan, flags=re.MULTILINE):
        issues.append(
            ContractIssue(
                "warning",
                "PLAN_DOCUMENT_TITLE",
                "计划建议包含一个明确标题。",
            )
        )
    if len(plan.splitlines()) > 400:
        issues.append(
            ContractIssue(
                "warning",
                "PLAN_DOCUMENT_VERBOSE",
                "计划超过 400 行，请检查是否重复 contract 或无关资料。",
            )
        )
    if mode == "approval":
        for marker in TEMPLATE_MARKERS:
            if marker in plan:
                issues.append(
                    ContractIssue(
                        "error",
                        "PLAN_DOCUMENT_PLACEHOLDER",
                        f"批准版计划仍包含占位符 {marker}。",
                    )
                )
        if re.search(r"\b(?:TODO|TBD)\b", plan, flags=re.IGNORECASE):
            issues.append(
                ContractIssue(
                    "warning",
                    "PLAN_DOCUMENT_OPEN_NOTE",
                    "批准版计划仍包含 TODO/TBD，请确认它不是阻塞项。",
                )
            )
    return plan, issues


def validate_task(task_dir: Path, mode: str) -> list[ContractIssue]:
    """检查 contract 与计划引用；不要求固定章节或文风。"""

    try:
        resolved = task_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return [
            ContractIssue(
                "error",
                "PLAN_TASK_DIR_INVALID",
                "task-dir 不存在或不可访问。",
            )
        ]
    if not resolved.is_dir():
        return [
            ContractIssue("error", "PLAN_TASK_DIR_INVALID", "task-dir 必须是目录。")
        ]

    contract_path = resolved / "plan-contract.json"
    contract, issues = load_contract(contract_path)
    issues = list(issues)
    plan, plan_issues = _read_plan(resolved / "execution-plan.md", mode)
    issues.extend(plan_issues)

    if contract:
        stages, validations = contract_maps(contract)
        for item_id in [*stages, *validations]:
            if item_id not in plan:
                issues.append(
                    ContractIssue(
                        "error",
                        "PLAN_DOCUMENT_REFERENCE_MISSING",
                        f"execution-plan.md 未提及 {item_id}。",
                    )
                )
        try:
            if contract_path.stat().st_size > 32 * 1024:
                issues.append(
                    ContractIssue(
                        "warning",
                        "PLAN_CONTRACT_VERBOSE",
                        "plan-contract.json 超过 32 KiB，请删除重复的人类说明。",
                    )
                )
        except OSError:
            pass
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 compact managed plan")
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("draft", "approval"), default="draft")
    args = parser.parse_args()
    issues = validate_task(args.task_dir, args.mode)
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    for issue in issues:
        print(f"{issue.severity.upper()} [{issue.code}]: {issue.message}")
    if errors:
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
    else:
        print(f"PASS: core plan contract is valid ({len(warnings)} warning(s)).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
