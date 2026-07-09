#!/usr/bin/env python3
"""GitLab issue/MR notes 查询和受保护回复。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_common import add_body_args, add_common_args, add_pagination_args, make_client, output_result, quote_id, read_body_from_args, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询或回复 GitLab notes")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("issue-list", "列出 issue notes"), ("mr-list", "列出 MR notes")):
        sub = subparsers.add_parser(name, help=help_text)
        add_common_args(sub)
        add_pagination_args(sub)
        sub.add_argument("--project", required=True)
        sub.add_argument("--iid", required=True)
        sub.add_argument("--only-comments", action="store_true")
        sub.add_argument("--compact", action="store_true", help="输出适合评论解析的简化字段")

    for name, help_text in (("issue-reply", "回复 issue note"), ("mr-reply", "回复 MR note")):
        sub = subparsers.add_parser(name, help=help_text)
        add_common_args(sub)
        sub.add_argument("--project", required=True)
        sub.add_argument("--iid", required=True)
        add_body_args(sub)
        sub.add_argument("--internal", action="store_true")
        sub.add_argument("--confirm", action="store_true", help="确认真实发送回复")
    return parser


def note_path(kind: str, project: str, iid: str) -> str:
    resource = "issues" if kind == "issue" else "merge_requests"
    return f"/projects/{quote_id(project)}/{resource}/{quote_id(iid)}/notes"


def compact_notes(notes: Any) -> Any:
    if not isinstance(notes, list):
        return notes
    result = []
    for note in notes:
        author = note.get("author") if isinstance(note, dict) else {}
        result.append(
            {
                "id": note.get("id"),
                "type": note.get("type"),
                "system": note.get("system"),
                "internal": note.get("internal", note.get("confidential")),
                "created_at": note.get("created_at"),
                "author": author.get("username") if isinstance(author, dict) else None,
                "body": note.get("body"),
            }
        )
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)

    if args.command in {"issue-list", "mr-list"}:
        kind = "issue" if args.command.startswith("issue") else "mr"
        params = {"activity_filter": "only_comments" if args.only_comments else None}
        notes = request_list(client, note_path(kind, args.project, args.iid), args, params=params)
        output_result(compact_notes(notes) if args.compact else notes, pretty=args.pretty)
        return 0
    if args.command in {"issue-reply", "mr-reply"}:
        kind = "issue" if args.command.startswith("issue") else "mr"
        body, source = read_body_from_args(args)
        payload = {"body": body, "internal": args.internal or None}
        payload = {key: value for key, value in payload.items() if value is not None}
        path = note_path(kind, args.project, args.iid)
        if not args.confirm:
            preview = client.preview("POST", path, None, payload)
            preview["body_source"] = source
            output_result(preview, pretty=args.pretty)
            return 0
        output_result(client.request("POST", path, json_body=payload), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
