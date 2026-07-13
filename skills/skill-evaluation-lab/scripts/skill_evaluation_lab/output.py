"""公共 CLI 的稳定 JSON 输出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import PathError


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


def write_new_text(path: Path, content: str) -> None:
    """以独占创建方式写文本，避免静默覆盖既有证据。"""
    if path.exists():
        raise PathError(
            "输出路径已存在，拒绝覆盖",
            code="PATH_OUTPUT_EXISTS",
            path=str(path),
            guidance="选择新的输出路径，或由用户明确清理旧证据后重试。",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    except FileExistsError as exc:
        raise PathError(
            "输出路径在写入前已被占用",
            code="PATH_OUTPUT_EXISTS",
            path=str(path),
        ) from exc


def write_new_json(path: Path, value: Any) -> None:
    write_new_text(path, render_json(value, pretty=True) + "\n")
