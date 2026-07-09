#!/usr/bin/env python3
"""GitLab 项目成员只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_common import add_common_args, add_pagination_args, make_client, output_result, parse_csv, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab 项目成员")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目成员")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--include-inherited", action="store_true", help="包含继承和邀请成员")
    list_parser.add_argument("--query")
    list_parser.add_argument("--user-ids", help="逗号分隔 user id")
    list_parser.add_argument("--state", choices=["awaiting", "active"])

    get_parser = subparsers.add_parser("get", help="读取项目成员详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--user-id", required=True)
    get_parser.add_argument("--include-inherited", action="store_true", help="包含继承和邀请成员")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))
    suffix = "/all" if getattr(args, "include_inherited", False) else ""

    if args.command == "list":
        params = {"query": args.query, "user_ids": parse_csv(args.user_ids), "state": args.state}
        output_result(request_list(client, f"/projects/{project}/members{suffix}", args, params=params), pretty=args.pretty)
        return 0
    if args.command == "get":
        path = f"/projects/{project}/members{suffix}/{quote_id(args.user_id)}"
        output_result(client.request("GET", path), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
