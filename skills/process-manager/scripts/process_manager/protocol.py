"""公共成功/失败 envelope。"""

from __future__ import annotations

import json
from typing import Any

from .errors import PMError


def success(operation: str, data: Any, *, instance_id: str | None = None) -> dict[str, Any]:
    meta = {"managerInstanceId": instance_id} if instance_id else {}
    return {"ok": True, "operation": operation, "data": data, "meta": meta}


def failure(
    operation: str,
    error: Exception,
    *,
    instance_id: str | None = None,
    include_diagnostics: bool = True,
) -> dict[str, Any]:
    meta = {"managerInstanceId": instance_id} if instance_id else {}
    if isinstance(error, PMError):
        value = error.public_dict(include_diagnostics=include_diagnostics)
    else:
        value = {
            "code": "internal_error",
            "message": "process-manager 发生未分类错误",
            "retryable": False,
        }
    return {"ok": False, "operation": operation, "error": value, "meta": meta}


def print_json(value: Any, *, pretty: bool = True) -> None:
    if pretty:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)
