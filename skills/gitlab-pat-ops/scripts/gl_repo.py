#!/usr/bin/env python3
"""GitLab repository tree、file 与二进制安全内容读取命令。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from gitlab_ops import (
    GitLabSkillError,
    add_common_args,
    add_pagination_args,
    make_client,
    output_client_result,
    project_path,
    quote_file_path,
    quote_id,
    request_list,
    run_cli,
)


def _add_raw_output_args(parser: argparse.ArgumentParser) -> None:
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--output", help="将原始 bytes 原子写入本地文件")
    output.add_argument("--text", action="store_true", help="严格按 UTF-8 解码后放入 JSON envelope")
    parser.add_argument("--overwrite", action="store_true", help="允许替换已存在的 --output 文件")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 GitLab repository tree、file 和 blob")
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

    raw = subparsers.add_parser("raw", help="读取 raw file bytes")
    add_common_args(raw)
    raw.add_argument("--project", required=True)
    raw.add_argument("--file-path", required=True)
    raw.add_argument("--ref", required=True)
    _add_raw_output_args(raw)

    blob = subparsers.add_parser("blob", help="读取 blob JSON 或 raw bytes")
    add_common_args(blob)
    blob.add_argument("--project", required=True)
    blob.add_argument("--sha", required=True)
    blob.add_argument("--raw", action="store_true")
    _add_raw_output_args(blob)
    return parser


def _atomic_output(data: bytes, path_value: str, overwrite: bool) -> Path:
    target = Path(path_value).expanduser().resolve()
    if not target.parent.is_dir():
        raise GitLabSkillError(f"输出目录不存在: {target.parent}")
    if target.exists() and not overwrite:
        raise GitLabSkillError("输出文件已存在；如需替换请显式传入 --overwrite")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
            temporary.unlink()
        return target
    except FileExistsError as exc:
        raise GitLabSkillError("输出文件在写入期间已出现，未覆盖该文件") from exc
    except OSError as exc:
        raise GitLabSkillError(f"无法写入输出文件: {target}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def raw_result(data: bytes, args: argparse.Namespace) -> dict[str, Any]:
    if args.overwrite and not args.output:
        raise GitLabSkillError("--overwrite 只能与 --output 一起使用")
    digest = hashlib.sha256(data).hexdigest()
    value: dict[str, Any] = {"bytes": len(data), "sha256": digest}
    if args.output:
        value.update({"encoding": "file", "output": str(_atomic_output(data, args.output, args.overwrite))})
        return value
    if args.text:
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitLabSkillError("内容不是有效 UTF-8；请省略 --text 使用 base64，或使用 --output") from exc
        value.update({"encoding": "utf-8", "content": content})
        return value
    value.update({"encoding": "base64", "content": base64.b64encode(data).decode("ascii")})
    return value


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = make_client(args)
    project = project_path(args.project)
    if args.command == "tree":
        params = {"path": args.path, "ref": args.ref, "recursive": args.recursive or None}
        value = request_list(client, f"{project}/repository/tree", args, params=params)
        output_client_result(client, value, pretty=args.pretty, operation="repository.tree")
        return 0
    if args.command == "file":
        path = f"{project}/repository/files/{quote_file_path(args.file_path)}"
        value = client.request("GET", path, params={"ref": args.ref})
        output_client_result(client, value, pretty=args.pretty, operation="repository.file")
        return 0
    if args.command == "raw":
        path = f"{project}/repository/files/{quote_file_path(args.file_path)}/raw"
        data = client.request("GET", path, params={"ref": args.ref}, raw=True)
        output_client_result(client, raw_result(data, args), pretty=args.pretty, operation="repository.raw")
        return 0
    if args.command == "blob":
        suffix = "/raw" if args.raw else ""
        value = client.request("GET", f"{project}/repository/blobs/{quote_id(args.sha)}{suffix}", raw=args.raw)
        if args.raw:
            value = raw_result(value, args)
        elif args.output or args.text or args.overwrite:
            raise GitLabSkillError("--output/--text/--overwrite 只适用于 blob --raw")
        output_client_result(client, value, pretty=args.pretty, operation="repository.blob.raw" if args.raw else "repository.blob")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
