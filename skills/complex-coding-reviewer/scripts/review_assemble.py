#!/usr/bin/env python3
"""把 supporting artifacts 组装为 canonical review receipt。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.assemble import assemble_receipt
from complex_coding_reviewer.cli import require_review_root, run_cli
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.io import (
    load_json_object,
    resolve_review_artifact,
    write_new_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="组装 canonical review receipt")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--dispatch", type=Path, required=True)
    parser.add_argument("--semantic-result", type=Path, required=True)
    parser.add_argument("--supersedes", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--expected-dispatch-policy",
        choices=("strict", "conditional", "disabled"),
    )
    parser.add_argument("--allow-non-gating-candidate", action="store_true")
    args = parser.parse_args()

    def handler() -> dict[str, object]:
        require_review_root(args.output, args.review_root)
        if (
            not args.allow_non_gating_candidate
            and args.expected_dispatch_policy is None
        ):
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "建立 gating receipt 必须显式传入 --expected-dispatch-policy。",
            )
        receipt = assemble_receipt(
            target_path=args.target,
            context_path=args.context,
            dispatch_path=args.dispatch,
            semantic_result_path=args.semantic_result,
            review_root=args.review_root,
            workspace=args.workspace,
            task_dir=args.task_dir,
        )
        previous = None
        if args.supersedes is not None:
            previous = load_json_object(
                resolve_review_artifact(args.supersedes, args.review_root)
            )
        summary = None
        if not args.allow_non_gating_candidate:
            summary = validate_receipt(
                receipt,
                review_root=args.review_root,
                workspace=args.workspace,
                task_dir=args.task_dir,
                expected_dispatch_policy=args.expected_dispatch_policy,
                previous_receipt=previous,
            )
        output = write_new_json(args.output, receipt, review_root=args.review_root)
        return {
            "review_id": receipt["review_id"],
            "verdict": receipt["verdict"],
            "gate_ready": summary is not None,
            "output": str(output),
            "agent_calls": 0,
            "network_calls": 0,
        }

    return run_cli("review.assemble", handler)


if __name__ == "__main__":
    raise SystemExit(main())
