#!/usr/bin/env python3
"""导出当前 session 的页面异常事件。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出页面异常事件。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--id", default="collect-exceptions")
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--fail-on-exception", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        options = {"maxEvents": args.max_events, "failOnException": args.fail_on_exception}
        action = {"id": args.id, "type": "collectExceptions", "options": options, "continueOnFailure": not args.fail_on_exception}
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/actions/run", {"runId": args.run_id, "action": action}, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "exceptions_failed")


if __name__ == "__main__":
    raise SystemExit(main())
