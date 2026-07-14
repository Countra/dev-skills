"""评估脚本共用的严格 knowledge asset 构造器。"""

from __future__ import annotations

from electron_verifier.knowledge_models import CanonicalAsset


CREATED_AT = "2026-07-11T00:00:00Z"


def action_asset(
    app_id: str,
    goal: str,
    aliases: list[str],
    *,
    success_count: int = 3,
    evidence_digest: str = "c" * 64,
) -> CanonicalAsset:
    return CanonicalAsset.create(
        kind="action",
        app_id=app_id,
        goal=goal,
        aliases=aliases,
        payload={
            "action": {
                "type": "click",
                "locator": {"role": "button", "accessibleName": goal},
                "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
            },
            "parameterSchema": {},
            "requiredParameters": [],
            "compatibility": {
                "appVersionMin": "1.0.0",
                "appVersionMax": "1.0.0",
                "screenDigest": "screen-main",
                "preState": "home",
                "postState": "done",
                "risk": "low",
            },
            "stats": {
                "successCount": success_count,
                "failureCount": 0,
                "lastVerifiedAt": CREATED_AT,
            },
        },
        evidence=[{"reportDigest": evidence_digest}],
        created_at=CREATED_AT,
    )


def runtime_context(app_id: str) -> dict[str, str]:
    return {
        "appId": app_id,
        "appVersion": "1.0.0",
        "screenDigest": "screen-main",
        "preState": "home",
        "maxRisk": "low",
    }
