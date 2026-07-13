"""公共 CLI 的稳定 JSON 输出。"""

from __future__ import annotations

import json
from typing import Any


def render_json(value: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def success(operation: str, data: Any, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "operation": operation, "data": data, "meta": meta or {}}


def failure(operation: str, error: Exception) -> dict[str, Any]:
    from .errors import LabError

    if isinstance(error, LabError):
        details = error.to_dict()
    else:
        details = {
            "code": "internal_error",
            "message": "Skill Evaluation Lab 发生未分类错误",
            "outcome": "unknown",
        }
    return {"ok": False, "operation": operation, "error": details, "meta": {}}


def print_json(value: Any, *, pretty: bool = False) -> None:
    print(render_json(value, pretty=pretty))
