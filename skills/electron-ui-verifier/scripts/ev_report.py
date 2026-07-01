#!/usr/bin/env python3
"""读取 verifier session 的报告。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 verifier 报告。")
    add_common_args(parser)
    parser.add_argument("--session", required=True)
    parser.add_argument("--latest", action="store_true", help="读取 session 最新报告")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.latest:
            raise EVError("currently only --latest is supported")
        config = load_config(resolve_config_path(args))
        result = request_json(config, "GET", f"/reports/latest?session={args.session}", timeout=60.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "report_failed")


if __name__ == "__main__":
    raise SystemExit(main())
