"""Knowledge 检索与服务端执行共享的现场兼容性规则。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errors import VerifierError


RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
VERSION_PART = re.compile(r"\d+")


def optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _version(value: str) -> tuple[int, ...]:
    parts = tuple(int(item) for item in VERSION_PART.findall(value))
    if not parts:
        raise VerifierError("invalid_app_version", f"appVersion 无法比较：{value}")
    return parts


def _compare_versions(left: str, right: str) -> int:
    left_parts = _version(left)
    right_parts = _version(right)
    width = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (width - len(left_parts))
    padded_right = right_parts + (0,) * (width - len(right_parts))
    return (padded_left > padded_right) - (padded_left < padded_right)


@dataclass(frozen=True)
class RuntimeContext:
    app_id: str
    app_version: str | None = None
    screen_digest: str | None = None
    pre_state: str | None = None
    max_risk: str = "low"

    @classmethod
    def decode(cls, value: Any) -> "RuntimeContext":
        if not isinstance(value, dict):
            raise VerifierError("invalid_retrieval_context", "runtime context 必须是 object")
        app_id = str(value.get("appId") or "").strip()
        risk = str(value.get("maxRisk") or "low").lower()
        if not app_id:
            raise VerifierError("app_id_required", "knowledge 操作需要 appId")
        if len(app_id) > 200:
            raise VerifierError("invalid_retrieval_context", "appId 超过 200 字符上限")
        if risk not in RISK_ORDER:
            raise VerifierError("invalid_risk_level", f"maxRisk 不受支持：{risk}")
        return cls(
            app_id=app_id,
            app_version=optional_text(value.get("appVersion")),
            screen_digest=optional_text(value.get("screenDigest")),
            pre_state=optional_text(value.get("preState")),
            max_risk=risk,
        )


def compatibility_reasons(compatibility: dict[str, Any], context: RuntimeContext) -> list[str]:
    reasons: list[str] = []
    minimum = optional_text(compatibility.get("appVersionMin"))
    maximum = optional_text(compatibility.get("appVersionMax"))
    if minimum or maximum:
        if context.app_version is None:
            reasons.append("app_version_required")
        elif minimum and maximum and minimum == maximum:
            if context.app_version != minimum:
                reasons.append("app_version_mismatch")
        else:
            if minimum and _compare_versions(context.app_version, minimum) < 0:
                reasons.append("app_version_below_minimum")
            if maximum and _compare_versions(context.app_version, maximum) > 0:
                reasons.append("app_version_above_maximum")
    screen = optional_text(compatibility.get("screenDigest"))
    if screen and context.screen_digest != screen:
        reasons.append("screen_digest_mismatch" if context.screen_digest else "screen_digest_required")
    state = optional_text(compatibility.get("preState"))
    if state and context.pre_state != state:
        reasons.append("pre_state_mismatch" if context.pre_state else "pre_state_required")
    risk = str(compatibility.get("risk") or "low").lower()
    if risk not in RISK_ORDER or RISK_ORDER[risk] > RISK_ORDER[context.max_risk]:
        reasons.append("risk_not_allowed")
    return reasons


def require_asset_compatibility(
    asset_app_id: str,
    compatibility: dict[str, Any],
    context: RuntimeContext,
) -> None:
    if asset_app_id != context.app_id:
        raise VerifierError("asset_app_mismatch", "asset appId 与当前 run 不一致", status=409)
    reasons = compatibility_reasons(compatibility, context)
    if reasons:
        raise VerifierError(
            "asset_context_mismatch",
            "asset 与当前 run 现场不兼容",
            status=409,
            details={"reasons": reasons},
        )
