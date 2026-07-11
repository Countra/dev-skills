#!/usr/bin/env python3
"""GitLab 搜索命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import add_common_args, add_pagination_args, make_client, output_client_result, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="调用 GitLab Search API")
    add_common_args(parser)
    add_pagination_args(parser)
    parser.add_argument("--project", help="限定项目 ID 或 URL-encoded path")
    parser.add_argument("--scope", required=True, help="搜索范围，例如 projects/issues/merge_requests")
    parser.add_argument("--query", required=True, help="搜索关键词")
    parser.add_argument("--state", help="状态过滤，例如 opened/closed")
    parser.add_argument("--confidential", choices=["true", "false"], help="是否搜索 confidential 项")
    parser.add_argument("--search-type", dest="search_type", help="GitLab search_type 参数")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    path = "/search"
    if args.project:
        path = f"/projects/{quote_id(args.project)}/search"
    params = {
        "scope": args.scope,
        "search": args.query,
        "state": args.state,
        "confidential": args.confidential,
        "search_type": args.search_type,
    }
    output_client_result(client, request_list(client, path, args, params=params), pretty=args.pretty, operation="search.query")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
