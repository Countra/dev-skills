"""当前 canonical knowledge 模型、参数模板和内容寻址 ID。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import KNOWLEDGE_FORMAT, SCHEMA_VERSION
from .errors import VerifierError
from .models import ActionSpec, canonical_digest
from .sensitivity import normalize_parameter_schema, placeholders


ASSET_FIELDS = {
    "schemaVersion",
    "format",
    "assetId",
    "kind",
    "appId",
    "goal",
    "aliases",
    "status",
    "payload",
    "evidence",
    "createdAt",
}
ACTION_ID = re.compile(r"^action-[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RISK_LEVELS = {"low", "medium", "high"}
COMPATIBILITY_FIELDS = {
    "appVersionMin",
    "appVersionMax",
    "screenDigest",
    "preState",
    "postState",
    "risk",
}
STATS_FIELDS = {"successCount", "failureCount", "lastVerifiedAt"}


def _timestamp(value: Any, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerifierError("invalid_asset", f"{label} 必须是 RFC3339 时间") from exc
    if parsed.tzinfo is None:
        raise VerifierError("invalid_asset", f"{label} 必须包含时区")
    return text


def _closed(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise VerifierError("invalid_asset", f"{label} 字段不完整或包含未知字段")
    return value


def _validate_compatibility(value: Any) -> dict[str, Any]:
    compatibility = _closed(value, COMPATIBILITY_FIELDS, "compatibility")
    for field in ("appVersionMin", "appVersionMax", "screenDigest", "preState", "postState"):
        if not isinstance(compatibility.get(field), str) or not compatibility[field].strip():
            raise VerifierError("invalid_asset", f"compatibility.{field} 必须是非空字符串")
    if compatibility.get("risk") not in RISK_LEVELS:
        raise VerifierError("invalid_asset", "compatibility.risk 必须是 low/medium/high")
    return compatibility


def _validate_stats(value: Any) -> None:
    stats = _closed(value, STATS_FIELDS, "stats")
    for field in ("successCount", "failureCount"):
        count = stats.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise VerifierError("invalid_asset", f"stats.{field} 必须是非负整数")
    if stats["successCount"] < 1:
        raise VerifierError("invalid_asset", "批准资产的 successCount 基线至少为 1")
    _timestamp(stats.get("lastVerifiedAt"), "stats.lastVerifiedAt")


def _validate_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise VerifierError("invalid_asset", "canonical asset 至少需要一项 evidence")
    for item in value:
        if not isinstance(item, dict):
            raise VerifierError("invalid_asset", "evidence item 必须是 object")
        if "artifactId" in item:
            if set(item) - {"artifactId", "sha256", "mediaType"} or not item.get("artifactId"):
                raise VerifierError("invalid_asset", "artifact evidence 字段无效")
            if not SHA256.fullmatch(str(item.get("sha256") or "")):
                raise VerifierError("invalid_asset", "artifact evidence sha256 无效")
        elif set(item) == {"reportDigest"}:
            if not SHA256.fullmatch(str(item.get("reportDigest") or "")):
                raise VerifierError("invalid_asset", "report evidence digest 无效")
        else:
            raise VerifierError("invalid_asset", "evidence item 类型不受支持")
    return value


def _validate_payload(kind: str, value: Any) -> dict[str, Any]:
    if kind == "action":
        payload = _closed(
            value,
            {"action", "parameterSchema", "requiredParameters", "compatibility", "stats"},
            "action payload",
        )
        action = payload.get("action")
        ActionSpec.decode(action)
        required = sorted(placeholders(action))
    elif kind == "workflow":
        payload = _closed(
            value,
            {"actionIds", "parameterSchema", "requiredParameters", "compatibility", "transitions", "stats"},
            "workflow payload",
        )
        action_ids = payload.get("actionIds")
        transitions = payload.get("transitions")
        if (
            not isinstance(action_ids, list)
            or not action_ids
            or any(not isinstance(item, str) or not ACTION_ID.fullmatch(item) for item in action_ids)
        ):
            raise VerifierError("invalid_asset", "workflow actionIds 必须是有序 action asset IDs")
        if not isinstance(transitions, list) or len(transitions) != len(action_ids):
            raise VerifierError("invalid_asset", "workflow transitions 必须与 actionIds 一一对应")
        previous = None
        for index, transition in enumerate(transitions):
            item = _closed(transition, {"actionId", "preState", "postState"}, "transition")
            if any(not isinstance(item.get(field), str) or not item[field].strip() for field in item):
                raise VerifierError("invalid_asset", "workflow transition 字段必须是非空字符串")
            if item["actionId"] != action_ids[index]:
                raise VerifierError("invalid_asset", "workflow transition actionId 顺序不一致")
            if previous is not None and item["preState"] != previous:
                raise VerifierError("invalid_asset", "workflow transition state 无法衔接")
            previous = item["postState"]
        raw_required = payload.get("requiredParameters")
        if not isinstance(raw_required, list) or any(not isinstance(item, str) for item in raw_required):
            raise VerifierError("invalid_asset", "workflow requiredParameters 必须是字符串数组")
        required = sorted(set(raw_required))
    else:
        raise VerifierError("invalid_asset", f"knowledge kind 不受支持：{kind}")
    schema = normalize_parameter_schema(payload.get("parameterSchema"))
    if payload.get("parameterSchema") != schema:
        raise VerifierError("invalid_asset", "parameterSchema 必须使用规范化 closed 结构")
    if payload.get("requiredParameters") != required or set(required) - set(schema):
        raise VerifierError("invalid_asset", "requiredParameters 与 payload placeholders/schema 不一致")
    compatibility = _validate_compatibility(payload.get("compatibility"))
    if kind == "workflow":
        transitions = payload["transitions"]
        if transitions[0]["preState"] != compatibility["preState"] or transitions[-1]["postState"] != compatibility["postState"]:
            raise VerifierError("invalid_asset", "workflow compatibility 与 transition chain 不一致")
    _validate_stats(payload.get("stats"))
    return payload


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
        if not isinstance(app_id, str) or not isinstance(goal, str) or not app_id.strip() or not goal.strip():
            raise VerifierError("invalid_asset", "canonical asset 需要 appId、goal 和 evidence")
        if not isinstance(aliases, list) or any(not isinstance(item, str) for item in aliases):
            raise VerifierError("invalid_asset", "canonical aliases 必须是字符串数组")
        normalized_aliases = sorted(set(item.strip() for item in aliases if item.strip()))
        normalized_payload = _validate_payload(kind, payload)
        normalized_evidence = _validate_evidence(evidence)
        normalized_created_at = _timestamp(created_at, "createdAt")
        identity = {
            "kind": kind,
            "appId": app_id.strip(),
            "goal": goal.strip(),
            "aliases": normalized_aliases,
            "payload": normalized_payload,
            "evidence": normalized_evidence,
            "createdAt": normalized_created_at,
        }
        asset_id = f"{kind}-{canonical_digest(identity)[:40]}"
        return cls(
            asset_id=asset_id,
            kind=kind,
            app_id=app_id.strip(),
            goal=goal.strip(),
            aliases=tuple(normalized_aliases),
            payload=normalized_payload,
            evidence=tuple(normalized_evidence),
            created_at=normalized_created_at,
        )

    @classmethod
    def decode(cls, value: Any) -> "CanonicalAsset":
        if not isinstance(value, dict):
            raise VerifierError("invalid_asset", "canonical asset 必须是 object")
        if set(value) != ASSET_FIELDS:
            raise VerifierError("invalid_asset", "canonical asset 字段不完整或包含未知字段")
        if value.get("schemaVersion") != SCHEMA_VERSION or value.get("format") != KNOWLEDGE_FORMAT:
            raise VerifierError("invalid_asset", "canonical asset format/schema 不匹配")
        if value.get("status") != "approved":
            raise VerifierError("invalid_asset", "canonical asset status 必须是 approved")
        payload = value.get("payload")
        evidence = value.get("evidence")
        aliases = value.get("aliases") or []
        if (
            not isinstance(payload, dict)
            or not isinstance(evidence, list)
            or not isinstance(aliases, list)
            or any(not isinstance(item, str) for item in aliases)
        ):
            raise VerifierError("invalid_asset", "canonical asset payload/evidence/aliases 结构无效")
        asset = cls(
            asset_id=str(value.get("assetId") or ""),
            kind=str(value.get("kind") or ""),
            app_id=str(value.get("appId") or ""),
            goal=str(value.get("goal") or ""),
            aliases=tuple(str(item) for item in aliases),
            payload=payload,
            evidence=tuple(evidence),
            created_at=str(value.get("createdAt") or ""),
        )
        canonical = cls.create(
            kind=asset.kind,
            app_id=asset.app_id,
            goal=asset.goal,
            aliases=list(asset.aliases),
            payload=asset.payload,
            evidence=list(asset.evidence),
            created_at=asset.created_at,
        )
        if asset.asset_id != canonical.asset_id:
            raise VerifierError("invalid_asset", "canonical assetId 与内容摘要不匹配")
        if canonical.to_dict() != value:
            raise VerifierError("invalid_asset", "canonical asset 使用了非规范表示")
        return canonical

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
