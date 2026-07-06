#!/usr/bin/env python3
"""检查 complex-coding-planner 生成的 execution-plan.md 结构。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    "问题定义",
    "上下文",
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


def check_plan(text: str) -> list[str]:
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

    approval = section(text, "方案批准")
    if "提交" not in approval:
        errors.append("Plan Approval must record commit authorization")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 complex-coding-planner 的执行计划结构")
    parser.add_argument("--plan", required=True, help="execution-plan.md 的路径")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"FAIL: plan not found: {plan_path}", file=sys.stderr)
        return 2

    errors = check_plan(read_text(plan_path))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print("PASS: plan structure is ready for approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
