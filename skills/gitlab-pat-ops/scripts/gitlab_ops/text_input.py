"""命令正文、列表和日期参数解析。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .errors import GitLabSkillError, ResponseLimitError


MAX_TEXT_BYTES = 1024 * 1024


def _read_text_file(value: str) -> str:
    path = Path(value)
    if not path.is_file():
        raise GitLabSkillError(f"文本文件不存在: {path}")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ResponseLimitError("文本文件超过 1 MiB")
    return path.read_text(encoding="utf-8")


def _read_stdin() -> str:
    value = sys.stdin.read(MAX_TEXT_BYTES + 1)
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ResponseLimitError("标准输入超过 1 MiB")
    return value


def parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_csv(value: str | None, label: str) -> list[int] | None:
    items = parse_csv(value)
    if items is None:
        return None
    try:
        parsed = [int(item) for item in items]
    except ValueError as exc:
        raise GitLabSkillError(f"{label} 必须是逗号分隔的整数") from exc
    if any(item <= 0 for item in parsed):
        raise GitLabSkillError(f"{label} 中的 id 必须大于 0")
    return parsed


def validate_yyyy_mm_dd(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise GitLabSkillError(f"{label} 必须使用 YYYY-MM-DD 格式") from exc
    return value


def validate_iso8601(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitLabSkillError(f"{label} 必须使用 ISO 8601 日期时间") from exc
    return value


def parse_bool(value: str | None, label: str) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise GitLabSkillError(f"{label} 必须是 true 或 false")


def require_nonempty_update(body: dict[str, object], label: str) -> dict[str, object]:
    if not body:
        raise GitLabSkillError(f"{label} 至少需要一个更新字段")
    return body


def read_body_from_args(args: argparse.Namespace) -> tuple[str, str]:
    body_file = getattr(args, "body_file", None)
    body = getattr(args, "body", None)
    use_stdin = getattr(args, "stdin", False)
    provided = [bool(body_file), body is not None, bool(use_stdin)]
    if sum(1 for item in provided if item) != 1:
        raise GitLabSkillError("必须且只能使用 --body-file、--body 或 --stdin 之一提供正文")
    if body_file:
        return _read_text_file(body_file), "body-file"
    if body is not None:
        return body, "body-argument"
    return _read_stdin(), "stdin"


def read_optional_text_from_args(
    args: argparse.Namespace,
    text_attr: str,
    file_attr: str,
    stdin_attr: str,
    label: str,
) -> tuple[str | None, str]:
    text_value = getattr(args, text_attr, None)
    file_value = getattr(args, file_attr, None)
    stdin_value = getattr(args, stdin_attr, False)
    provided = [text_value is not None, bool(file_value), bool(stdin_value)]
    if sum(1 for item in provided if item) > 1:
        raise GitLabSkillError(f"{label} 只能从参数、文件或标准输入中选择一种来源")
    if file_value:
        return _read_text_file(file_value), file_attr.replace("_", "-")
    if text_value is not None:
        return text_value, text_attr.replace("_", "-")
    if stdin_value:
        return _read_stdin(), "stdin"
    return None, "none"


def add_body_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body-file", help="从 UTF-8 文本文件读取正文")
    group.add_argument("--body", help="直接传入正文；较长内容优先使用 --body-file")
    group.add_argument("--stdin", action="store_true", help="从标准输入读取正文")


def add_optional_description_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--description", help="直接传入描述；较长内容优先使用 --description-file")
    group.add_argument("--description-file", help="从 UTF-8 文本文件读取描述")
    group.add_argument("--stdin", action="store_true", help="从标准输入读取描述")
