#!/usr/bin/env python3
"""GitLab namespace 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import (
    add_common_args,
    add_pagination_args,
    make_client,
    output_client_result,
    quote_id,
    request_list,
    run_cli,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab namespace")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出或搜索 namespace")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--search")
    list_parser.add_argument("--owned-only", action="store_true")
    list_parser.add_argument("--top-level-only", action="store_true")
    list_parser.add_argument("--full-path-search", action="store_true")
    list_parser.add_argument("--root-storage-statistics", action="store_true")

    get_parser = subparsers.add_parser("get", help="读取 namespace 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--namespace", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    if args.command == "list":
        params = {
            "search": args.search,
            "owned_only": args.owned_only or None,
            "top_level_only": args.top_level_only or None,
            "full_path_search": args.full_path_search or None,
            "root_storage_statistics": args.root_storage_statistics or None,
        }
        value = request_list(client, "/namespaces", args, params=params)
        output_client_result(client, value, pretty=args.pretty, operation="namespaces.list")
        return 0
    if args.command == "get":
        value = client.request("GET", f"/namespaces/{quote_id(args.namespace)}")
        output_client_result(client, value, pretty=args.pretty, operation="namespaces.get")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
