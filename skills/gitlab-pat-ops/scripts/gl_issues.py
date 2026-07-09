#!/usr/bin/env python3
"""GitLab issue 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_common import add_common_args, add_pagination_args, make_client, output_result, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab issue")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 issue")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--state")
    list_parser.add_argument("--search")
    list_parser.add_argument("--labels")
    list_parser.add_argument("--assignee-id")

    get_parser = subparsers.add_parser("get", help="读取项目 issue 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--iid", required=True)

    related = subparsers.add_parser("related-mrs", help="读取 issue 关联 MR")
    add_common_args(related)
    related.add_argument("--project", required=True)
    related.add_argument("--iid", required=True)

    closed_by = subparsers.add_parser("closed-by", help="读取关闭 issue 的 MR")
    add_common_args(closed_by)
    closed_by.add_argument("--project", required=True)
    closed_by.add_argument("--iid", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        params = {"state": args.state, "search": args.search, "labels": args.labels, "assignee_id": args.assignee_id}
        output_result(request_list(client, f"/projects/{project}/issues", args, params=params), pretty=args.pretty)
        return 0
    if args.command == "get":
        output_result(client.request("GET", f"/projects/{project}/issues/{quote_id(args.iid)}"), pretty=args.pretty)
        return 0
    if args.command == "related-mrs":
        path = f"/projects/{project}/issues/{quote_id(args.iid)}/related_merge_requests"
        output_result(client.request("GET", path), pretty=args.pretty)
        return 0
    if args.command == "closed-by":
        path = f"/projects/{project}/issues/{quote_id(args.iid)}/closed_by"
        output_result(client.request("GET", path), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
