#!/usr/bin/env python3
"""从 grade 文档生成 JSON 与 Markdown 报告。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.grading import load_json_object
from skill_evaluation_lab.output import render_json
from skill_evaluation_lab.reports import build_report, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Skill Evaluation Lab 报告")
    parser.add_argument("--grade", required=True, type=Path, help="se_grade.py 生成的 grade JSON")
    parser.add_argument("--json-output", type=Path, help="可选 report JSON 路径")
    parser.add_argument("--markdown-output", type=Path, help="可选 Markdown 报告路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        report = build_report(load_json_object(args.grade))
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(render_json(report, pretty=True) + "\n", encoding="utf-8")
        if args.markdown_output:
            args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
        return report

    return run_cli("grade.report", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
