#!/usr/bin/env python3
"""使用 exact fingerprint 批准或拒绝 pending bundle。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="sealed pending decision。")
    add_common_args(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--fingerprint", required=True)
    approve.add_argument("--note", required=True)
    reject = commands.add_parser("reject")
    reject.add_argument("--run-id", required=True)
    reject.add_argument("--fingerprint", required=True)
    reject.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.command == "approve":
            path = "/pending/approve"
            payload = {"runId": args.run_id, "fingerprint": args.fingerprint, "note": args.note}
        else:
            path = "/pending/reject"
            payload = {"runId": args.run_id, "fingerprint": args.fingerprint, "reason": args.reason}
        result = request_json(config, "POST", path, payload, timeout=60.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "persist_failed")


if __name__ == "__main__":
    raise SystemExit(main())
