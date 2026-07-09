#!/usr/bin/env python3
"""GitLab branch 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_common import add_common_args, add_pagination_args, make_client, output_result, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab 项目 branch")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 branch")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    group = list_parser.add_mutually_exclusive_group()
    group.add_argument("--search")
    group.add_argument("--regex")

    get_parser = subparsers.add_parser("get", help="读取项目 branch 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--branch", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        params = {"search": args.search, "regex": args.regex}
        output_result(request_list(client, f"/projects/{project}/repository/branches", args, params=params), pretty=args.pretty)
        return 0
    if args.command == "get":
        path = f"/projects/{project}/repository/branches/{quote_id(args.branch)}"
        output_result(client.request("GET", path), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
