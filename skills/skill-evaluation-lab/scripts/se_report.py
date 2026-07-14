#!/usr/bin/env python3
"""合并三层证据并生成透明 JSON/Markdown 报告。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import (
    load_imported_observation,
    load_json_document,
    load_semantic_review,
    validate_static_evidence,
)
from skill_evaluation_lab.errors import LabError, PathError, ReportError
from skill_evaluation_lab.output import write_new_json, write_new_text
from skill_evaluation_lab.paths import resolve_input, resolve_output, resolve_workspace
from skill_evaluation_lab.reports import build_report, render_markdown, verify_current_sources


def main() -> int:
    parser = argparse.ArgumentParser(description="生成分层 Skill evaluation evidence report")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace 根目录")
    parser.add_argument("--static", type=Path, required=True, help="se_check.py 生成的 static evidence")
    parser.add_argument("--review", type=Path, required=True, help="当前 Agent 完成的 semantic review")
    parser.add_argument("--observation", type=Path, help="可选 imported observation evidence")
    parser.add_argument("--json-output", type=Path, help="可选的新建 report JSON")
    parser.add_argument("--markdown-output", type=Path, help="可选的新建 Markdown report")
    parser.add_argument("--pretty", action="store_true", help="格式化标准输出 JSON")
    args = parser.parse_args()

    def handler() -> object:
        workspace = resolve_workspace(args.workspace)
        static_path = resolve_input(workspace, args.static, label="static evidence", expect="file")
        review_path = resolve_input(workspace, args.review, label="semantic review", expect="file")
        observation_path = (
            resolve_input(workspace, args.observation, label="imported observation", expect="file")
            if args.observation
            else None
        )
        static = validate_static_evidence(load_json_document(static_path))
        source_roots = verify_current_sources(workspace, static)
        review = load_semantic_review(review_path)
        observation = load_imported_observation(observation_path) if observation_path else None
        report = build_report(static, review, observation)
        json_output = (
            resolve_output(
                workspace,
                args.json_output,
                label="report JSON output",
                source_roots=source_roots,
            )
            if args.json_output
            else None
        )
        markdown_output = (
            resolve_output(
                workspace,
                args.markdown_output,
                label="report Markdown output",
                source_roots=source_roots,
            )
            if args.markdown_output
            else None
        )
        if json_output is not None and json_output == markdown_output:
            raise PathError(
                "JSON 与 Markdown 输出不能使用同一路径",
                code="PATH_OUTPUT_CONFLICT",
                path=str(json_output),
            )
        created: list[Path] = []
        try:
            if json_output is not None:
                write_new_json(json_output, report)
                created.append(json_output)
            if markdown_output is not None:
                write_new_text(markdown_output, render_markdown(report))
                created.append(markdown_output)
        except (OSError, LabError) as exc:
            cleanup_failures: list[str] = []
            for path in reversed(created):
                try:
                    path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    cleanup_failures.append(f"{path}: {cleanup_error}")
            if cleanup_failures:
                raise ReportError(
                    "报告写入失败且部分输出无法回滚",
                    code="REPORT_ROLLBACK_FAILED",
                    guidance="; ".join(cleanup_failures),
                    outcome="partial",
                ) from exc
            raise
        return report

    return run_cli("evidence.report", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
