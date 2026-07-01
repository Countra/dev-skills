#!/usr/bin/env python3
"""快捷采集当前 session 的 DOM 文本 snapshot。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="采集 session snapshot。")
    add_common_args(parser)
    parser.add_argument("--session", required=True)
    parser.add_argument("--id", default="snapshot")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/actions/run", {"session": args.session, "action": {"id": args.id, "snapshot": True}}, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "snapshot_failed")


if __name__ == "__main__":
    raise SystemExit(main())
