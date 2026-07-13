#!/usr/bin/env python3
"""把 run manifest 转换为确定性 grade 文档。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.grading import grade_manifest, load_json_object, resolve_blind_swap
from skill_evaluation_lab.output import render_json


def _optional_human(path: Path | None) -> Any:
    if path is None:
        return None
    value = load_json_object(path)
    if set(value) != {"feedback"}:
        raise SuiteError("人工反馈文件必须且仅能包含 feedback", path="$")
    return value.get("feedback")


def _optional_judge(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = load_json_object(path)
    if not {"judgments", "private_mappings"}.issubset(value) or set(value) - {
        "judgments",
        "private_mappings",
        "calibration",
    }:
        raise SuiteError("judge bundle 字段无效", path="$")
    return resolve_blind_swap(
        value.get("judgments", []),
        value.get("private_mappings", {}),
        calibration=value.get("calibration"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="确定性评分 Skill Evaluation Lab run")
    parser.add_argument("--run", required=True, type=Path, help="se_run.py 生成的 run.json")
    parser.add_argument("--human-feedback", type=Path, help="可选人工反馈 JSON")
    parser.add_argument("--judge-bundle", type=Path, help="可选 blind/swap judge 结果与私有映射 JSON")
    parser.add_argument("--output", type=Path, help="可选 grade JSON 路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        grade = grade_manifest(
            load_json_object(args.run),
            human_feedback=_optional_human(args.human_feedback),
            judge_result=_optional_judge(args.judge_bundle),
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(render_json(grade, pretty=True) + "\n", encoding="utf-8")
        return grade

    return run_cli("run.grade", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
