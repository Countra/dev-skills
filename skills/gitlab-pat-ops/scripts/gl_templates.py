#!/usr/bin/env python3
"""GitLab Project Templates 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import (
    TEMPLATE_TYPES,
    add_common_args,
    add_pagination_args,
    make_client,
    output_client_result,
    project_path,
    read_template_content,
    request_list,
    run_cli,
    template_params,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab issue/MR Project Templates")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目模板")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--type", choices=TEMPLATE_TYPES, required=True)
    list_parser.add_argument("--source-template-project-id", type=int)

    get_parser = subparsers.add_parser("get", help="读取项目模板内容")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--type", choices=TEMPLATE_TYPES, required=True)
    get_parser.add_argument("--name", required=True)
    get_parser.add_argument("--source-template-project-id", type=int)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    if args.command == "list":
        path = f"{project_path(args.project)}/templates/{args.type}"
        value = request_list(client, path, args, params=template_params(args.source_template_project_id))
        output_client_result(client, value, pretty=args.pretty, operation="templates.list")
        return 0
    if args.command == "get":
        value = read_template_content(
            client,
            args.project,
            args.type,
            args.name,
            args.source_template_project_id,
        )
        output_client_result(client, value, pretty=args.pretty, operation="templates.get")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
