#!/usr/bin/env python3
"""校验人工 observation suite 的闭合协议与资源路径。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.output import write_new_json
from skill_evaluation_lab.packets import suite_receipt, validate_suite_resources
from skill_evaluation_lab.paths import resolve_input, resolve_output, resolve_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="校验用户驱动的 Skill observation suite")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace 根目录")
    parser.add_argument("--suite", type=Path, required=True, help="observation suite JSON")
    parser.add_argument("--output", type=Path, help="可选的新建 validation receipt JSON")
    parser.add_argument("--pretty", action="store_true", help="格式化标准输出 JSON")
    args = parser.parse_args()

    def handler() -> object:
        workspace = resolve_workspace(args.workspace)
        suite_path = resolve_input(workspace, args.suite, label="suite", expect="file")
        suite = load_suite(suite_path)
        resources = validate_suite_resources(workspace, suite)
        receipt = suite_receipt(workspace, suite)
        if args.output:
            source_roots = (resources["candidate"],)
            if resources["baseline"] is not None:
                source_roots += (resources["baseline"],)
            output = resolve_output(
                workspace,
                args.output,
                label="suite validation output",
                source_roots=source_roots,
            )
            write_new_json(output, receipt)
        return receipt

    return run_cli("suite.validate", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
