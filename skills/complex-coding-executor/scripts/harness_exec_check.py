#!/usr/bin/env python3
"""执行 latest task bundle 的 preflight、状态、转移、恢复和 final 门禁。"""

from __future__ import annotations

import argparse
from typing import Any

from harness_cli import (
    add_bundle_arguments,
    emit_failure,
    emit_success,
    resolve_from_args,
)
from harness_execution import (
    check_final,
    check_preflight_status,
    check_transition_status,
    reconcile_snapshot,
    status_payload,
)


def authorization_result(
    task_id: str,
    plan_revision: int,
    attestation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "plan_revision": plan_revision,
        "authorizations": attestation["authorizations"],
    }


def run_mode(
    bundle: Any,
    mode: str,
    dependency_receipt: str | None = None,
) -> dict[str, Any]:
    if mode == "status":
        return status_payload(bundle)
    if mode == "reconcile":
        return reconcile_snapshot(bundle)
    if mode == "preflight":
        attestation, status = check_preflight_status(bundle, dependency_receipt)
        result = authorization_result(
            bundle.task_id,
            bundle.plan_revision,
            attestation,
        )
        result["state"] = status
        return result
    if mode == "transition":
        attestation, status = check_transition_status(bundle, dependency_receipt)
        result = authorization_result(
            bundle.task_id,
            bundle.plan_revision,
            attestation,
        )
        result["state"] = status
        return result
    attestation = check_final(bundle, dependency_receipt)
    result = authorization_result(
        bundle.task_id,
        bundle.plan_revision,
        attestation,
    )
    result["state"] = status_payload(bundle)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 complex coding executor lifecycle")
    add_bundle_arguments(parser)
    parser.add_argument(
        "--mode",
        choices=["preflight", "status", "transition", "reconcile", "final"],
        required=True,
    )
    parser.add_argument(
        "--dependency-receipt",
        help="task-dir 相对的 runtime dependency receipt",
    )
    args = parser.parse_args()
    action = f"executor {args.mode} check"
    try:
        bundle = resolve_from_args(args, require_attestation=True)
        result = run_mode(bundle, args.mode, args.dependency_receipt)
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
