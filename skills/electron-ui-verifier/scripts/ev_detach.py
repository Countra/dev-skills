#!/usr/bin/env python3
"""断开 Electron verifier session。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="断开 verifier session。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="session 名称或 sessionId")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/sessions/detach", {"session": args.session})
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "detach_failed")


if __name__ == "__main__":
    raise SystemExit(main())
