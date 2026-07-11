#!/usr/bin/env python3
"""追加一个合法 ledger event，并刷新 run-state snapshot。"""

from __future__ import annotations

import argparse

from harness_cli import (
    add_bundle_arguments,
    emit_failure,
    emit_success,
    parse_json_object,
    resolve_from_args,
)
from harness_event_writer import append_event_and_update
from harness_state_schema import EVENT_TYPES


def main() -> int:
    parser = argparse.ArgumentParser(description="追加并 replay executor ledger event")
    add_bundle_arguments(parser)
    parser.add_argument("--event", required=True, choices=sorted(EVENT_TYPES))
    parser.add_argument("--stage-id")
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--payload-json", help="event payload JSON object")
    parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="task-dir 内相对证据路径，可重复",
    )
    parser.add_argument("--occurred-at", help="可选 RFC3339 时间")
    args = parser.parse_args()
    action = f"ledger event appended: {args.event}"
    try:
        bundle = resolve_from_args(args, require_attestation=True)
        payload = parse_json_object(args.payload_json, "--payload-json")
        result = append_event_and_update(
            bundle,
            args.event,
            stage_id=args.stage_id,
            attempt=args.attempt,
            payload=payload,
            evidence_refs=args.evidence_ref,
            occurred_at=args.occurred_at,
        )
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
