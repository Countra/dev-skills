"""当前 canonical knowledge 模型、参数模板和内容寻址 ID。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import KNOWLEDGE_FORMAT, SCHEMA_VERSION
from .errors import VerifierError
from .models import canonical_digest
from .sensitivity import bind_parameters, normalize_parameter_schema, placeholder_name, placeholders


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
