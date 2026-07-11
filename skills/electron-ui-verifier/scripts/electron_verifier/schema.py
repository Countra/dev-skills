"""JSON 契约加载和轻量边界检查。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import VerifierError


DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


def load_schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifierError("invalid_schema", f"无法读取 JSON Schema {path}: {exc}", status=500) from exc
    if not isinstance(value, dict):
        raise VerifierError("invalid_schema", f"JSON Schema 根节点必须是 object：{path}", status=500)
    if value.get("$schema") != DRAFT_2020_12:
        raise VerifierError("invalid_schema", f"JSON Schema 必须声明 Draft 2020-12：{path}", status=500)
    return value


def validate_schema_directory(path: Path) -> list[str]:
    files = sorted(path.glob("*.schema.json"))
    if not files:
        raise VerifierError("schema_missing", f"未找到 schema 文件：{path}", status=500)
    identifiers: set[str] = set()
    for schema_path in files:
        schema = load_schema(schema_path)
        identifier = str(schema.get("$id") or "")
        if not identifier:
            raise VerifierError("invalid_schema", f"JSON Schema 缺少 $id：{schema_path}", status=500)
        if identifier in identifiers:
            raise VerifierError("invalid_schema", f"JSON Schema $id 重复：{identifier}", status=500)
        identifiers.add(identifier)
    return [str(item) for item in files]


def ensure_json_depth(value: Any, maximum: int, current: int = 0) -> None:
    if current > maximum:
        raise VerifierError("json_too_deep", f"JSON 嵌套深度超过上限 {maximum}")
    if isinstance(value, dict):
        for item in value.values():
            ensure_json_depth(item, maximum, current + 1)
    elif isinstance(value, list):
        for item in value:
            ensure_json_depth(item, maximum, current + 1)
