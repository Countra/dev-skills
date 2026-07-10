#!/usr/bin/env python3
"""GitLab issue/MR resource event 只读命令。"""

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


EVENT_SEGMENTS = {
    "state": "resource_state_events",
    "label": "resource_label_events",
    "milestone": "resource_milestone_events",
}


def _add_resource(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--resource", choices=["issue", "mr"], required=True)
    parser.add_argument("--iid", required=True)
    parser.add_argument("--event", choices=tuple(EVENT_SEGMENTS), required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab issue/MR resource events")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出 resource events")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    _add_resource(list_parser)

    get_parser = subparsers.add_parser("get", help="读取单个 resource event")
    add_common_args(get_parser)
    _add_resource(get_parser)
    get_parser.add_argument("--event-id", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    base = f"{resource_path(args.resource, args.project, args.iid)}/{EVENT_SEGMENTS[args.event]}"
    operation = f"resource_events.{args.resource}.{args.event}"
    if args.command == "list":
        value = request_list(client, base, args)
        output_client_result(client, value, pretty=args.pretty, operation=f"{operation}.list")
        return 0
    if args.command == "get":
        value = client.request("GET", f"{base}/{quote_id(args.event_id)}")
        output_client_result(client, value, pretty=args.pretty, operation=f"{operation}.get")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
