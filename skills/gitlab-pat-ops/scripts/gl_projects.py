#!/usr/bin/env python3
"""GitLab 项目查询和受保护创建命令。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_ops import (
    GitLabSkillError,
    add_common_args,
    add_confirmation_arg,
    add_pagination_args,
    execute_guarded_write,
    make_client,
    output_client_result,
    preflight_snapshot,
    quote_id,
    request_list,
    run_cli,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询或创建 GitLab 项目")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--membership", action="store_true")
    list_parser.add_argument("--owned", action="store_true")
    list_parser.add_argument("--search")

    search_parser = subparsers.add_parser("search", help="搜索项目")
    add_common_args(search_parser)
    add_pagination_args(search_parser)
    search_parser.add_argument("query")

    get_parser = subparsers.add_parser("get", help="获取项目详情")
    add_common_args(get_parser)
    get_parser.add_argument("project")

    create_parser = subparsers.add_parser("create", help="创建项目，默认 dry-run")
    add_common_args(create_parser)
    create_parser.add_argument("--name")
    create_parser.add_argument("--path")
    create_parser.add_argument("--namespace-id", type=int)
    create_parser.add_argument("--description")
    create_parser.add_argument("--visibility", choices=["private", "internal", "public"])
    create_parser.add_argument("--initialize-with-readme", action="store_true")
    add_confirmation_arg(create_parser)
    return parser


def create_body(args: argparse.Namespace) -> dict[str, Any]:
    body = {
        "name": args.name,
        "path": args.path,
        "namespace_id": args.namespace_id,
        "description": args.description,
        "visibility": args.visibility,
        "initialize_with_readme": args.initialize_with_readme or None,
    }
    body = {key: value for key, value in body.items() if value is not None}
    if not body.get("name") and not body.get("path"):
        raise GitLabSkillError("create 需要 --name 或 --path")
    return body


def namespace_snapshot(client: Any, namespace_id: int | None) -> dict[str, Any]:
    if namespace_id is not None:
        value = client.request("GET", f"/namespaces/{quote_id(namespace_id)}")
        snapshot = preflight_snapshot(value, ("id", "full_path", "kind"))
        snapshot["source"] = "namespace"
        return snapshot
    value = client.request("GET", "/user")
    snapshot = preflight_snapshot(value, ("id", "username", "name"))
    snapshot["source"] = "current_user"
    return snapshot


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)

    if args.command == "list":
        params = {"membership": args.membership or None, "owned": args.owned or None, "search": args.search}
        output_client_result(client, request_list(client, "/projects", args, params=params), pretty=args.pretty, operation="projects.list")
        return 0
    if args.command == "search":
        output_client_result(client, request_list(client, "/projects", args, params={"search": args.query}), pretty=args.pretty, operation="projects.search")
        return 0
    if args.command == "get":
        output_client_result(client, client.request("GET", f"/projects/{quote_id(args.project)}"), pretty=args.pretty, operation="projects.get")
        return 0
    if args.command == "create":
        body = create_body(args)
        preflight = namespace_snapshot(client, args.namespace_id)
        result = execute_guarded_write(
            client,
            operation="projects.create",
            method="POST",
            path="/projects",
            params=None,
            json_body=body,
            confirm=args.confirm,
            target={"namespace_id": preflight.get("id"), "path": body.get("path") or body.get("name")},
            preflight=preflight,
            reread_preflight=lambda: namespace_snapshot(client, args.namespace_id),
        )
        output_client_result(client, result, pretty=args.pretty, operation="projects.create")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
