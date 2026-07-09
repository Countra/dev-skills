#!/usr/bin/env python3
"""GitLab 仓库只读访问命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_common import add_common_args, add_pagination_args, make_client, output_result, quote_file_path, quote_id, request_list, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 GitLab 仓库 tree、文件和 blob")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    tree = subparsers.add_parser("tree", help="读取 repository tree")
    add_common_args(tree)
    add_pagination_args(tree)
    tree.add_argument("--project", required=True)
    tree.add_argument("--path")
    tree.add_argument("--ref")
    tree.add_argument("--recursive", action="store_true")

    file_parser = subparsers.add_parser("file", help="读取 repository file 元数据和 base64 内容")
    add_common_args(file_parser)
    file_parser.add_argument("--project", required=True)
    file_parser.add_argument("--file-path", required=True)
    file_parser.add_argument("--ref", required=True)

    raw = subparsers.add_parser("raw", help="读取 raw file 内容")
    add_common_args(raw)
    raw.add_argument("--project", required=True)
    raw.add_argument("--file-path", required=True)
    raw.add_argument("--ref", required=True)
    raw.add_argument("--as-json", action="store_true", help="以 JSON 包装 raw 文本")

    blob = subparsers.add_parser("blob", help="读取 blob 或 raw blob")
    add_common_args(blob)
    blob.add_argument("--project", required=True)
    blob.add_argument("--sha", required=True)
    blob.add_argument("--raw", action="store_true")
    blob.add_argument("--as-json", action="store_true", help="raw 模式下以 JSON 包装文本")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = quote_id(getattr(args, "project", ""))

    if args.command == "tree":
        params = {"path": args.path, "ref": args.ref, "recursive": args.recursive or None}
        output_result(request_list(client, f"/projects/{project}/repository/tree", args, params=params), pretty=args.pretty)
        return 0
    if args.command == "file":
        file_path = quote_file_path(args.file_path)
        path = f"/projects/{project}/repository/files/{file_path}"
        output_result(client.request("GET", path, params={"ref": args.ref}), pretty=args.pretty)
        return 0
    if args.command == "raw":
        file_path = quote_file_path(args.file_path)
        path = f"/projects/{project}/repository/files/{file_path}/raw"
        data = client.request("GET", path, params={"ref": args.ref}, raw=True)
        text = data.decode("utf-8", errors="replace")
        if args.as_json:
            output_result({"content": text}, pretty=args.pretty)
        else:
            print(text, end="" if text.endswith("\n") else "\n")
        return 0
    if args.command == "blob":
        suffix = "/raw" if args.raw else ""
        data = client.request("GET", f"/projects/{project}/repository/blobs/{quote_id(args.sha)}{suffix}", raw=args.raw)
        if args.raw:
            text = data.decode("utf-8", errors="replace")
            if args.as_json:
                output_result({"content": text}, pretty=args.pretty)
            else:
                print(text, end="" if text.endswith("\n") else "\n")
        else:
            output_result(data, pretty=args.pretty)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
