"""当前 canonical knowledge 模型、参数模板和内容寻址 ID。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import KNOWLEDGE_FORMAT, SCHEMA_VERSION
from .errors import VerifierError
from .models import canonical_digest


PLACEHOLDER = re.compile(r"^\$\{([A-Za-z][A-Za-z0-9_.-]{0,63})\}$")


def placeholder_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = PLACEHOLDER.fullmatch(value)
    return match.group(1) if match else None


def placeholders(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            result.update(placeholders(item))
    elif isinstance(value, list):
        for item in value:
            result.update(placeholders(item))
    elif isinstance(value, str):
        name = placeholder_name(value)
        if name:
            result.add(name)
        elif "${" in value:
            raise VerifierError("invalid_placeholder", "参数占位符必须占据完整字符串")
    return result


def normalize_parameter_schema(value: Any) -> dict[str, dict[str, Any]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise VerifierError("invalid_parameter_schema", "parameterSchema 必须是 object")
    result: dict[str, dict[str, Any]] = {}
    for name, raw in value.items():
        if not PLACEHOLDER.fullmatch(f"${{{name}}}"):
            raise VerifierError("invalid_parameter_schema", f"参数名无效：{name}")
        if not isinstance(raw, dict):
            raise VerifierError("invalid_parameter_schema", f"参数 {name} schema 必须是 object")
        parameter_type = str(raw.get("type") or "string")
        if parameter_type not in {"string", "number", "integer", "boolean"}:
            raise VerifierError("invalid_parameter_schema", f"参数 {name} type 不受支持：{parameter_type}")
        result[str(name)] = {
            "type": parameter_type,
            "required": raw.get("required", True) is not False,
            "description": str(raw.get("description") or "")[:500],
        }
    return result


def _validate_binding(name: str, value: Any, schema: dict[str, Any]) -> None:
    expected = schema.get("type", "string")
    valid = {
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }[expected]
    if not valid:
        raise VerifierError("invalid_parameter_binding", f"参数 {name} 必须是 {expected}")


def bind_parameters(
    value: Any,
    bindings: Any,
    schema: dict[str, dict[str, Any]],
) -> tuple[Any, set[str]]:
    binding_map = bindings if isinstance(bindings, dict) else {}
    required = placeholders(value)
    undeclared = required - set(schema)
    if undeclared:
        raise VerifierError("undeclared_parameter", f"占位符未在 parameterSchema 声明：{sorted(undeclared)}")
    missing = {name for name in required if name not in binding_map}
    if missing:
        raise VerifierError("parameter_binding_required", f"缺少参数绑定：{sorted(missing)}")
    for name in required:
        _validate_binding(name, binding_map[name], schema[name])

    def replace(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: replace(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child) for child in item]
        name = placeholder_name(item)
        return binding_map[name] if name else item

    return replace(value), required


@dataclass(frozen=True)
class CanonicalAsset:
    asset_id: str
    kind: str
    app_id: str
    goal: str
    aliases: tuple[str, ...]
    payload: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        app_id: str,
        goal: str,
        aliases: list[str],
        payload: dict[str, Any],
        evidence: list[dict[str, Any]],
        created_at: str,
    ) -> "CanonicalAsset":
        if kind not in {"action", "workflow"}:
            raise VerifierError("invalid_asset", f"knowledge kind 不受支持：{kind}")
        if not app_id.strip() or not goal.strip() or not evidence:
            raise VerifierError("invalid_asset", "canonical asset 需要 appId、goal 和 evidence")
        normalized_aliases = sorted(set(item.strip() for item in aliases if item.strip()))
        identity = {
            "kind": kind,
            "appId": app_id,
            "goal": goal,
            "aliases": normalized_aliases,
            "payload": payload,
            "evidence": evidence,
        }
        asset_id = f"{kind}-{canonical_digest(identity)[:40]}"
        return cls(
            asset_id=asset_id,
            kind=kind,
            app_id=app_id,
            goal=goal,
            aliases=tuple(normalized_aliases),
            payload=payload,
            evidence=tuple(evidence),
            created_at=created_at,
        )

    @classmethod
    def decode(cls, value: Any) -> "CanonicalAsset":
        if not isinstance(value, dict):
            raise VerifierError("invalid_asset", "canonical asset 必须是 object")
        if value.get("schemaVersion") != SCHEMA_VERSION or value.get("format") != KNOWLEDGE_FORMAT:
            raise VerifierError("invalid_asset", "canonical asset format/schema 不匹配")
        if value.get("status") != "approved":
            raise VerifierError("invalid_asset", "canonical asset status 必须是 approved")
        payload = value.get("payload")
        evidence = value.get("evidence")
        aliases = value.get("aliases") or []
        if not isinstance(payload, dict) or not isinstance(evidence, list) or not isinstance(aliases, list):
            raise VerifierError("invalid_asset", "canonical asset payload/evidence/aliases 结构无效")
        asset = cls(
            asset_id=str(value.get("assetId") or ""),
            kind=str(value.get("kind") or ""),
            app_id=str(value.get("appId") or ""),
            goal=str(value.get("goal") or ""),
            aliases=tuple(str(item) for item in aliases),
            payload=payload,
            evidence=tuple(item for item in evidence if isinstance(item, dict)),
            created_at=str(value.get("createdAt") or ""),
        )
        expected = cls.create(
            kind=asset.kind,
            app_id=asset.app_id,
            goal=asset.goal,
            aliases=list(asset.aliases),
            payload=asset.payload,
            evidence=list(asset.evidence),
            created_at=asset.created_at,
        ).asset_id
        if asset.asset_id != expected:
            raise VerifierError("invalid_asset", "canonical assetId 与内容摘要不匹配")
        return asset

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "format": KNOWLEDGE_FORMAT,
            "assetId": self.asset_id,
            "kind": self.kind,
            "appId": self.app_id,
            "goal": self.goal,
            "aliases": list(self.aliases),
            "status": "approved",
            "payload": self.payload,
            "evidence": list(self.evidence),
            "createdAt": self.created_at,
        }
