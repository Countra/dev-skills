#!/usr/bin/env python3
"""校验 planner task bundle 的结构和跨制品语义。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from harness_contract import (
    ValidationIssue,
    add_issue,
    contains_placeholder,
    load_json_object,
)
from harness_contract_rules import validate_contract


REQUIRED_PLAN_SECTIONS = [
    "规划摘要",
    "问题定义",
    "需求与验收",
    "调研门禁",
    "规范发现门禁",
    "开发质量门禁",
    "上下文",
    "候选方案",
    "决策",
    "影响面矩阵",
    "实施计划",
    "环境",
    "Git",
    "工具",
    "长期进程",
    "验证",
    "文档",
    "文件写入策略",
    "方案质量门禁",
    "规划自查",
    "就绪门禁",
    "方案批准",
    "方案变更门禁",
    "Artifact Index",
    "Executor Handoff",
]

FORBIDDEN_MUTABLE_SECTIONS = [
    "执行控制",
    "实施进度",
    "Ledger Evidence",
    "阶段进入门禁",
    "阶段退出门禁",
    "阶段转移门禁",
    "代码审查",
    "恢复摘要",
    "提交记录",
]

ID_REGEX = {
    "GOAL": re.compile(r"\bGOAL-\d{2,}\b"),
    "REQ": re.compile(r"\bREQ-\d{2,}\b"),
    "AC": re.compile(r"\bAC-\d{2,}\b"),
    "NFR": re.compile(r"\bNFR-\d{2,}\b"),
    "STG": re.compile(r"\bSTG-\d{2,}\b"),
    "VAL": re.compile(r"\bVAL-\d{2,}\b"),
    "ART": re.compile(r"\bART-\d{2,}\b"),
}


def read_text(path: Path, issues: list[ValidationIssue]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        add_issue(issues, "TASK_PLAN_MISSING", "$plan", f"缺少计划：{path}", "创建 execution-plan.md。")
    except (OSError, UnicodeError) as exc:
        add_issue(issues, "TASK_PLAN_UNREADABLE", "$plan", f"无法读取计划：{exc}", "修复文件权限或 UTF-8 编码。")
    return ""


def has_heading(text: str, name: str) -> bool:
    return bool(re.search(rf"^##\s+.*{re.escape(name)}", text, re.MULTILINE))


def section(text: str, name: str) -> str:
    match = re.search(rf"^##\s+.*{re.escape(name)}.*$", text, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end]


def stage_sections(plan: str) -> dict[str, tuple[str, str]]:
    implementation = section(plan, "实施计划")
    matches = list(
        re.finditer(r"^###\s+(STG-\d{2,})\b.*$", implementation, re.MULTILINE)
    )
    result: dict[str, tuple[str, str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(implementation)
        result[match.group(1)] = (match.group(0), implementation[match.end() : end])
    return result


def contract_ids(contract: dict[str, Any]) -> dict[str, set[str]]:
    def ids(field: str) -> set[str]:
        values = contract.get(field, [])
        if not isinstance(values, list):
            return set()
        return {str(item.get("id")) for item in values if isinstance(item, dict) and item.get("id")}

    return {
        "GOAL": {str(contract.get("goal", {}).get("id"))}
        if isinstance(contract.get("goal"), dict) and contract["goal"].get("id")
        else set(),
        "REQ": ids("requirements"),
        "AC": ids("acceptance_criteria"),
        "NFR": ids("nonfunctional_requirements"),
        "STG": ids("stages"),
        "VAL": ids("validations"),
        "ART": ids("artifacts"),
    }


def validation_context(task_dir: Path, contract: dict[str, Any], plan: str) -> str:
    chunks = [plan]
    task_root = task_dir.resolve()
    artifacts = contract.get("artifacts", [])
    if not isinstance(artifacts, list):
        return plan
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("kind") != "research":
            continue
        path = artifact.get("path")
        if isinstance(path, str):
            try:
                artifact_path = (task_dir / path).resolve()
                artifact_path.relative_to(task_root)
                chunks.append(artifact_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                pass
    return "\n".join(chunks)


def validate_plan(
    task_dir: Path,
    contract: dict[str, Any],
    mode: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    plan = read_text(task_dir / "execution-plan.md", issues)
    if not plan:
        return issues

    for name in REQUIRED_PLAN_SECTIONS:
        if not has_heading(plan, name):
            add_issue(
                issues,
                "TASK_PLAN_MISSING_SECTION",
                f"$plan.{name}",
                f"缺少章节：{name}",
                "按 execution-plan 模板补齐。",
            )
    for name in FORBIDDEN_MUTABLE_SECTIONS:
        if has_heading(plan, name):
            add_issue(
                issues,
                "TASK_PLAN_MUTABLE_SECTION",
                f"$plan.{name}",
                f"批准计划不得包含可变执行章节：{name}",
                "把运行状态移到 run-state/ledger。",
            )

    summary = section(plan, "规划摘要")
    task_id = contract.get("task_id")
    if isinstance(task_id, str) and task_id not in summary:
        add_issue(
            issues,
            "TASK_PLAN_CONTRACT_DRIFT",
            "$plan.规划摘要",
            "Task ID 与 contract 不一致。",
            "在 Plan Summary 使用相同 task_id。",
        )
    profile = contract.get("plan_profile")
    if isinstance(profile, str) and profile not in summary:
        add_issue(issues, "TASK_PLAN_CONTRACT_DRIFT", "$plan.规划摘要", "Plan profile 与 contract 不一致。", "同步 profile。")
    revision = contract.get("plan_revision")
    if isinstance(revision, int) and not re.search(
        rf"Plan revision[^\n]*\b{revision}\b",
        summary,
        re.IGNORECASE,
    ):
        add_issue(
            issues,
            "TASK_PLAN_CONTRACT_DRIFT",
            "$plan.规划摘要",
            "Plan revision 与 contract 不一致。",
            "在 Plan Summary 使用相同 plan_revision。",
        )
    route = contract.get("lifecycle_route")
    if isinstance(route, str) and not re.search(
        rf"Lifecycle route[^\n]*\b{re.escape(route)}\b",
        summary,
        re.IGNORECASE,
    ):
        add_issue(
            issues,
            "TASK_PLAN_CONTRACT_DRIFT",
            "$plan.规划摘要",
            "Lifecycle route 与 contract 不一致。",
            "在 Plan Summary 使用相同 lifecycle_route。",
        )

    expected_ids = contract_ids(contract)
    for prefix, expected in expected_ids.items():
        actual = set(ID_REGEX[prefix].findall(plan))
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        for value in missing:
            add_issue(
                issues,
                "TASK_PLAN_MISSING_ID",
                "$plan",
                f"计划未解释 contract ID：{value}",
                "在对应需求、阶段、验证或 artifact 章节引用。",
            )
        for value in extra:
            add_issue(
                issues,
                "TASK_PLAN_EXTRA_ID",
                "$plan",
                f"计划包含 contract 未定义 ID：{value}",
                "同步 plan-contract.json 或删除漂移引用。",
            )

    implementation = section(plan, "实施计划")
    stage_heading_values = re.findall(
        r"^###\s+(STG-\d{2,})\b",
        implementation,
        re.MULTILINE,
    )
    if len(stage_heading_values) != len(set(stage_heading_values)):
        add_issue(
            issues,
            "TASK_PLAN_STAGE_DUPLICATE",
            "$plan.实施计划",
            "同一 Stage heading 出现多次。",
            "每个 contract stage 只保留一个对应章节。",
        )
    plan_stages = stage_sections(plan)
    stage_headings = set(plan_stages)
    if stage_headings != expected_ids["STG"]:
        add_issue(
            issues,
            "TASK_PLAN_STAGE_DRIFT",
            "$plan.实施计划",
            "Stage headings 与 contract stages 不一致。",
            "为每个 STG 写一个且仅一个阶段章节。",
        )
    stages = contract.get("stages", [])
    if isinstance(stages, list):
        for stage in stages:
            if not isinstance(stage, dict) or stage.get("id") not in plan_stages:
                continue
            stage_id = str(stage["id"])
            heading, body = plan_stages[stage_id]
            title = stage.get("title")
            if isinstance(title, str) and title not in heading:
                add_issue(
                    issues,
                    "TASK_PLAN_STAGE_DRIFT",
                    f"$plan.实施计划.{stage_id}",
                    "Stage title 与 contract 不一致。",
                    "同步 stage heading title。",
                )
            stage_text = f"{heading}\n{body}"
            for field in (
                "depends_on",
                "requirement_ids",
                "acceptance_ids",
                "nonfunctional_ids",
                "validation_ids",
                "allowed_changes",
                "forbidden_changes",
            ):
                values = stage.get(field, [])
                if not isinstance(values, list):
                    continue
                for value in values:
                    if isinstance(value, str) and value not in stage_text:
                        add_issue(
                            issues,
                            "TASK_PLAN_STAGE_DRIFT",
                            f"$plan.实施计划.{stage_id}",
                            f"Stage 未解释 contract {field}：{value}",
                            "在对应 Stage Contract 中同步依赖、追踪、验证和 scope。",
                        )

    if mode == "approval":
        if contains_placeholder(plan):
            add_issue(
                issues,
                "TASK_PLAN_PLACEHOLDER",
                "$plan",
                "计划仍包含模板占位符。",
                "用任务真实内容替换占位符。",
            )
        gates = (
            "调研门禁",
            "规范发现门禁",
            "开发质量门禁",
            "方案质量门禁",
            "规划自查",
            "就绪门禁",
        )
        for gate in gates:
            gate_text = section(plan, gate)
            if re.search(r"\bpending\b", gate_text, re.IGNORECASE):
                add_issue(issues, "TASK_PLAN_GATE_PENDING", f"$plan.{gate}", f"{gate} 仍为 pending。", "完成门禁并记录证据。")

        pending_path = task_dir / "pending-decisions.md"
        if pending_path.is_file():
            pending = read_text(pending_path, issues)
            if re.search(r"(?:状态|status)[^\n]*\bopen\b", pending, re.IGNORECASE):
                add_issue(
                    issues,
                    "TASK_PLAN_OPEN_DECISION",
                    "$plan.pending-decisions",
                    "仍有 open 决策。",
                    "关闭决策或停止在 blocked。",
                )

        research = contract.get("research", {})
        if isinstance(research, dict) and research.get("mode") == "online-required":
            if not re.search(r"https?://", validation_context(task_dir, contract, plan)):
                add_issue(
                    issues,
                    "TASK_PLAN_RESEARCH_SOURCE_MISSING",
                    "$plan.调研门禁",
                    "online-required 缺少 URL 证据。",
                    "引用官方或一手来源。",
                )

        options = section(plan, "候选方案")
        option_count = len(re.findall(r"^###\s+", options, re.MULTILINE))
        if option_count < 2 and "只有一个合理方案" not in options:
            add_issue(
                issues,
                "TASK_PLAN_OPTIONS_INCOMPLETE",
                "$plan.候选方案",
                "缺少可区分候选方案。",
                "比较至少两个方案或说明唯一方案的排除依据。",
            )
    return issues


def validate_task(task_dir: Path, mode: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        resolved_task_dir = task_dir.resolve(strict=True)
    except FileNotFoundError:
        add_issue(issues, "TASK_DIR_MISSING", "$", f"任务目录不存在：{task_dir}", "传入已有 task-dir。")
        return issues
    if not resolved_task_dir.is_dir():
        add_issue(issues, "TASK_DIR_INVALID", "$", f"不是任务目录：{resolved_task_dir}", "传入目录路径。")
        return issues

    contract, load_issues = load_json_object(resolved_task_dir / "plan-contract.json")
    issues.extend(load_issues)
    if contract is None:
        return issues
    issues.extend(validate_contract(contract, resolved_task_dir, mode))
    issues.extend(validate_plan(resolved_task_dir, contract, mode))
    return issues


def print_text(issues: list[ValidationIssue], mode: str) -> None:
    for issue in issues:
        print(f"{issue.level.upper()} [{issue.code}] {issue.path}: {issue.message} Hint: {issue.hint}")
    errors = sum(issue.level == "error" for issue in issues)
    warnings = sum(issue.level == "warning" for issue in issues)
    if errors == 0:
        print(f"PASS: {mode} task bundle is valid ({warnings} warning(s))")
    else:
        print(f"FAIL: {errors} error(s), {warnings} warning(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 complex-coding-planner task bundle")
    parser.add_argument("--task-dir", required=True, help="包含 execution-plan.md 和 plan-contract.json 的任务目录")
    parser.add_argument("--mode", choices=["draft", "approval"], default="approval")
    parser.add_argument("--format", choices=["text", "json"], default="text", dest="output_format")
    args = parser.parse_args()

    issues = validate_task(Path(args.task_dir), args.mode)
    if args.output_format == "json":
        errors = sum(issue.level == "error" for issue in issues)
        payload = {
            "mode": args.mode,
            "valid": errors == 0,
            "issues": [issue.to_dict() for issue in issues],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(issues, args.mode)
    return 1 if any(issue.level == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
