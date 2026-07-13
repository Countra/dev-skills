#!/usr/bin/env python3
"""展开实验矩阵、预算和 fingerprint，不调用模型。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.budgets import build_experiment_plan
from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.output import render_json


def main() -> int:
    parser = argparse.ArgumentParser(description="预览 Skill Evaluation Lab 实验矩阵")
    parser.add_argument("--suite", required=True, type=Path, help="suite JSON 路径")
    parser.add_argument("--output", type=Path, help="可选 preview JSON 路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        plan = build_experiment_plan(load_suite(args.suite))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(render_json(plan, pretty=True) + "\n", encoding="utf-8")
        return plan

    return run_cli("suite.plan", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
