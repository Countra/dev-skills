#!/usr/bin/env python3
"""导出当前 session 的 network 事件摘要。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出 network 事件。")
    add_common_args(parser)
    parser.add_argument("--session", required=True)
    parser.add_argument("--id", default="collect-network")
    parser.add_argument("--max-events", type=int, default=300)
    parser.add_argument("--url-contains")
    parser.add_argument("--failed-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = {"maxEvents": args.max_events, "includeFailedOnly": args.failed_only}
        if args.url_contains:
            payload["urlContains"] = args.url_contains
        action = {"id": args.id, "collectNetwork": payload}
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/actions/run", {"session": args.session, "action": action}, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "network_failed")


if __name__ == "__main__":
    raise SystemExit(main())
