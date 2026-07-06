#!/usr/bin/env python3
"""快捷采集当前 session 截图。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="采集 session screenshot。")
    add_common_args(parser)
    parser.add_argument("--session", required=True)
    parser.add_argument("--name", default="screenshot.png")
    parser.add_argument("--id", default="screenshot")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        action = {"id": args.id, "screenshot": args.name}
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/actions/run", {"session": args.session, "action": action}, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "screenshot_failed")


if __name__ == "__main__":
    raise SystemExit(main())
