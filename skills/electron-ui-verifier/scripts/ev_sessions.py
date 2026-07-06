#!/usr/bin/env python3
"""列出或检查 Electron verifier sessions。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="列出 verifier sessions。")
    add_common_args(parser)
    parser.add_argument("--session", help="指定 session 时返回连接状态")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.session:
            result = request_json(config, "GET", f"/sessions/status?session={args.session}")
        else:
            result = request_json(config, "GET", "/sessions")
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "sessions_failed")


if __name__ == "__main__":
    raise SystemExit(main())
