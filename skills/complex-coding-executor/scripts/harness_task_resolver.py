#!/usr/bin/env python3
"""解析并展示当前最新 task bundle。"""

from __future__ import annotations

import argparse

from harness_cli import (
    add_bundle_arguments,
    emit_failure,
    emit_success,
    resolve_from_args,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="解析 pointer-only managed task")
    add_bundle_arguments(parser)
    parser.add_argument(
        "--require-attestation",
        action="store_true",
        help="同时要求批准证明存在",
    )
    args = parser.parse_args()
    action = "task bundle resolved"
    try:
        bundle = resolve_from_args(
            args,
            require_attestation=args.require_attestation,
        )
        result = {
            "task_id": bundle.task_id,
            "plan_revision": bundle.plan_revision,
            "task_dir": str(bundle.task_dir),
            "plan_path": str(bundle.plan_path),
            "contract_path": str(bundle.contract_path),
            "attestation_path": str(bundle.attestation_path),
            "run_state_path": str(bundle.run_state_path),
            "ledger_path": str(bundle.ledger_path),
            "resolved_from_active_pointer": bundle.pointer is not None,
        }
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
