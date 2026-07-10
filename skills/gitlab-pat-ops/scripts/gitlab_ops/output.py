"""GitLab 命令的稳定 JSON 输出。"""

from __future__ import annotations

import json
from typing import Any

from .config import BASE_URL_ENV, TOKEN_ENV
from .errors import GitLabSkillError, MissingEnvironmentError


def json_dumps(value: Any, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def print_json(value: Any, pretty: bool = False) -> None:
    print(json_dumps(value, pretty=pretty))


def success_envelope(
    data: Any,
    *,
    operation: str = "gitlab.operation",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"ok": True, "operation": operation, "data": data, "meta": meta or {}}


def output_result(
    value: Any,
    pretty: bool = False,
    *,
    operation: str = "gitlab.operation",
    meta: dict[str, Any] | None = None,
) -> None:
    print_json(success_envelope(value, operation=operation, meta=meta), pretty=pretty)


def output_client_result(
    client: Any,
    value: Any,
    *,
    operation: str,
    pretty: bool = False,
) -> None:
    """输出最近一次 GitLab 请求的可审计元数据。"""
    meta = dict(getattr(client, "last_meta", {}) or {})
    output_result(value, pretty=pretty, operation=operation, meta=meta)


def output_error(error: Exception, pretty: bool = False, *, operation: str = "gitlab.operation") -> int:
    if isinstance(error, GitLabSkillError):
        meta: dict[str, Any] = {}
        if error.request_id:
            meta["request_id"] = error.request_id
        value: dict[str, Any] = {
            "ok": False,
            "operation": operation,
            "error": error.to_error_dict(),
            "meta": meta,
        }
        if isinstance(error, MissingEnvironmentError):
            value["required"] = [BASE_URL_ENV, TOKEN_ENV]
            value["powershell"] = [
                '$env:SKILL_GITLAB_BASE_URL="https://gitlab.example.com"',
                '$env:SKILL_GITLAB_PAT="..."',
            ]
        print_json(value, pretty=pretty)
        return error.exit_code
    print_json(
        {
            "ok": False,
            "operation": operation,
            "error": {
                "code": "internal_error",
                "message": "GitLab 命令发生未分类错误",
                "outcome": "unknown",
                "retryable": False,
            },
            "meta": {},
        },
        pretty=pretty,
    )
    return 1
