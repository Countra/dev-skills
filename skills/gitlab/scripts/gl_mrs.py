#!/usr/bin/env python3
"""GitLab merge request 查询和受保护创建。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_common import add_common_args, add_pagination_args, make_client, output_result, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询或创建 GitLab merge request")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 MR")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--state")
    list_parser.add_argument("--search")
    list_parser.add_argument("--source-branch")
    list_parser.add_argument("--target-branch")

    get_parser = subparsers.add_parser("get", help="读取 MR 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--iid", required=True)

    notes = subparsers.add_parser("notes", help="读取 MR notes")
    add_common_args(notes)
    add_pagination_args(notes)
    notes.add_argument("--project", required=True)
    notes.add_argument("--iid", required=True)

    create = subparsers.add_parser("create", help="创建 MR，默认 dry-run")
    add_common_args(create)
    create.add_argument("--project", required=True)
    create.add_argument("--source-branch", required=True)
    create.add_argument("--target-branch", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--description")
    create.add_argument("--description-file")
    create.add_argument("--remove-source-branch", action="store_true")
    create.add_argument("--squash", action="store_true")
    create.add_argument("--reviewer-ids", help="逗号分隔 reviewer id")
    create.add_argument("--confirm", action="store_true")
    return parser


def create_body(args: argparse.Namespace) -> dict[str, Any]:
    if args.description and args.description_file:
        raise ValueError("--description 和 --description-file 只能使用一个")
    description = args.description
    if args.description_file:
        with open(args.description_file, "r", encoding="utf-8") as handle:
            description = handle.read()
    reviewer_ids = None
    if args.reviewer_ids:
        reviewer_ids = [int(item.strip()) for item in args.reviewer_ids.split(",") if item.strip()]
    body = {
        "source_branch": args.source_branch,
        "target_branch": args.target_branch,
        "title": args.title,
        "description": description,
        "remove_source_branch": args.remove_source_branch or None,
        "squash": args.squash or None,
        "reviewer_ids": reviewer_ids,
    }
    return {key: value for key, value in body.items() if value is not None}


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        params = {
            "state": args.state,
            "search": args.search,
            "source_branch": args.source_branch,
            "target_branch": args.target_branch,
        }
        output_result(request_list(client, f"/projects/{project}/merge_requests", args, params=params), pretty=args.pretty)
        return 0
    if args.command == "get":
        output_result(client.request("GET", f"/projects/{project}/merge_requests/{quote_id(args.iid)}"), pretty=args.pretty)
        return 0
    if args.command == "notes":
        path = f"/projects/{project}/merge_requests/{quote_id(args.iid)}/notes"
        output_result(request_list(client, path, args), pretty=args.pretty)
        return 0
    if args.command == "create":
        body = create_body(args)
        path = f"/projects/{project}/merge_requests"
        if not args.confirm:
            output_result(client.preview("POST", path, None, body), pretty=args.pretty)
            return 0
        output_result(client.request("POST", path, json_body=body), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
