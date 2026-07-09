#!/usr/bin/env python3
"""GitLab issue 只读命令。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_common import (
    add_common_args,
    add_pagination_args,
    make_client,
    output_result,
    parse_csv,
    parse_int_csv,
    quote_id,
    read_optional_text_from_args,
    request_list,
    run_cli,
    validate_yyyy_mm_dd,
)
from gl_issue_templates import DEFAULT_TEMPLATE_DIR, read_template_content


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab issue")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 issue")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--state")
    list_parser.add_argument("--search")
    list_parser.add_argument("--labels")
    list_parser.add_argument("--assignee-id")

    get_parser = subparsers.add_parser("get", help="读取项目 issue 详情")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--iid", required=True)

    related = subparsers.add_parser("related-mrs", help="读取 issue 关联 MR")
    add_common_args(related)
    related.add_argument("--project", required=True)
    related.add_argument("--iid", required=True)

    closed_by = subparsers.add_parser("closed-by", help="读取关闭 issue 的 MR")
    add_common_args(closed_by)
    closed_by.add_argument("--project", required=True)
    closed_by.add_argument("--iid", required=True)

    for command, help_text in (("close", "关闭 issue，默认 dry-run"), ("reopen", "重新打开 issue，默认 dry-run")):
        state = subparsers.add_parser(command, help=help_text)
        add_common_args(state)
        state.add_argument("--project", required=True)
        state.add_argument("--iid", required=True)
        state.add_argument("--confirm", action="store_true", help="确认真实发送状态变更")

    create = subparsers.add_parser("create", help="创建 issue，默认 dry-run")
    add_common_args(create)
    create.add_argument("--project", required=True)
    create.add_argument("--title", required=True)
    description = create.add_mutually_exclusive_group()
    description.add_argument("--description")
    description.add_argument("--description-file")
    description.add_argument("--stdin", action="store_true")
    description.add_argument("--template", help="读取项目 .gitlab/issue_templates 下的模板")
    create.add_argument("--template-ref")
    create.add_argument("--template-dir", default=DEFAULT_TEMPLATE_DIR)
    create.add_argument("--labels", help="逗号分隔 label 名称")
    create.add_argument("--allow-new-labels", action="store_true", help="允许 GitLab 在创建 issue 时自动创建缺失 label")
    create.add_argument("--milestone-id", type=int)
    assignee = create.add_mutually_exclusive_group()
    assignee.add_argument("--assignee-id", type=int)
    assignee.add_argument("--assignee-ids", help="逗号分隔 assignee id")
    create.add_argument("--due-date")
    create.add_argument("--confidential", action="store_true")
    create.add_argument("--issue-type", choices=["issue", "incident", "test_case", "task"])
    create.add_argument("--confirm", action="store_true", help="确认真实发送创建请求")
    return parser


def ensure_labels_exist(client: Any, project: str, labels: list[str] | None, allow_new_labels: bool) -> list[str]:
    if not labels or allow_new_labels:
        return []
    for label in labels:
        client.request("GET", f"/projects/{project}/labels/{quote_id(label)}")
    return labels


def create_body(args: argparse.Namespace, client: Any, project: str) -> tuple[dict[str, Any], str, list[str]]:
    if args.template:
        template = read_template_content(client, project, args.template, args.template_ref, args.template_dir)
        description = template["content"]
        description_source = f"template:{template['path']}@{template['ref']}"
    else:
        description, description_source = read_optional_text_from_args(
            args,
            "description",
            "description_file",
            "stdin",
            "description",
        )
    labels = parse_csv(args.labels)
    checked_labels = ensure_labels_exist(client, project, labels, args.allow_new_labels)
    assignee_ids = parse_int_csv(args.assignee_ids, "--assignee-ids")
    if args.assignee_id is not None:
        assignee_ids = [args.assignee_id]
    body = {
        "title": args.title,
        "description": description,
        "labels": ",".join(labels) if labels else None,
        "milestone_id": args.milestone_id,
        "assignee_ids": assignee_ids,
        "due_date": validate_yyyy_mm_dd(args.due_date, "--due-date"),
        "confidential": args.confidential or None,
        "issue_type": args.issue_type,
    }
    return {key: value for key, value in body.items() if value is not None}, description_source, checked_labels


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        params = {"state": args.state, "search": args.search, "labels": args.labels, "assignee_id": args.assignee_id}
        output_result(request_list(client, f"/projects/{project}/issues", args, params=params), pretty=args.pretty)
        return 0
    if args.command == "get":
        output_result(client.request("GET", f"/projects/{project}/issues/{quote_id(args.iid)}"), pretty=args.pretty)
        return 0
    if args.command == "related-mrs":
        path = f"/projects/{project}/issues/{quote_id(args.iid)}/related_merge_requests"
        output_result(client.request("GET", path), pretty=args.pretty)
        return 0
    if args.command == "closed-by":
        path = f"/projects/{project}/issues/{quote_id(args.iid)}/closed_by"
        output_result(client.request("GET", path), pretty=args.pretty)
        return 0
    if args.command == "create":
        body, description_source, checked_labels = create_body(args, client, project)
        path = f"/projects/{project}/issues"
        if not args.confirm:
            preview = client.preview("POST", path, None, body)
            preview["description_source"] = description_source
            preview["checked_labels"] = checked_labels
            output_result(preview, pretty=args.pretty)
            return 0
        output_result(client.request("POST", path, json_body=body), pretty=args.pretty)
        return 0
    if args.command in {"close", "reopen"}:
        body = {"state_event": args.command}
        path = f"/projects/{project}/issues/{quote_id(args.iid)}"
        if not args.confirm:
            output_result(client.preview("PUT", path, None, body), pretty=args.pretty)
            return 0
        output_result(client.request("PUT", path, json_body=body), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
