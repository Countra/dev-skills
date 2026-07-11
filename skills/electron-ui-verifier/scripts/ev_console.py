#!/usr/bin/env python3
"""导出当前 session 的 console 事件。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出 console 事件。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--id", default="collect-console")
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--level", action="append", dest="levels")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        options = {"maxEvents": args.max_events}
        if args.levels:
            options["levels"] = args.levels
        action = {"id": args.id, "type": "collectConsole", "options": options, "continueOnFailure": True}
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/actions/run", {"runId": args.run_id, "action": action}, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "console_failed")


if __name__ == "__main__":
    raise SystemExit(main())
