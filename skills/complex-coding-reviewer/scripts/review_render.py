#!/usr/bin/env python3
"""把已验证 receipt 渲染为 findings-first Markdown。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.cli import require_review_root, run_cli
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.io import load_json_object, resolve_review_artifact, write_new_text
from complex_coding_reviewer.render import render_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 review receipt")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--supersedes", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    args = parser.parse_args()

    def handler() -> dict[str, object]:
        require_review_root(args.output, args.review_root)
        receipt = load_json_object(resolve_review_artifact(args.receipt, args.review_root))
        previous = None
        if args.supersedes:
            previous = load_json_object(resolve_review_artifact(args.supersedes, args.review_root))
        summary = validate_receipt(
            receipt,
            workspace=args.workspace,
            task_dir=args.task_dir,
            previous_receipt=previous,
        )
        output = write_new_text(
            args.output,
            render_receipt(receipt),
            review_root=args.review_root,
        )
        return {**summary, "output": str(output), "agent_calls": 0, "network_calls": 0}

    return run_cli("review.render", handler)


if __name__ == "__main__":
    raise SystemExit(main())
