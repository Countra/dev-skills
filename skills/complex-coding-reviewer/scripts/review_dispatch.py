#!/usr/bin/env python3
"""准备、封存并校验 Reviewer 子 Agent 派发制品。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.assemble import assemble_receipt
from complex_coding_reviewer.cli import require_review_root, run_cli
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.dispatch import prepare_dispatch, validate_preparation
from complex_coding_reviewer.dispatch_lifecycle import finalize_dispatch, validate_dispatch
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.io import (
    load_json_object,
    resolve_review_artifact,
    resolve_review_ref,
    write_new_json,
)


def _roots(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-dir", type=Path)


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 Reviewer dispatch 制品")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="冻结输入并生成 allowlist prompt")
    prepare.add_argument("--review-id", required=True)
    prepare.add_argument("--target", type=Path, required=True)
    prepare.add_argument("--context", type=Path, required=True)
    prepare.add_argument("--package", type=Path)
    prepare.add_argument("--policy", choices=("strict", "conditional", "disabled"), required=True)
    prepare.add_argument(
        "--capability-status",
        choices=("available", "unavailable", "policy-disabled"),
        required=True,
    )
    prepare.add_argument("--tool-family", required=True)
    prepare.add_argument("--available-tool", action="append", default=[])
    prepare.add_argument("--attempt", type=int, default=1)
    prepare.add_argument("--max-attempts", type=int, default=2)
    prepare.add_argument("--timeout-seconds", type=int)
    prepare.add_argument("--prepared-at")
    prepare.add_argument("--semantic-result-ref")
    prepare.add_argument("--previous-dispatch", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    _roots(prepare)

    finalize = commands.add_parser("finalize", help="封存宿主记录的 Agent 生命周期")
    finalize.add_argument("--preparation", type=Path, required=True)
    finalize.add_argument("--outcome", type=Path, required=True)
    finalize.add_argument("--finalized-at")
    finalize.add_argument("--output", type=Path, required=True)
    _roots(finalize)

    validate = commands.add_parser("validate", help="校验 final dispatch")
    validate.add_argument("--dispatch", type=Path, required=True)
    validate.add_argument(
        "--expected-dispatch-policy",
        choices=("strict", "conditional", "disabled"),
    )
    validate.add_argument("--require-receipt-ready", action="store_true")
    _roots(validate)

    complete = commands.add_parser(
        "complete",
        help="一次封存 dispatch、组装并校验 canonical receipt",
    )
    complete.add_argument("--preparation", type=Path, required=True)
    complete.add_argument("--outcome", type=Path, required=True)
    complete.add_argument("--dispatch-output", type=Path, required=True)
    complete.add_argument("--output", type=Path, required=True)
    complete.add_argument("--supersedes", type=Path)
    complete.add_argument("--finalized-at")
    complete.add_argument(
        "--expected-dispatch-policy",
        choices=("strict", "conditional", "disabled"),
        required=True,
    )
    _roots(complete)
    args = parser.parse_args()

    def handler() -> dict[str, object]:
        if args.command == "prepare":
            require_review_root(args.output, args.review_root)
            value = prepare_dispatch(
                review_id=args.review_id,
                target_path=args.target,
                context_path=args.context,
                package_path=args.package,
                review_root=args.review_root,
                policy=args.policy,
                capability_status=args.capability_status,
                tool_family=args.tool_family,
                available_tools=args.available_tool,
                workspace=args.workspace,
                task_dir=args.task_dir,
                attempt=args.attempt,
                max_attempts=args.max_attempts,
                timeout_seconds=args.timeout_seconds,
                prepared_at=args.prepared_at,
                semantic_result_ref=args.semantic_result_ref,
                previous_dispatch_path=args.previous_dispatch,
            )
            output = write_new_json(args.output, value, review_root=args.review_root)
            return {
                "dispatch_id": value["dispatch_id"],
                "decision": value["decision"],
                "prompt_digest": value["prompt_digest"],
                "output": str(output),
                "agent_calls": 0,
                "network_calls": 0,
            }
        if args.command == "finalize":
            require_review_root(args.output, args.review_root)
            preparation_path = resolve_review_artifact(args.preparation, args.review_root)
            outcome_path = resolve_review_artifact(args.outcome, args.review_root)
            value = finalize_dispatch(
                load_json_object(preparation_path),
                load_json_object(outcome_path),
                preparation_path=preparation_path,
                review_root=args.review_root,
                workspace=args.workspace,
                task_dir=args.task_dir,
                finalized_at=args.finalized_at,
            )
            output = write_new_json(args.output, value, review_root=args.review_root)
            return {
                "dispatch_id": value["dispatch_id"],
                "lifecycle_status": value["lifecycle"]["status"],
                "receipt_ready": value["lifecycle"]["status"] in {"completed", "fallback"},
                "output": str(output),
                "agent_calls": 0,
                "network_calls": 0,
            }
        if args.command == "complete":
            require_review_root(args.dispatch_output, args.review_root)
            require_review_root(args.output, args.review_root)
            preparation_path = resolve_review_artifact(
                args.preparation,
                args.review_root,
            )
            outcome_path = resolve_review_artifact(args.outcome, args.review_root)
            preparation = load_json_object(preparation_path)
            dispatch = finalize_dispatch(
                preparation,
                load_json_object(outcome_path),
                preparation_path=preparation_path,
                review_root=args.review_root,
                workspace=args.workspace,
                task_dir=args.task_dir,
                finalized_at=args.finalized_at,
            )
            dispatch_path = write_new_json(
                args.dispatch_output,
                dispatch,
                review_root=args.review_root,
            )
            inputs = preparation["inputs"]
            target_path = resolve_review_ref(inputs["target_ref"], args.review_root)
            context_path = resolve_review_ref(inputs["context_ref"], args.review_root)
            result_path = resolve_review_ref(
                inputs["semantic_result_ref"],
                args.review_root,
            )
            receipt = assemble_receipt(
                target_path=target_path,
                context_path=context_path,
                dispatch_path=dispatch_path,
                semantic_result_path=result_path,
                review_root=args.review_root,
                workspace=args.workspace,
                task_dir=args.task_dir,
            )
            previous = None
            if args.supersedes is not None:
                previous = load_json_object(
                    resolve_review_artifact(args.supersedes, args.review_root)
                )
            summary = validate_receipt(
                receipt,
                review_root=args.review_root,
                workspace=args.workspace,
                task_dir=args.task_dir,
                expected_dispatch_policy=args.expected_dispatch_policy,
                previous_receipt=previous,
            )
            receipt_path = write_new_json(
                args.output,
                receipt,
                review_root=args.review_root,
            )
            return {
                "dispatch_id": dispatch["dispatch_id"],
                "review_id": receipt["review_id"],
                "verdict": receipt["verdict"],
                "gate_ready": True,
                "dispatch_output": str(dispatch_path),
                "output": str(receipt_path),
                "reviewer_mode": summary["reviewer_mode"],
                "independence_claim": summary["independence_claim"],
                "agent_calls": 0,
                "network_calls": 0,
            }
        dispatch_path = resolve_review_artifact(args.dispatch, args.review_root)
        if args.require_receipt_ready and args.expected_dispatch_policy is None:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "receipt-ready dispatch 校验必须显式传入 --expected-dispatch-policy。",
            )
        summary = validate_dispatch(
            load_json_object(dispatch_path),
            review_root=args.review_root,
            workspace=args.workspace,
            task_dir=args.task_dir,
            expected_policy=args.expected_dispatch_policy,
            require_receipt_ready=args.require_receipt_ready,
        )
        return {
            **summary,
            "dispatch": str(dispatch_path),
            "agent_calls": 0,
            "network_calls": 0,
        }

    return run_cli(f"review.dispatch.{args.command}", handler)


if __name__ == "__main__":
    raise SystemExit(main())
