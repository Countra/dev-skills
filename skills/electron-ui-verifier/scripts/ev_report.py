#!/usr/bin/env python3
"""读取 verifier session 的报告。"""

from __future__ import annotations

import argparse
import urllib.parse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 verifier 报告。")
    add_common_args(parser)
    parser.add_argument("--session")
    parser.add_argument("--run-id", help="读取 run journal 状态")
    parser.add_argument("--latest", action="store_true", help="读取 session 最新报告")
    parser.add_argument("--path", help="读取 stateRoot 下的指定 report 绝对路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.run_id:
            query = urllib.parse.urlencode({"runId": args.run_id})
            result = request_json(config, "GET", f"/runs/status?{query}", timeout=60.0)
        elif args.latest:
            if not args.session:
                raise EVError("--latest requires --session")
            query = urllib.parse.urlencode({"session": args.session})
            result = request_json(config, "GET", f"/reports/latest?{query}", timeout=60.0)
        elif args.path:
            query = urllib.parse.urlencode({"path": args.path})
            result = request_json(config, "GET", f"/reports/get?{query}", timeout=60.0)
        else:
            raise EVError("use --run-id <id>, --latest --session <name>, or --path <report>")
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "report_failed")


if __name__ == "__main__":
    raise SystemExit(main())
