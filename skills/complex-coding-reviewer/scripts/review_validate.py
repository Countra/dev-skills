#!/usr/bin/env python3
"""校验 canonical receipt、profile 语义与 target freshness。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.cli import run_cli
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.io import load_json_object, resolve_review_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 review receipt")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-dir", type=Path)
    parser.add_argument("--expected-profile", choices=("plan-review", "code-review"))
    parser.add_argument(
        "--expected-scope",
        choices=("managed-plan", "stage-delta", "final-integration", "standalone"),
    )
    parser.add_argument("--expected-stage-id")
    parser.add_argument("--expected-attempt", type=int)
    parser.add_argument(
        "--expected-dispatch-policy",
        choices=("strict", "conditional", "disabled"),
    )
    parser.add_argument("--supersedes", type=Path)
    args = parser.parse_args()

    def handler() -> dict[str, object]:
        receipt_path = resolve_review_artifact(args.receipt, args.review_root)
        if args.expected_dispatch_policy is None:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "正式 receipt 校验必须显式传入 --expected-dispatch-policy。",
            )
        receipt = load_json_object(receipt_path)
        previous = None
        if args.supersedes:
            previous = load_json_object(resolve_review_artifact(args.supersedes, args.review_root))
        result = validate_receipt(
            receipt,
            review_root=args.review_root,
            workspace=args.workspace,
            task_dir=args.task_dir,
            expected_profile=args.expected_profile,
            expected_scope=args.expected_scope,
            expected_stage_id=args.expected_stage_id,
            expected_attempt=args.expected_attempt,
            expected_dispatch_policy=args.expected_dispatch_policy,
            previous_receipt=previous,
        )
        return {**result, "receipt": str(receipt_path), "agent_calls": 0, "network_calls": 0}

    return run_cli("review.validate", handler)


if __name__ == "__main__":
    raise SystemExit(main())
