#!/usr/bin/env python3
"""GitLab merge request 查询与受保护 metadata 写入命令。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_ops import (
    GitLabSkillError,
    add_common_args,
    add_confirmation_arg,
    add_description_update_args,
    add_id_list_update_args,
    add_label_update_args,
    add_milestone_update_args,
    add_pagination_args,
    description_update,
    execute_guarded_write,
    id_list_update,
    label_update,
    make_client,
    milestone_update,
    output_client_result,
    parse_bool,
    parse_csv,
    parse_int_csv,
    preflight_snapshot,
    project_path,
    project_snapshot,
    quote_id,
    read_optional_text_from_args,
    request_list,
    require_nonempty_update,
    resource_path,
    resource_snapshot,
    read_template_content,
    run_cli,
    template_snapshot,
    validate_iso8601,
)


def _add_mr(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--iid", required=True)


def _add_list_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", choices=["opened", "closed", "locked", "merged", "all"])
    parser.add_argument("--scope", choices=["created_by_me", "assigned_to_me", "all"])
    parser.add_argument("--search")
    parser.add_argument("--in", dest="search_in", choices=["title", "description"])
    parser.add_argument("--source-branch")
    parser.add_argument("--target-branch")
    parser.add_argument("--author-id", type=int)
    parser.add_argument("--author-username")
    parser.add_argument("--assignee-id")
    parser.add_argument("--assignee-username")
    parser.add_argument("--reviewer-id")
    parser.add_argument("--reviewer-username")
    parser.add_argument("--labels")
    parser.add_argument("--not-labels")
    parser.add_argument("--milestone")
    parser.add_argument("--wip", help="true 或 false")
    parser.add_argument("--approved-by-ids", help="逗号分隔 user id")
    parser.add_argument("--created-after")
    parser.add_argument("--created-before")
    parser.add_argument("--updated-after")
    parser.add_argument("--updated-before")
    parser.add_argument("--order-by")
    parser.add_argument("--sort", choices=["asc", "desc"])
    parser.add_argument("--with-label-details", action="store_true")


def _add_update_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title")
    parser.add_argument("--target-branch")
    add_description_update_args(parser)
    add_label_update_args(parser)
    add_milestone_update_args(parser)
    add_id_list_update_args(
        parser,
        option="--assignee-ids",
        unassign_option="--unassign",
        help_noun="assignee",
    )
    add_id_list_update_args(
        parser,
        option="--reviewer-ids",
        unassign_option="--unassign-reviewers",
        help_noun="reviewer",
    )
    parser.add_argument("--remove-source-branch", help="true 或 false")
    parser.add_argument("--squash", help="true 或 false")
    parser.add_argument("--allow-collaboration", help="true 或 false")
    parser.add_argument("--discussion-locked", help="true 或 false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询或受保护写入 GitLab merge request")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 MR")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    _add_list_filters(list_parser)

    get_parser = subparsers.add_parser("get", help="读取 MR 详情")
    add_common_args(get_parser)
    _add_mr(get_parser)
    get_parser.add_argument("--include-rebase-in-progress", action="store_true")
    get_parser.add_argument("--render-html", action="store_true")

    create = subparsers.add_parser("create", help="创建 MR，默认 dry-run")
    add_common_args(create)
    create.add_argument("--project", required=True)
    create.add_argument("--source-branch", required=True)
    create.add_argument("--target-branch", required=True)
    create.add_argument("--title", required=True)
    description = create.add_mutually_exclusive_group()
    description.add_argument("--description")
    description.add_argument("--description-file")
    description.add_argument("--stdin", dest="description_stdin", action="store_true")
    description.add_argument("--template", help="Project Templates API 中的 MR 模板名称")
    create.add_argument("--source-template-project-id", type=int)
    create.add_argument("--remove-source-branch", action="store_true")
    create.add_argument("--squash", action="store_true")
    create.add_argument("--allow-collaboration", action="store_true")
    create.add_argument("--reviewer-ids", help="逗号分隔 reviewer id")
    create.add_argument("--assignee-ids", help="逗号分隔 assignee id")
    create.add_argument("--labels")
    create.add_argument("--milestone-id", type=int)
    add_confirmation_arg(create)

    update = subparsers.add_parser("update", help="更新 MR metadata，默认 dry-run")
    add_common_args(update)
    _add_mr(update)
    _add_update_args(update)
    add_confirmation_arg(update)

    for command, help_text in (("close", "关闭 MR，默认 dry-run"), ("reopen", "重新打开 MR，默认 dry-run")):
        state = subparsers.add_parser(command, help=help_text)
        add_common_args(state)
        _add_mr(state)
        add_confirmation_arg(state)
    return parser


def project_and_branch_snapshot(client: Any, project: str, source: str, target: str) -> dict[str, Any]:
    source_value = client.request("GET", f"{project_path(project)}/repository/branches/{quote_id(source)}")
    target_value = client.request("GET", f"{project_path(project)}/repository/branches/{quote_id(target)}")
    return {
        "project": project_snapshot(client, project),
        "source": preflight_snapshot(source_value, ("name", "merged", "protected", "default")),
        "target": preflight_snapshot(target_value, ("name", "merged", "protected", "default")),
    }


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
            "merge_requests",
            args.template,
            args.source_template_project_id,
        )
        snapshot = template_snapshot(value, "merge_requests", args.template, args.source_template_project_id)
        return value["content"], f"template:merge_requests/{args.template}", snapshot
    description, source = read_optional_text_from_args(
        args,
        "description",
        "description_file",
        "description_stdin",
        "description",
    )
    return description, source, None


def create_body(args: argparse.Namespace, client: Any) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    if not args.title.strip():
        raise GitLabSkillError("MR title 不能为空")
    if not args.source_branch.strip() or not args.target_branch.strip():
        raise GitLabSkillError("source/target branch 不能为空")
    if args.milestone_id is not None and args.milestone_id <= 0:
        raise GitLabSkillError("--milestone-id 必须大于 0")
    description, source, template = _read_create_description(args, client)
    labels = parse_csv(args.labels)
    body = {
        "source_branch": args.source_branch,
        "target_branch": args.target_branch,
        "title": args.title,
        "description": description,
        "remove_source_branch": args.remove_source_branch or None,
        "squash": args.squash or None,
        "allow_collaboration": args.allow_collaboration or None,
        "reviewer_ids": parse_int_csv(args.reviewer_ids, "--reviewer-ids"),
        "assignee_ids": parse_int_csv(args.assignee_ids, "--assignee-ids"),
        "labels": ",".join(labels) if labels else None,
        "milestone_id": args.milestone_id,
    }
    return {key: value for key, value in body.items() if value is not None}, source, template


def create_preflight(client: Any, args: argparse.Namespace) -> dict[str, Any]:
    value = project_and_branch_snapshot(client, args.project, args.source_branch, args.target_branch)
    template = None
    if args.template:
        template_value = read_template_content(
            client,
            args.project,
            "merge_requests",
            args.template,
            args.source_template_project_id,
        )
        template = template_snapshot(
            template_value,
            "merge_requests",
            args.template,
            args.source_template_project_id,
        )
    value["template"] = template
    return value


def list_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "state": args.state,
        "scope": args.scope,
        "search": args.search,
        "in": args.search_in,
        "source_branch": args.source_branch,
        "target_branch": args.target_branch,
        "author_id": args.author_id,
        "author_username": args.author_username,
        "assignee_id": args.assignee_id,
        "assignee_username": args.assignee_username,
        "reviewer_id": args.reviewer_id,
        "reviewer_username": args.reviewer_username,
        "labels": args.labels,
        "not[labels]": args.not_labels,
        "milestone": args.milestone,
        "wip": parse_bool(args.wip, "--wip"),
        "approved_by_ids[]": parse_int_csv(args.approved_by_ids, "--approved-by-ids"),
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
            raise GitLabSkillError("MR title 不能为空")
        body["title"] = args.title
    if args.target_branch is not None:
        if not args.target_branch.strip():
            raise GitLabSkillError("target branch 不能为空")
        body["target_branch"] = args.target_branch
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
    body.update(
        id_list_update(
            args,
            value_attr="reviewer_ids",
            unassign_attr="unassign_reviewers",
            body_key="reviewer_ids",
            label="--reviewer-ids",
        )
    )
    for attr, key in (
        ("remove_source_branch", "remove_source_branch"),
        ("squash", "squash"),
        ("allow_collaboration", "allow_collaboration"),
        ("discussion_locked", "discussion_locked"),
    ):
        value = parse_bool(getattr(args, attr), f"--{attr.replace('_', '-')}")
        if value is not None:
            body[key] = value
    return require_nonempty_update(body, "MR update"), source


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    base = project_path(args.project)
    if args.command == "list":
        value = request_list(client, f"{base}/merge_requests", args, params=list_params(args))
        output_client_result(client, value, pretty=args.pretty, operation="merge_requests.list")
        return 0
    if args.command == "create":
        body, source, template = create_body(args, client)
        preflight = project_and_branch_snapshot(client, args.project, args.source_branch, args.target_branch)
        preflight["template"] = template
        result = execute_guarded_write(
            client,
            operation="merge_requests.create",
            method="POST",
            path=f"{base}/merge_requests",
            params=None,
            json_body=body,
            confirm=args.confirm,
            target={
                "project": args.project,
                "source_branch": args.source_branch,
                "target_branch": args.target_branch,
            },
            preflight=preflight,
            reread_preflight=lambda: create_preflight(client, args),
        )
        result["description_source"] = source
        output_client_result(client, result, pretty=args.pretty, operation="merge_requests.create")
        return 0
    mr = resource_path("mr", args.project, args.iid)
    if args.command == "get":
        params = {
            "include_rebase_in_progress": args.include_rebase_in_progress or None,
            "render_html": args.render_html or None,
        }
        value = client.request("GET", mr, params=params)
        output_client_result(client, value, pretty=args.pretty, operation="merge_requests.get")
        return 0
    preflight = resource_snapshot(client, "mr", args.project, args.iid)
    if args.command in {"close", "reopen"}:
        operation = f"merge_requests.{args.command}"
        body = {"state_event": args.command}
    elif args.command == "update":
        operation = "merge_requests.update"
        body, source = update_body(args)
    else:
        parser.error("unknown command")
        return 2
    result = execute_guarded_write(
        client,
        operation=operation,
        method="PUT",
        path=mr,
        params=None,
        json_body=body,
        confirm=args.confirm,
        target={"project": args.project, "iid": str(args.iid)},
        preflight=preflight,
        reread_preflight=lambda: resource_snapshot(client, "mr", args.project, args.iid),
    )
    if args.command == "update":
        result["description_source"] = source
    output_client_result(client, result, pretty=args.pretty, operation=operation)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
