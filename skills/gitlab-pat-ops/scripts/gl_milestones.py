#!/usr/bin/env python3
"""GitLab milestone 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import add_common_args, add_pagination_args, make_client, output_client_result, quote_id, request_list, run_cli


def add_project_milestone_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--state", choices=["active", "closed"])
    parser.add_argument("--title")
    parser.add_argument("--search")
    parser.add_argument("--include-ancestors", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab 项目 milestone")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 milestone")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    add_project_milestone_args(list_parser)

    get_parser = subparsers.add_parser("get", help="读取项目 milestone 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--milestone-id", required=True)

    issues = subparsers.add_parser("issues", help="列出 milestone 关联 issue")
    add_common_args(issues)
    add_pagination_args(issues)
    issues.add_argument("--project", required=True)
    issues.add_argument("--milestone-id", required=True)

    mrs = subparsers.add_parser("mrs", help="列出 milestone 关联 MR")
    add_common_args(mrs)
    add_pagination_args(mrs)
    mrs.add_argument("--project", required=True)
    mrs.add_argument("--milestone-id", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        params = {
            "state": args.state,
            "title": args.title,
            "search": args.search,
            "include_ancestors": args.include_ancestors or None,
        }
        output_client_result(client, request_list(client, f"/projects/{project}/milestones", args, params=params), pretty=args.pretty, operation="milestones.list")
        return 0
    if args.command == "get":
        path = f"/projects/{project}/milestones/{quote_id(args.milestone_id)}"
        output_client_result(client, client.request("GET", path), pretty=args.pretty, operation="milestones.get")
        return 0
    if args.command == "issues":
        path = f"/projects/{project}/milestones/{quote_id(args.milestone_id)}/issues"
        output_client_result(client, request_list(client, path, args), pretty=args.pretty, operation="milestones.issues")
        return 0
    if args.command == "mrs":
        path = f"/projects/{project}/milestones/{quote_id(args.milestone_id)}/merge_requests"
        output_client_result(client, request_list(client, path, args), pretty=args.pretty, operation="milestones.merge_requests")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
