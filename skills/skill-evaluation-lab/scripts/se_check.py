#!/usr/bin/env python3
"""生成 candidate 与可选 baseline 的只读静态证据。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.output import write_new_json
from skill_evaluation_lab.paths import resolve_input, resolve_output, resolve_workspace
from skill_evaluation_lab.static_checks import evaluate_skill


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Skill 的确定性静态证据")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace 根目录")
    parser.add_argument("--candidate", type=Path, required=True, help="candidate Skill 目录")
    parser.add_argument("--baseline", type=Path, help="可选 baseline Skill 目录")
    parser.add_argument("--evaluation-id", help="可选稳定评估标识")
    parser.add_argument("--output", type=Path, help="可选的新建 evidence JSON 路径")
    parser.add_argument("--pretty", action="store_true", help="格式化标准输出 JSON")
    args = parser.parse_args()

    def handler() -> object:
        workspace = resolve_workspace(args.workspace)
        candidate = resolve_input(workspace, args.candidate, label="candidate", expect="directory")
        baseline = (
            resolve_input(workspace, args.baseline, label="baseline", expect="directory")
            if args.baseline
            else None
        )
        evidence = evaluate_skill(
            workspace,
            candidate,
            baseline=baseline,
            evaluation_id=args.evaluation_id,
        )
        if args.output:
            sources = (candidate,) if baseline is None else (candidate, baseline)
            output = resolve_output(
                workspace,
                args.output,
                label="static evidence output",
                source_roots=sources,
            )
            write_new_json(output, evidence)
        return evidence

    return run_cli("static.check", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
