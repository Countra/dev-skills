#!/usr/bin/env python3
"""从 attested ledger replay 当前任务状态。"""

from __future__ import annotations

import argparse

from harness_cli import (
    add_bundle_arguments,
    emit_failure,
    emit_success,
    resolve_from_args,
)
from harness_execution import status_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 ledger replay 与 snapshot drift")
    add_bundle_arguments(parser)
    args = parser.parse_args()
    action = "ledger summary generated"
    try:
        bundle = resolve_from_args(args, require_attestation=True)
        result = status_payload(bundle)
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
