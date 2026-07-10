#!/usr/bin/env python3
"""GitLab issue/MR discussion 查询与受保护协作命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import (
    add_body_args,
    add_common_args,
    add_confirmation_arg,
    add_pagination_args,
    discussion_snapshot,
    execute_guarded_write,
    make_client,
    output_client_result,
    quote_id,
    read_body_from_args,
    request_list,
    resource_path,
    run_cli,
)


def _add_resource(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--resource", choices=["issue", "mr"], required=True)
    parser.add_argument("--iid", required=True)


def _add_discussion(parser: argparse.ArgumentParser, *, include_resource: bool = True) -> None:
    parser.add_argument("--project", required=True)
    if include_resource:
        parser.add_argument("--resource", choices=["issue", "mr"], required=True)
    parser.add_argument("--iid", required=True)
    parser.add_argument("--discussion-id", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询或回复 GitLab issue/MR discussion")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出 discussions")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    _add_resource(list_parser)

    get_parser = subparsers.add_parser("get", help="读取 discussion 详情")
    add_common_args(get_parser)
    _add_discussion(get_parser)

    reply_parser = subparsers.add_parser("reply", help="回复 discussion，默认 dry-run")
    add_common_args(reply_parser)
    _add_discussion(reply_parser)
    add_body_args(reply_parser)
    add_confirmation_arg(reply_parser)

    for command, help_text in (
        ("resolve", "解决 MR discussion，默认 dry-run"),
        ("reopen", "重新打开 MR discussion，默认 dry-run"),
    ):
        item = subparsers.add_parser(command, help=help_text)
        add_common_args(item)
        _add_discussion(item, include_resource=False)
        add_confirmation_arg(item)
    return parser


def _discussion_path(resource: str, project: str, iid: str, discussion_id: str | None = None) -> str:
    base = f"{resource_path(resource, project, iid)}/discussions"
    return f"{base}/{quote_id(discussion_id)}" if discussion_id is not None else base


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    resource = getattr(args, "resource", "mr")
    base = _discussion_path(resource, args.project, args.iid)
    if args.command == "list":
        value = request_list(client, base, args)
        output_client_result(client, value, pretty=args.pretty, operation=f"discussions.{resource}.list")
        return 0
    path = _discussion_path(resource, args.project, args.iid, args.discussion_id)
    if args.command == "get":
        value = client.request("GET", path)
        output_client_result(client, value, pretty=args.pretty, operation=f"discussions.{resource}.get")
        return 0
    preflight = discussion_snapshot(client, resource, args.project, args.iid, args.discussion_id)
    if args.command == "reply":
        body, source = read_body_from_args(args)
        result = execute_guarded_write(
            client,
            operation=f"discussions.{resource}.reply",
            method="POST",
            path=f"{path}/notes",
            params=None,
            json_body={"body": body},
            confirm=args.confirm,
            target={
                "project": args.project,
                "resource": resource,
                "iid": str(args.iid),
                "discussion_id": args.discussion_id,
            },
            preflight=preflight,
            reread_preflight=lambda: discussion_snapshot(
                client, resource, args.project, args.iid, args.discussion_id
            ),
        )
        result["body_source"] = source
        output_client_result(client, result, pretty=args.pretty, operation=f"discussions.{resource}.reply")
        return 0
    if args.command in {"resolve", "reopen"}:
        resolved = args.command == "resolve"
        result = execute_guarded_write(
            client,
            operation=f"discussions.mr.{args.command}",
            method="PUT",
            path=path,
            params=None,
            json_body={"resolved": resolved},
            confirm=args.confirm,
            target={"project": args.project, "resource": "mr", "iid": str(args.iid), "discussion_id": args.discussion_id},
            preflight=preflight,
            reread_preflight=lambda: discussion_snapshot(
                client, "mr", args.project, args.iid, args.discussion_id
            ),
        )
        output_client_result(client, result, pretty=args.pretty, operation=f"discussions.mr.{args.command}")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
