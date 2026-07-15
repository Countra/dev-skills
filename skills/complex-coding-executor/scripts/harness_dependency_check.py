#!/usr/bin/env python3
"""展示并校验 dependency preflight 或单阶段执行 receipt。"""

from __future__ import annotations

import argparse

from harness_attestation import validate_attestation
from harness_cli import add_bundle_arguments, emit_failure, emit_success, resolve_from_args
from harness_dependency_evaluation import (
    evaluate_dependency_preflight,
    evaluate_dependency_stage,
)
from harness_dependency_gate import DependencyGateError


def main() -> int:
    parser = argparse.ArgumentParser(description="校验批准依赖的执行期事实")
    add_bundle_arguments(parser)
    parser.add_argument("--mode", choices=("preflight", "stage"), required=True)
    parser.add_argument("--stage-id", help="stage mode 的 STG-* ID")
    parser.add_argument(
        "--runtime-receipt",
        help="task-dir 相对的只读 runtime dependency receipt",
    )
    args = parser.parse_args()
    action = f"dependency {args.mode} check"
    try:
        bundle = resolve_from_args(args, require_attestation=True)
        validate_attestation(bundle)
        if args.mode == "preflight":
            result = evaluate_dependency_preflight(bundle, args.runtime_receipt)
        else:
            if not args.stage_id:
                raise DependencyGateError(
                    "EXEC_DEPENDENCY_STAGE_INVALID",
                    "stage mode 必须提供 --stage-id。",
                )
            result = evaluate_dependency_stage(
                bundle,
                args.stage_id,
                args.runtime_receipt,
            )
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
