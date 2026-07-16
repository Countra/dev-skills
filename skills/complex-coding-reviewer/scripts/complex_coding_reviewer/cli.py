"""Reviewer CLI 的统一 JSON envelope 与参数辅助。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .errors import ReviewError


def envelope(operation: str, result: Any) -> dict[str, Any]:
    return {"ok": True, "operation": operation, "result": result, "error": None}


def error_envelope(operation: str, error: ReviewError) -> dict[str, Any]:
    return {"ok": False, "operation": operation, "result": None, "error": error.as_dict()}


def run_cli(operation: str, handler: Callable[[], Any]) -> int:
    try:
        payload = envelope(operation, handler())
        exit_code = 0
    except ReviewError as exc:
        payload = error_envelope(operation, exc)
        exit_code = 1
    except (OSError, UnicodeError, ValueError) as exc:
        payload = error_envelope(
            operation,
            ReviewError("REVIEW_INTERNAL_IO_ERROR", f"操作失败：{exc}"),
        )
        exit_code = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def require_review_root(output: Path | None, review_root: Path | None) -> None:
    if output is not None and review_root is None:
        raise ReviewError(
            "REVIEW_OUTPUT_ROOT_REQUIRED",
            "写入输出时必须显式提供 --review-root。",
            path=str(output),
        )


def parse_roles(values: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ReviewError("REVIEW_TARGET_ROLE_INVALID", "--role 必须使用 PATH=ROLE。", path=value)
        path, role = value.split("=", 1)
        if not path or not role:
            raise ReviewError("REVIEW_TARGET_ROLE_INVALID", "--role 的 PATH 与 ROLE 均不能为空。", path=value)
        if path in roles:
            raise ReviewError("REVIEW_TARGET_ROLE_INVALID", "同一路径不能重复声明 role。", path=path)
        roles[path] = role
    return roles
