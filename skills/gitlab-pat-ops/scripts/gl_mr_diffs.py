#!/usr/bin/env python3
"""GitLab merge request diff 只读命令。"""

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
    resource_path,
    run_cli,
)


def _add_mr(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--iid", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab merge request diff")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出 MR 当前 diff")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    _add_mr(list_parser)
    list_parser.add_argument("--unidiff", action="store_true")

    versions_parser = subparsers.add_parser("versions", help="列出 MR diff versions")
    add_common_args(versions_parser)
    add_pagination_args(versions_parser)
    _add_mr(versions_parser)

    get_parser = subparsers.add_parser("get-version", help="读取指定 MR diff version")
    add_common_args(get_parser)
    _add_mr(get_parser)
    get_parser.add_argument("--version-id", required=True)
    get_parser.add_argument("--unidiff", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    base = resource_path("mr", args.project, args.iid)
    if args.command == "list":
        value = request_list(client, f"{base}/diffs", args, params={"unidiff": args.unidiff or None})
        output_client_result(client, value, pretty=args.pretty, operation="merge_request_diffs.list")
        return 0
    if args.command == "versions":
        value = request_list(client, f"{base}/versions", args)
        output_client_result(client, value, pretty=args.pretty, operation="merge_request_diffs.versions")
        return 0
    if args.command == "get-version":
        path = f"{base}/versions/{quote_id(args.version_id)}"
        value = client.request("GET", path, params={"unidiff": args.unidiff or None})
        output_client_result(client, value, pretty=args.pretty, operation="merge_request_diffs.get_version")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
