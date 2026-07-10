#!/usr/bin/env python3
"""GitLab repository commit 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import (
    add_common_args,
    add_pagination_args,
    make_client,
    output_client_result,
    project_path,
    quote_id,
    request_list,
    run_cli,
    validate_iso8601,
)


def _add_project_and_commit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--sha", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab repository commit")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出 commit")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--ref-name")
    list_parser.add_argument("--since")
    list_parser.add_argument("--until")
    list_parser.add_argument("--path")
    list_parser.add_argument("--author")
    list_parser.add_argument("--all-refs", action="store_true")
    list_parser.add_argument("--with-stats", action="store_true")
    list_parser.add_argument("--first-parent", action="store_true")
    list_parser.add_argument("--order", choices=["default", "topo"])
    list_parser.add_argument("--trailers", action="store_true")

    get_parser = subparsers.add_parser("get", help="读取 commit 详情")
    add_common_args(get_parser)
    _add_project_and_commit(get_parser)
    get_parser.add_argument("--stats", action="store_true")

    refs_parser = subparsers.add_parser("refs", help="读取包含 commit 的 branch/tag")
    add_common_args(refs_parser)
    add_pagination_args(refs_parser)
    _add_project_and_commit(refs_parser)
    refs_parser.add_argument("--type", choices=["branch", "tag", "all"], default="all")

    mrs_parser = subparsers.add_parser("merge-requests", help="读取包含 commit 的 MR")
    add_common_args(mrs_parser)
    add_pagination_args(mrs_parser)
    _add_project_and_commit(mrs_parser)

    diff_parser = subparsers.add_parser("diff", help="读取 commit diff")
    add_common_args(diff_parser)
    add_pagination_args(diff_parser)
    _add_project_and_commit(diff_parser)
    diff_parser.add_argument("--unidiff", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    base = f"{project_path(args.project)}/repository/commits"
    if args.command == "list":
        params = {
            "ref_name": args.ref_name,
            "since": validate_iso8601(args.since, "--since"),
            "until": validate_iso8601(args.until, "--until"),
            "path": args.path,
            "author": args.author,
            "all": args.all_refs or None,
            "with_stats": args.with_stats or None,
            "first_parent": args.first_parent or None,
            "order": args.order,
            "trailers": args.trailers or None,
        }
        value = request_list(client, base, args, params=params)
        output_client_result(client, value, pretty=args.pretty, operation="commits.list")
        return 0
    commit = f"{base}/{quote_id(args.sha)}"
    if args.command == "get":
        value = client.request("GET", commit, params={"stats": args.stats or None})
        output_client_result(client, value, pretty=args.pretty, operation="commits.get")
        return 0
    if args.command == "refs":
        value = request_list(client, f"{commit}/refs", args, params={"type": args.type})
        output_client_result(client, value, pretty=args.pretty, operation="commits.refs")
        return 0
    if args.command == "merge-requests":
        value = request_list(client, f"{commit}/merge_requests", args)
        output_client_result(client, value, pretty=args.pretty, operation="commits.merge_requests")
        return 0
    if args.command == "diff":
        value = request_list(client, f"{commit}/diff", args, params={"unidiff": args.unidiff or None})
        output_client_result(client, value, pretty=args.pretty, operation="commits.diff")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
