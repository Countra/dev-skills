#!/usr/bin/env python3
"""GitLab issue 模板只读命令。"""

from __future__ import annotations

import argparse
from pathlib import PurePosixPath
from typing import Any, Iterable

from gitlab_common import (
    GitLabSkillError,
    add_common_args,
    add_pagination_args,
    make_client,
    output_result,
    quote_file_path,
    quote_id,
    request_list,
    run_cli,
)


DEFAULT_TEMPLATE_DIR = ".gitlab/issue_templates"


def normalize_template_name(name: str) -> str:
    value = name.strip().replace("\\", "/")
    if not value:
        raise GitLabSkillError("模板名称不能为空")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise GitLabSkillError("模板名称只能是单个 Markdown 文件名")
    if not value.lower().endswith(".md"):
        value = f"{value}.md"
    return value


def template_path(name: str, template_dir: str = DEFAULT_TEMPLATE_DIR) -> str:
    directory = template_dir.strip().strip("/")
    if not directory or ".." in PurePosixPath(directory).parts:
        raise GitLabSkillError("模板目录不合法")
    return f"{directory}/{normalize_template_name(name)}"


def resolve_ref(client: Any, project: str, ref: str | None) -> str:
    if ref:
        return ref
    project_info = client.request("GET", f"/projects/{project}")
    if isinstance(project_info, dict) and project_info.get("default_branch"):
        return str(project_info["default_branch"])
    raise GitLabSkillError("无法从项目详情中读取 default_branch，请显式传入 --ref")


def read_template_content(
    client: Any,
    project: str,
    name: str,
    ref: str | None = None,
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> dict[str, Any]:
    final_ref = resolve_ref(client, project, ref)
    path = template_path(name, template_dir)
    endpoint = f"/projects/{project}/repository/files/{quote_file_path(path)}/raw"
    data = client.request("GET", endpoint, params={"ref": final_ref}, raw=True)
    text = data.decode("utf-8", errors="replace")
    return {"name": normalize_template_name(name), "path": path, "ref": final_ref, "content": text}


def compact_template_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": PurePosixPath(str(entry.get("path", ""))).name,
        "path": entry.get("path"),
        "type": entry.get("type"),
        "id": entry.get("id"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab issue 模板")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 issue 模板")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    list_parser.add_argument("--project", required=True)
    list_parser.add_argument("--ref")
    list_parser.add_argument("--template-dir", default=DEFAULT_TEMPLATE_DIR)

    get_parser = subparsers.add_parser("get", help="读取项目 issue 模板内容")
    add_common_args(get_parser)
    get_parser.add_argument("--project", required=True)
    get_parser.add_argument("--name", required=True)
    get_parser.add_argument("--ref")
    get_parser.add_argument("--template-dir", default=DEFAULT_TEMPLATE_DIR)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "list":
        final_ref = resolve_ref(client, project, args.ref)
        params = {"path": args.template_dir, "ref": final_ref}
        entries = request_list(client, f"/projects/{project}/repository/tree", args, params=params)
        templates = [
            compact_template_entry(entry)
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("type") == "blob"
            and str(entry.get("path", "")).lower().endswith(".md")
        ]
        output_result({"ref": final_ref, "template_dir": args.template_dir, "templates": templates}, pretty=args.pretty)
        return 0
    if args.command == "get":
        output_result(read_template_content(client, project, args.name, args.ref, args.template_dir), pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
