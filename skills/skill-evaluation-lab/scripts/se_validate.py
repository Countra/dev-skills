#!/usr/bin/env python3
"""验证 eval suite closed contract。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import load_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Skill Evaluation Lab suite")
    parser.add_argument("--suite", required=True, type=Path, help="suite JSON 路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        suite = load_suite(args.suite)
        return {
            "suite_id": suite.suite_id,
            "case_count": len(suite.cases),
            "trigger_cases": sum(case["mode"] == "trigger" for case in suite.cases),
            "behavior_cases": sum(case["mode"] == "behavior" for case in suite.cases),
            "valid": True,
        }

    return run_cli("suite.validate", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
