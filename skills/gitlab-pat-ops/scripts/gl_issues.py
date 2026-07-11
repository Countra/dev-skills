#!/usr/bin/env python3
"""GitLab issue 查询与受保护 metadata 写入命令。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_ops import (
    GitLabSkillError,
    add_common_args,
    add_confirmation_arg,
    add_description_update_args,
    add_due_date_update_args,
    add_id_list_update_args,
    add_label_update_args,
    add_milestone_update_args,
    add_pagination_args,
    description_update,
    due_date_update,
    execute_guarded_write,
    id_list_update,
    label_update,
    make_client,
    milestone_update,
    output_client_result,
    parse_bool,
    parse_csv,
    parse_int_csv,
    project_path,
    project_snapshot,
    quote_id,
    read_optional_text_from_args,
    request_list,
    require_nonempty_update,
    resource_path,
    resource_snapshot,
    run_cli,
    read_template_content,
    template_snapshot,
    validate_iso8601,
    validate_yyyy_mm_dd,
)


ISSUE_TYPES = ("issue", "incident", "test_case", "task")


def _add_issue(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--iid", required=True)


def _add_list_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", choices=["opened", "closed", "all"])
    parser.add_argument("--scope", choices=["created_by_me", "assigned_to_me", "all"])
    parser.add_argument("--search")
    parser.add_argument("--in", dest="search_in", choices=["title", "description"])
    parser.add_argument("--labels")
    parser.add_argument("--not-labels")
    parser.add_argument("--assignee-id")
    parser.add_argument("--assignee-username")
    parser.add_argument("--author-id", type=int)
    parser.add_argument("--author-username")
    parser.add_argument("--milestone")
    parser.add_argument("--iids", help="逗号分隔 issue IID")
    parser.add_argument("--issue-type", choices=ISSUE_TYPES)
    parser.add_argument("--confidential", help="true 或 false")
    parser.add_argument("--due-date")
    parser.add_argument("--created-after")
    parser.add_argument("--created-before")
    parser.add_argument("--updated-after")
    parser.add_argument("--updated-before")
    parser.add_argument("--order-by")
    parser.add_argument("--sort", choices=["asc", "desc"])
    parser.add_argument("--with-label-details", action="store_true")


def _add_update_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title")
    add_description_update_args(parser)
    add_label_update_args(parser)
    add_milestone_update_args(parser)
    add_id_list_update_args(
        parser,
        option="--assignee-ids",
        unassign_option="--unassign",
        help_noun="assignee",
    )
    add_due_date_update_args(parser)
    parser.add_argument("--confidential", help="true 或 false")
    parser.add_argument("--issue-type", choices=ISSUE_TYPES)
    parser.add_argument("--discussion-locked", help="true 或 false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询或受保护写入 GitLab issue")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 issue")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    _add_list_filters(list_parser)

    get_parser = subparsers.add_parser("get", help="读取 issue 详情")
    add_common_args(get_parser)
    _add_issue(get_parser)

    for command, help_text in (
        ("related-mrs", "读取 issue 关联 MR"),
        ("closed-by", "读取关闭 issue 的 MR"),
    ):
        item = subparsers.add_parser(command, help=help_text)
        add_common_args(item)
        _add_issue(item)

    create = subparsers.add_parser("create", help="创建 issue，默认 dry-run")
    add_common_args(create)
    create.add_argument("--project", required=True)
    create.add_argument("--title", required=True)
    description = create.add_mutually_exclusive_group()
    description.add_argument("--description")
    description.add_argument("--description-file")
    description.add_argument("--stdin", dest="description_stdin", action="store_true")
    description.add_argument("--template", help="Project Templates API 中的 issue 模板名称")
    create.add_argument("--source-template-project-id", type=int)
    create.add_argument("--labels", help="逗号分隔 label 名称")
    create.add_argument("--allow-new-labels", action="store_true")
    create.add_argument("--milestone-id", type=int)
    assignee = create.add_mutually_exclusive_group()
    assignee.add_argument("--assignee-id", type=int)
    assignee.add_argument("--assignee-ids", help="逗号分隔 assignee id")
    create.add_argument("--due-date")
    create.add_argument("--confidential", action="store_true")
    create.add_argument("--issue-type", choices=ISSUE_TYPES)
    add_confirmation_arg(create)

    update = subparsers.add_parser("update", help="更新 issue metadata，默认 dry-run")
    add_common_args(update)
    _add_issue(update)
    _add_update_args(update)
    add_confirmation_arg(update)

    for command, help_text in (("close", "关闭 issue，默认 dry-run"), ("reopen", "重新打开 issue，默认 dry-run")):
        state = subparsers.add_parser(command, help=help_text)
        add_common_args(state)
        _add_issue(state)
        add_confirmation_arg(state)
    return parser


def ensure_labels_exist(client: Any, project: str, labels: list[str] | None, allow_new_labels: bool) -> list[str]:
    if not labels or allow_new_labels:
        return []
    for label in labels:
        client.request("GET", f"{project_path(project)}/labels/{quote_id(label)}")
    return labels


def _read_create_description(
    args: argparse.Namespace,
    client: Any,
) -> tuple[str | None, str, dict[str, Any] | None]:
    if args.source_template_project_id is not None and not args.template:
        raise GitLabSkillError("--source-template-project-id 只能与 --template 一起使用")
    if args.template:
        value = read_template_content(
            client,
            args.project,
            "issues",
            args.template,
            args.source_template_project_id,
        )
        snapshot = template_snapshot(value, "issues", args.template, args.source_template_project_id)
        return value["content"], f"template:issues/{args.template}", snapshot
    description, source = read_optional_text_from_args(
        args,
        "description",
        "description_file",
        "description_stdin",
        "description",
    )
    return description, source, None


def create_body(
    args: argparse.Namespace,
    client: Any,
) -> tuple[dict[str, Any], str, list[str], dict[str, Any] | None]:
    if not args.title.strip():
        raise GitLabSkillError("issue title 不能为空")
    if args.milestone_id is not None and args.milestone_id <= 0:
        raise GitLabSkillError("--milestone-id 必须大于 0")
    if args.assignee_id is not None and args.assignee_id <= 0:
        raise GitLabSkillError("--assignee-id 必须大于 0")
    description, source, template = _read_create_description(args, client)
    labels = parse_csv(args.labels)
    checked_labels = ensure_labels_exist(client, args.project, labels, args.allow_new_labels)
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
    return {key: value for key, value in body.items() if value is not None}, source, checked_labels, template


def create_preflight(client: Any, args: argparse.Namespace) -> dict[str, Any]:
    labels = parse_csv(args.labels)
    template = None
    if args.template:
        value = read_template_content(
            client,
            args.project,
            "issues",
            args.template,
            args.source_template_project_id,
        )
        template = template_snapshot(value, "issues", args.template, args.source_template_project_id)
    return {
        "project": project_snapshot(client, args.project),
        "checked_labels": ensure_labels_exist(client, args.project, labels, args.allow_new_labels),
        "template": template,
    }


def list_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "state": args.state,
        "scope": args.scope,
        "search": args.search,
        "in": args.search_in,
        "labels": args.labels,
        "not[labels]": args.not_labels,
        "assignee_id": args.assignee_id,
        "assignee_username": args.assignee_username,
        "author_id": args.author_id,
        "author_username": args.author_username,
        "milestone": args.milestone,
        "iids[]": parse_int_csv(args.iids, "--iids"),
        "issue_type": args.issue_type,
        "confidential": parse_bool(args.confidential, "--confidential"),
        "due_date": args.due_date,
        "created_after": validate_iso8601(args.created_after, "--created-after"),
        "created_before": validate_iso8601(args.created_before, "--created-before"),
        "updated_after": validate_iso8601(args.updated_after, "--updated-after"),
        "updated_before": validate_iso8601(args.updated_before, "--updated-before"),
        "order_by": args.order_by,
        "sort": args.sort,
        "with_labels_details": args.with_label_details or None,
    }


def update_body(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    body: dict[str, Any] = {}
    if args.title is not None:
        if not args.title.strip():
            raise GitLabSkillError("issue title 不能为空")
        body["title"] = args.title
    description, source = description_update(args)
    body.update(description)
    body.update(label_update(args))
    body.update(milestone_update(args))
    body.update(
        id_list_update(
            args,
            value_attr="assignee_ids",
            unassign_attr="unassign",
            body_key="assignee_ids",
            label="--assignee-ids",
        )
    )
    body.update(due_date_update(args))
    confidential = parse_bool(args.confidential, "--confidential")
    discussion_locked = parse_bool(args.discussion_locked, "--discussion-locked")
    if confidential is not None:
        body["confidential"] = confidential
    if discussion_locked is not None:
        body["discussion_locked"] = discussion_locked
    if args.issue_type is not None:
        body["issue_type"] = args.issue_type
    return require_nonempty_update(body, "issue update"), source


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    base = project_path(args.project)
    if args.command == "list":
        value = request_list(client, f"{base}/issues", args, params=list_params(args))
        output_client_result(client, value, pretty=args.pretty, operation="issues.list")
        return 0
    if args.command == "create":
        body, source, checked_labels, template = create_body(args, client)
        preflight = {
            "project": project_snapshot(client, args.project),
            "checked_labels": checked_labels,
            "template": template,
        }
        result = execute_guarded_write(
            client,
            operation="issues.create",
            method="POST",
            path=f"{base}/issues",
            params=None,
            json_body=body,
            confirm=args.confirm,
            target={"project": args.project, "title": args.title},
            preflight=preflight,
            reread_preflight=lambda: create_preflight(client, args),
        )
        result["description_source"] = source
        result["checked_labels"] = checked_labels
        output_client_result(client, result, pretty=args.pretty, operation="issues.create")
        return 0
    issue = resource_path("issue", args.project, args.iid)
    if args.command == "get":
        output_client_result(client, client.request("GET", issue), pretty=args.pretty, operation="issues.get")
        return 0
    if args.command in {"related-mrs", "closed-by"}:
        suffix = "related_merge_requests" if args.command == "related-mrs" else "closed_by"
        operation = "issues.related_merge_requests" if args.command == "related-mrs" else "issues.closed_by"
        output_client_result(client, client.request("GET", f"{issue}/{suffix}"), pretty=args.pretty, operation=operation)
        return 0
    preflight = resource_snapshot(client, "issue", args.project, args.iid)
    if args.command in {"close", "reopen"}:
        operation = f"issues.{args.command}"
        body = {"state_event": args.command}
    elif args.command == "update":
        operation = "issues.update"
        body, source = update_body(args)
    else:
        parser.error("unknown command")
        return 2
    result = execute_guarded_write(
        client,
        operation=operation,
        method="PUT",
        path=issue,
        params=None,
        json_body=body,
        confirm=args.confirm,
        target={"project": args.project, "iid": str(args.iid)},
        preflight=preflight,
        reread_preflight=lambda: resource_snapshot(client, "issue", args.project, args.iid),
    )
    if args.command == "update":
        result["description_source"] = source
    output_client_result(client, result, pretty=args.pretty, operation=operation)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
