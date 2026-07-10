#!/usr/bin/env python3
"""GitLab merge request approval 状态只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import add_common_args, make_client, output_client_result, resource_path, run_cli


ENDPOINTS = {
    "summary": ("approvals", "merge_request_approvals.summary"),
    "state": ("approval_state", "merge_request_approvals.state"),
    "rules": ("approval_rules", "merge_request_approvals.rules"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab merge request approval 状态")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("summary", "读取 MR approval 摘要"),
        ("state", "读取 MR approval state"),
        ("rules", "读取 MR approval rules"),
    ):
        item = subparsers.add_parser(name, help=help_text)
        add_common_args(item)
        item.add_argument("--project", required=True)
        item.add_argument("--iid", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    suffix, operation = ENDPOINTS[args.command]
    path = f"{resource_path('mr', args.project, args.iid)}/{suffix}"
    value = client.request("GET", path)
    output_client_result(client, value, pretty=args.pretty, operation=operation)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
