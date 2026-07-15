"""高风险 UI mutation 的独立、短期和一次性授权凭据。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json, exclusive_write_json
from .errors import VerifierError
from .locators import locator_risks
from .models import ActionSpec, MUTATING_ACTIONS, canonical_digest


RECEIPT_TTL_SECONDS = 600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerifierError("risk_authorization_invalid", "risk authorization 时间戳无效", status=500) from exc
    return parsed.astimezone(timezone.utc)


def authorization_risks(action: ActionSpec) -> list[dict[str, Any]]:
    if action.action_type not in MUTATING_ACTIONS:
        return []
    risks = [risk for risk in locator_risks(action.locator) if risk.get("learnable") is False]
    if action.action_type in {"click", "doubleClick"} and action.locator is None:
        risks.append({"code": "coordinate_action", "learnable": False})
    return sorted(risks, key=lambda item: (str(item.get("code")), int(item.get("nth", -1))))


def target_identity(session_id: str, target_id: str | None, app_id: str | None) -> str:
    return canonical_digest(
        {
            "sessionId": session_id,
            "targetId": target_id or "",
            "appId": app_id or "",
        }
    )


class RiskAuthorizationService:
    """receipt 不保存动作原文或绑定值，只绑定不可逆摘要和目标身份。"""

    def __init__(self, state_root: Path) -> None:
        self.root = state_root / "risk-authorizations"
        self.previews = self.root / "previews"
        self.receipts = self.root / "receipts"
        self.approvals = self.root / "approvals"
        self.consumed = self.root / "consumed"

    @staticmethod
    def _identity(value: str, label: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise VerifierError("risk_authorization_invalid", f"{label} 不是 UUID") from exc

    def _load(self, path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VerifierError("risk_authorization_not_found", f"{label} 不存在", status=404) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("risk_authorization_invalid", f"无法读取 {label}：{exc}", status=500) from exc
        if not isinstance(value, dict):
            raise VerifierError("risk_authorization_invalid", f"{label} 结构无效", status=500)
        return value

    def preview(
        self,
        *,
        run_id: str,
        action_digest: str,
        target: str,
        risks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not risks:
            raise VerifierError("risk_authorization_not_required", "该 action 不需要风险授权")
        preview_id = str(uuid.uuid4())
        created = _now()
        preview = {
            "schemaVersion": 1,
            "previewId": preview_id,
            "runId": run_id,
            "actionDigest": action_digest,
            "targetIdentity": target,
            "risks": risks,
            "createdAt": _timestamp(created),
            "expireAt": _timestamp(created + timedelta(seconds=RECEIPT_TTL_SECONDS)),
        }
        preview["fingerprint"] = canonical_digest(preview)
        atomic_write_json(self.previews / f"{preview_id}.json", preview)
        return {
            "ok": True,
            "previewId": preview_id,
            "fingerprint": preview["fingerprint"],
            "runId": run_id,
            "targetIdentity": target,
            "risks": risks,
            "expireAt": preview["expireAt"],
        }

    def approve(self, preview_id: str, fingerprint: str, note: str) -> dict[str, Any]:
        normalized = self._identity(preview_id, "previewId")
        preview = self._load(self.previews / f"{normalized}.json", "risk preview")
        if preview.get("fingerprint") != fingerprint:
            raise VerifierError("risk_authorization_mismatch", "risk preview fingerprint 不匹配", status=409)
        if _parse_timestamp(preview.get("expireAt")) <= _now():
            raise VerifierError("risk_authorization_expired", "risk preview 已过期", status=409)
        approved_note = note.strip()
        if not approved_note or len(approved_note) > 500:
            raise VerifierError("risk_authorization_note_required", "批准 note 必须为 1..500 个字符")
        note_digest = canonical_digest({"note": approved_note})
        receipt_id = str(uuid.uuid4())
        approval = {
            "schemaVersion": 1,
            "previewId": normalized,
            "fingerprint": fingerprint,
            "noteDigest": note_digest,
            "receiptId": receipt_id,
            "approvedAt": _timestamp(_now()),
        }
        approval_path = self.approvals / f"{normalized}.json"
        if not exclusive_write_json(approval_path, approval):
            approval = self._load(approval_path, "risk approval")
            if approval.get("fingerprint") != fingerprint or approval.get("noteDigest") != note_digest:
                raise VerifierError("risk_authorization_conflict", "risk preview 已使用不同批准内容", status=409)
            receipt_id = self._identity(str(approval.get("receiptId")), "receiptId")
        receipt = {
            "schemaVersion": 1,
            "receiptId": receipt_id,
            "previewId": normalized,
            "runId": preview["runId"],
            "actionDigest": preview["actionDigest"],
            "targetIdentity": preview["targetIdentity"],
            "risks": preview["risks"],
            "approvedAt": approval["approvedAt"],
            "expireAt": preview["expireAt"],
            "noteDigest": note_digest,
        }
        created = exclusive_write_json(self.receipts / f"{receipt_id}.json", receipt)
        if not created:
            existing = self._load(self.receipts / f"{receipt_id}.json", "risk receipt")
            if existing != receipt:
                raise VerifierError("risk_authorization_conflict", "risk receipt 内容冲突", status=409)
        return {
            "ok": True,
            "receiptId": receipt_id,
            "runId": receipt["runId"],
            "targetIdentity": receipt["targetIdentity"],
            "risks": receipt["risks"],
            "expireAt": receipt["expireAt"],
            "oneTime": True,
        }

    def consume(
        self,
        receipt_id: str | None,
        *,
        run_id: str,
        action_digest: str,
        target: str,
        risks: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not risks:
            if receipt_id:
                raise VerifierError("risk_authorization_not_required", "低风险 action 不接受 risk receipt")
            return None
        if not receipt_id:
            raise VerifierError("risk_authorization_required", "高风险 action 需要独立 risk receipt", status=409)
        normalized = self._identity(receipt_id, "receiptId")
        receipt = self._load(self.receipts / f"{normalized}.json", "risk receipt")
        expected = {
            "runId": run_id,
            "actionDigest": action_digest,
            "targetIdentity": target,
            "risks": risks,
        }
        mismatched = [key for key, value in expected.items() if receipt.get(key) != value]
        if mismatched:
            raise VerifierError(
                "risk_authorization_mismatch",
                "risk receipt 与当前 run/action/target 不匹配",
                status=409,
                details={"fields": mismatched},
            )
        if _parse_timestamp(receipt.get("expireAt")) <= _now():
            raise VerifierError("risk_authorization_expired", "risk receipt 已过期", status=409)
        marker = {
            "schemaVersion": 1,
            "receiptId": normalized,
            "consumedAt": _timestamp(_now()),
            "contextDigest": canonical_digest(expected),
        }
        if not exclusive_write_json(self.consumed / f"{normalized}.json", marker):
            raise VerifierError("risk_authorization_consumed", "risk receipt 已使用", status=409)
        return {"receiptId": normalized, "risks": risks, "consumed": True}
