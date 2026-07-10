#!/usr/bin/env python3
"""GitLab label 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import add_common_args, add_pagination_args, make_client, output_client_result, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab 项目 label")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 label")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--search")
    list_parser.add_argument("--with-counts", action="store_true")
    list_parser.add_argument("--include-ancestor-groups", choices=["true", "false"])
    list_parser.add_argument("--archived", choices=["true", "false"])

    get_parser = subparsers.add_parser("get", help="读取项目 label 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--label-id", required=True, help="label ID 或名称")
    get_parser.add_argument("--include-ancestor-groups", choices=["true", "false"])
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        params = {
            "search": args.search,
            "with_counts": args.with_counts or None,
            "include_ancestor_groups": args.include_ancestor_groups,
            "archived": args.archived,
        }
        output_client_result(client, request_list(client, f"/projects/{project}/labels", args, params=params), pretty=args.pretty, operation="labels.list")
        return 0
    if args.command == "get":
        params = {"include_ancestor_groups": args.include_ancestor_groups}
        path = f"/projects/{project}/labels/{quote_id(args.label_id)}"
        output_client_result(client, client.request("GET", path, params=params), pretty=args.pretty, operation="labels.get")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
