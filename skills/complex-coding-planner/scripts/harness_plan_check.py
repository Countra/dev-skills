#!/usr/bin/env python3
"""检查 complex-coding-planner 生成的 execution-plan.md 结构。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    "问题定义",
    "执行契约",
    "目标条件",
    "规划循环协议",
    "执行循环协议",
    "上下文",
    "调研门禁",
    "候选方案",
    "决策",
    "影响面矩阵",
    "实施计划",
    "环境",
    "Git",
    "工具",
    "验证",
    "文件写入策略",
    "方案质量门禁",
    "规划自查",
    "就绪门禁",
    "方案批准",
    "执行控制",
]

STAGE_REQUIRED_TERMS = ["目标", "做法", "原因", "位置", "验证", "风险", "阶段契约"]

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

GOAL_REQUIRED_TERMS = ["approved stages", "final", "blocking", "验证", "提交"]
PLANNING_LOOP_REQUIRED_TERMS = ["findings", "重读", "rejected options", "Readiness"]
EXECUTOR_LOOP_REQUIRED_TERMS = ["Stage Contract", "ledger", "attempt", "continue Stage", "Goal Condition"]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text()


def has_heading(text: str, name: str) -> bool:
    pattern = re.compile(rf"^##+\s+.*{re.escape(name)}", re.MULTILINE)
    return bool(pattern.search(text))


def section(text: str, name: str) -> str:
    match = re.search(rf"^##+\s+.*{re.escape(name)}.*$", text, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end]


def heading_position(text: str, name: str) -> int:
    match = re.search(rf"^##+\s+.*{re.escape(name)}.*$", text, re.MULTILINE)
    return match.start() if match else -1


def extract_first_json_block(text: str) -> dict[str, object] | None:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def check_terms(section_text: str, terms: list[str], label: str) -> list[str]:
    return [f"{label} missing term: {term}" for term in terms if term not in section_text]


def check_gate_status(section_text: str, gate_name: str) -> list[str]:
    if re.search(r"\|\s*[^|\n]+\|\s*pending\s*\|", section_text, re.IGNORECASE):
        return [f"{gate_name} contains pending status"]
    return []


def check_template_placeholders(text: str) -> list[str]:
    errors: list[str] = []
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if first_line.strip() == "# 执行计划（Execution Plan）":
        errors.append("plan still uses the template title")
    placeholder_patterns = [
        r"<阶段名称>",
        r"<decision-title>",
        r"<这里说明",
        r"<推荐选项>",
        r"<备选项>",
        r"<这里",
    ]
    if any(re.search(pattern, text) for pattern in placeholder_patterns):
        errors.append("plan contains template placeholder markers")
    if "none / local-only / online-required / blocked-by-access" in section(text, "调研门禁"):
        errors.append("Research Gate still contains the template research mode placeholder")
    return errors


def check_research_gate(text: str, allow_template: bool) -> list[str]:
    errors: list[str] = []
    research = section(text, "调研门禁")
    if not research.strip():
        return ["Research Gate section is empty"]
    required_terms = ["研究模式", "不确定项", "搜索记录", "来源矩阵"]
    for term in required_terms:
        if term not in research:
            errors.append(f"Research Gate missing term: {term}")
    if "调研结论" not in research and "Research Gate 结论" not in research:
        errors.append("Research Gate missing term: 调研结论")
    if allow_template:
        return errors
    if "`pending`" in research or re.search(r"调研结论.*pending", research, re.IGNORECASE | re.DOTALL):
        errors.append("Research Gate result is still pending")
    if "online-required" in research and "http" not in research:
        errors.append("online-required Research Gate must include at least one URL/source link")
    if "blocked-by-access" in research and "影响" not in research:
        errors.append("blocked-by-access Research Gate must record impact")
    return errors


def check_plan(text: str, allow_template: bool = False) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_SECTIONS:
        if not has_heading(text, name):
            errors.append(f"missing section: {name}")

    implementation = section(text, "实施计划")
    if not implementation.strip():
        errors.append("missing implementation plan content")
    else:
        stage_count = len(re.findall(r"^###\s+.*Stage|^###\s+.*阶段", implementation, re.MULTILINE))
        if stage_count == 0:
            errors.append("implementation plan has no stage headings")
        for term in STAGE_REQUIRED_TERMS:
            if term not in implementation:
                errors.append(f"implementation plan missing term: {term}")

    gate_order = ["方案质量门禁", "规划自查", "就绪门禁", "方案批准"]
    positions = [heading_position(text, name) for name in gate_order]
    if any(pos < 0 for pos in positions):
        errors.append("approval gate order cannot be checked because a gate is missing")
    elif positions != sorted(positions):
        errors.append("approval gate order must be Plan Quality -> Plan Self-Review -> Readiness -> Plan Approval")

    readiness = section(text, "就绪门禁")
    if "规划自查" not in readiness:
        errors.append("Readiness Gate must confirm Plan Self-Review")
    if "Research Gate" not in readiness and "调研门禁" not in readiness:
        errors.append("Readiness Gate must confirm Research Gate")

    approval = section(text, "方案批准")
    if "提交" not in approval:
        errors.append("Plan Approval must record commit authorization")

    contract = section(text, "执行契约")
    contract_json = extract_first_json_block(contract)
    if contract_json is None:
        errors.append("Execution Contract must include a valid json block")
    else:
        for field in CONTRACT_REQUIRED_FIELDS:
            if field not in contract_json:
                errors.append(f"Execution Contract missing field: {field}")

    if "Plan Amendment Gate" not in contract:
        errors.append("Execution Contract must mention Plan Amendment Gate")

    errors.extend(check_research_gate(text, allow_template))
    errors.extend(check_terms(section(text, "目标条件"), GOAL_REQUIRED_TERMS, "Goal Condition"))
    errors.extend(check_terms(section(text, "规划循环协议"), PLANNING_LOOP_REQUIRED_TERMS, "Planning Loop Protocol"))
    errors.extend(check_terms(section(text, "执行循环协议"), EXECUTOR_LOOP_REQUIRED_TERMS, "Executor Work Loop"))
    if not allow_template:
        errors.extend(check_template_placeholders(text))
        errors.extend(check_gate_status(section(text, "方案质量门禁"), "Plan Quality Gate"))
        errors.extend(check_gate_status(readiness, "Readiness Gate"))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 complex-coding-planner 的执行计划结构")
    parser.add_argument("--plan", required=True, help="execution-plan.md 的路径")
    parser.add_argument("--allow-template", action="store_true", help="允许模板占位内容通过结构检查")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"FAIL: plan not found: {plan_path}", file=sys.stderr)
        return 2

    errors = check_plan(read_text(plan_path), allow_template=args.allow_template)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print("PASS: plan structure is ready for approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
