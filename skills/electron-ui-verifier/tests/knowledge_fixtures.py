"""严格 canonical knowledge 测试夹具。"""

from __future__ import annotations

from typing import Any

from electron_verifier.knowledge_models import CanonicalAsset
from electron_verifier.sensitivity import normalize_parameter_schema, placeholders


CREATED_AT = "2026-07-11T00:00:00Z"
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def runtime_context(
    *,
    app_id: str = "demo",
    app_version: str = "1.0.0",
    screen_digest: str = "screen-main",
    pre_state: str = "home",
    max_risk: str = "low",
) -> dict[str, str]:
    return {
        "appId": app_id,
        "appVersion": app_version,
        "screenDigest": screen_digest,
        "preState": pre_state,
        "maxRisk": max_risk,
    }


def action_asset(
    goal: str,
    aliases: list[str] | None = None,
    *,
    app_id: str = "demo",
    app_version: str = "1.0.0",
    screen_digest: str = "screen-main",
    pre_state: str = "home",
    post_state: str = "done",
    risk: str = "low",
    value: Any = None,
    parameter_schema: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
    success_count: int = 4,
    failure_count: int = 0,
    evidence_digest: str = "a" * 64,
) -> CanonicalAsset:
    if action is None:
        action = {
            "type": "fill" if value is not None else "click",
            "locator": {"role": "button", "accessibleName": goal},
            "postconditions": [{"type": "visible", "locator": {"text": post_state}}],
        }
        if value is not None:
            action["value"] = value
    schema = normalize_parameter_schema(parameter_schema)
    return CanonicalAsset.create(
        kind="action",
        app_id=app_id,
        goal=goal,
        aliases=aliases or [],
        payload={
            "action": action,
            "parameterSchema": schema,
            "requiredParameters": sorted(placeholders(action)),
            "compatibility": {
                "appVersionMin": app_version,
                "appVersionMax": app_version,
                "screenDigest": screen_digest,
                "preState": pre_state,
                "postState": post_state,
                "risk": risk,
            },
            "stats": {
                "successCount": success_count,
                "failureCount": failure_count,
                "lastVerifiedAt": CREATED_AT,
            },
        },
        evidence=[{"reportDigest": evidence_digest}],
        created_at=CREATED_AT,
    )


def workflow_asset(
    goal: str,
    actions: list[CanonicalAsset],
    aliases: list[str] | None = None,
    *,
    evidence_digest: str = "b" * 64,
) -> CanonicalAsset:
    if not actions:
        raise ValueError("actions must not be empty")
    first = actions[0]
    first_compatibility = first.payload["compatibility"]
    transitions = []
    merged_schema: dict[str, dict[str, Any]] = {}
    required: set[str] = set()
    risk = "low"
    previous_state = first_compatibility["preState"]
    for asset in actions:
        compatibility = asset.payload["compatibility"]
        if asset.app_id != first.app_id or compatibility["preState"] != previous_state:
            raise ValueError("actions must form one compatible state chain")
        transitions.append(
            {
                "actionId": asset.asset_id,
                "preState": compatibility["preState"],
                "postState": compatibility["postState"],
            }
        )
        for name, definition in asset.payload["parameterSchema"].items():
            if name in merged_schema and merged_schema[name] != definition:
                raise ValueError("action parameter schemas conflict")
            merged_schema[name] = definition
        required.update(asset.payload["requiredParameters"])
        risk = max((risk, compatibility["risk"]), key=RISK_ORDER.__getitem__)
        previous_state = compatibility["postState"]
    return CanonicalAsset.create(
        kind="workflow",
        app_id=first.app_id,
        goal=goal,
        aliases=aliases or [],
        payload={
            "actionIds": [asset.asset_id for asset in actions],
            "parameterSchema": merged_schema,
            "requiredParameters": sorted(required),
            "compatibility": {
                "appVersionMin": first_compatibility["appVersionMin"],
                "appVersionMax": first_compatibility["appVersionMax"],
                "screenDigest": first_compatibility["screenDigest"],
                "preState": first_compatibility["preState"],
                "postState": previous_state,
                "risk": risk,
            },
            "transitions": transitions,
            "stats": {"successCount": 1, "failureCount": 0, "lastVerifiedAt": CREATED_AT},
        },
        evidence=[{"reportDigest": evidence_digest}],
        created_at=CREATED_AT,
    )
