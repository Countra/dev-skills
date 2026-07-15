#!/usr/bin/env python3
"""查询、等待或取消 durable verifier operation。"""

from __future__ import annotations

import argparse
import urllib.parse

from ev_common import EVError, add_common_args, fail, load_config, operation_exit_code, print_json, request_json, resolve_config_path, wait_for_operation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 verifier durable operation。")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    get_parser = subparsers.add_parser("get", help="读取当前 operation 状态")
    get_parser.add_argument("--operation-id", required=True)
    wait_parser = subparsers.add_parser("wait", help="轮询到终态；等待超时不会取消 operation")
    wait_parser.add_argument("--operation-id", required=True)
    wait_parser.add_argument("--timeout-seconds", type=float, default=300)
    wait_parser.add_argument("--poll-seconds", type=float, default=0.2)
    cancel_parser = subparsers.add_parser("cancel", help="请求取消并返回收敛后的状态")
    cancel_parser.add_argument("--operation-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.command == "get":
            query = urllib.parse.urlencode({"operationId": args.operation_id})
            result = request_json(config, "GET", f"/operations/get?{query}")
        elif args.command == "wait":
            result = wait_for_operation(
                config,
                args.operation_id,
                args.timeout_seconds,
                args.poll_seconds,
            )
        else:
            result = request_json(
                config,
                "POST",
                "/operations/cancel",
                {"operationId": args.operation_id},
            )
        print_json(result)
        return operation_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "operation_failed")


if __name__ == "__main__":
    raise SystemExit(main())
