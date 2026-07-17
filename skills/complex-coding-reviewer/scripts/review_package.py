#!/usr/bin/env python3
"""从 canonical target/context 生成有界只读阅读包。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.cli import require_review_root, run_cli
from complex_coding_reviewer.io import load_json_object, write_new_json
from complex_coding_reviewer.package import build_review_package


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 bounded review package")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--generated-at")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    args = parser.parse_args()

    def handler() -> dict[str, object]:
        require_review_root(args.output, args.review_root)
        package = build_review_package(
            load_json_object(args.target, code="REVIEW_TARGET_INVALID"),
            load_json_object(args.context, code="REVIEW_CONTEXT_INVALID"),
            workspace=args.workspace,
            task_dir=args.task_dir,
            generated_at=args.generated_at,
        )
        output = write_new_json(args.output, package, review_root=args.review_root)
        return {"package": package, "output": str(output), "agent_calls": 0, "network_calls": 0}

    return run_cli("review.package", handler)


if __name__ == "__main__":
    raise SystemExit(main())

