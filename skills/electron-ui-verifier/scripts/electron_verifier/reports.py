"""Run report、summary 和初始 pending bundle 构建。"""

from __future__ import annotations

from typing import Any

from .knowledge_models import CanonicalAsset
from .models import MUTATING_ACTIONS, canonical_digest
from .sensitivity import normalize_parameter_schema, placeholders


PERSISTABLE_ACTIONS = MUTATING_ACTIONS | {"waitText", "waitUrlContains"}
RISK_LEVEL = {"coordinate_action": "high", "explicit_nth": "medium", "css_fallback": "medium"}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def clean_passed_steps(journal: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for step in journal.get("steps", []):
        if step.get("status") != "passed" or step.get("detour") is True:
            continue
        action = step.get("action")
        if not isinstance(action, dict):
            continue
        options = action.get("options") if isinstance(action.get("options"), dict) else {}
        if options.get("detour") is True or options.get("exploratoryOnly") is True:
            continue
        if action.get("type") not in PERSISTABLE_ACTIONS:
            continue
        result.append(step)
    return result


def build_report(journal: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    steps = journal.get("steps", [])
    required_failures = [
        step
        for step in steps
        if step.get("status") in {"failed", "unknown"} and step.get("optional") is not True
    ]
    passed = bool(steps) and not required_failures and all(step.get("status") != "running" for step in steps)
    return {
        "schemaVersion": 1,
        "runId": journal["runId"],
        "sessionId": journal["sessionId"],
        "sessionName": journal["sessionName"],
        "appId": journal.get("appId"),
        "appVersion": journal.get("appVersion"),
        "screenDigest": journal.get("screenDigest"),
        "preState": journal.get("preState"),
        "maxRisk": journal.get("maxRisk"),
        "goal": journal.get("goal"),
        "status": "passed" if passed else "failed",
        "createdAt": journal["createdAt"],
        "finalizedAt": journal["updatedAt"],
        "summary": {
            "stepCount": len(steps),
            "passed": sum(step.get("status") == "passed" for step in steps),
            "failed": sum(step.get("status") == "failed" for step in steps),
            "unknown": sum(step.get("status") == "unknown" for step in steps),
            "artifactCount": len(artifacts),
        },
        "steps": steps,
        "artifacts": artifacts,
        "backend": "playwright-cdp",
    }


def verified_post_state(action: Any) -> str:
    """从已通过的 typed action 与 postconditions 生成稳定的安全状态标识。"""

    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    return "verified-" + canonical_digest(
        {"type": action.get("type"), "postconditions": action.get("postconditions") or []}
    )[:24]


def _risk_level(step: dict[str, Any]) -> str:
    levels = [RISK_LEVEL.get(str(item.get("code")), "low") for item in step.get("risks", []) if isinstance(item, dict)]
    return max(levels or ["low"], key=RISK_ORDER.__getitem__)


def _action_goal(journal: dict[str, Any], action: dict[str, Any], index: int) -> str:
    action_id = str(action.get("id") or "").strip()
    options = action.get("options") if isinstance(action.get("options"), dict) else {}
    label = str(options.get("label") or "").strip()
    return (action_id or label or f"{journal['goal']} / {action.get('type')} {index + 1}")[:500]


def _action_aliases(action: dict[str, Any], goal: str) -> list[str]:
    options = action.get("options") if isinstance(action.get("options"), dict) else {}
    values = [str(action.get("id") or "").strip(), str(options.get("label") or "").strip()]
    return sorted({item for item in values if item and item != goal})


def _compatibility(
    journal: dict[str, Any],
    *,
    pre_state: str,
    post_state: str,
    risk: str,
) -> dict[str, Any]:
    version = str(journal["appVersion"])
    return {
        "appVersionMin": version,
        "appVersionMax": version,
        "screenDigest": str(journal["screenDigest"]),
        "preState": pre_state,
        "postState": post_state,
        "risk": risk,
    }


def _proposal_evidence(report: dict[str, Any]) -> list[dict[str, Any]]:
    result = [
        {
            "artifactId": item["artifactId"],
            "sha256": item["sha256"],
            "mediaType": item.get("mediaType"),
        }
        for item in report.get("artifacts", [])
    ]
    result.append({"reportDigest": canonical_digest(report)})
    return result


def build_pending(journal: dict[str, Any], report: dict[str, Any], report_path: str) -> dict[str, Any] | None:
    required_context = ("appId", "goal", "appVersion", "screenDigest", "preState")
    if report.get("status") != "passed" or any(not journal.get(field) for field in required_context):
        return None
    clean = clean_passed_steps(journal)
    mutating = [step for step in clean if step.get("action", {}).get("type") in MUTATING_ACTIONS]
    if not mutating:
        return None
    pending_evidence = [
        {
            "artifactId": item["artifactId"],
            "sha256": item["sha256"],
            "mediaType": item["mediaType"],
        }
        for item in report.get("artifacts", [])
    ]
    pending_evidence.append({"report": report_path, "reportDigest": canonical_digest(report)})
    risks = []
    for step in mutating:
        for risk in step.get("risks", []):
            risks.append(
                {
                    **risk,
                    "stepId": step.get("stepId"),
                    "confirmed": step.get("riskAuthorization", {}).get("consumed") is True,
                }
            )
    parameter_schema = normalize_parameter_schema(journal.get("parameterSchema"))
    created_at = str(report.get("finalizedAt") or journal["updatedAt"])
    proposal_evidence = _proposal_evidence(report)
    current_state = str(journal["preState"])
    ordered_action_ids: list[str] = []
    transitions: list[dict[str, str]] = []
    action_assets: dict[str, CanonicalAsset] = {}
    workflow_risk = "low"
    for index, step in enumerate(clean):
        action = step["action"]
        pre_state = str(step.get("preState") or current_state)
        if pre_state != current_state:
            return None
        post_state = str(step.get("postState") or verified_post_state(action))
        risk = _risk_level(step)
        workflow_risk = max((workflow_risk, risk), key=RISK_ORDER.__getitem__)
        required = sorted(placeholders(action))
        action_schema = {name: parameter_schema[name] for name in required if name in parameter_schema}
        if len(action_schema) != len(required):
            return None
        goal = _action_goal(journal, action, index)
        asset = CanonicalAsset.create(
            kind="action",
            app_id=str(journal["appId"]),
            goal=goal,
            aliases=_action_aliases(action, goal),
            payload={
                "action": action,
                "parameterSchema": action_schema,
                "requiredParameters": required,
                "compatibility": _compatibility(
                    journal,
                    pre_state=pre_state,
                    post_state=post_state,
                    risk=risk,
                ),
                "stats": {"successCount": 1, "failureCount": 0, "lastVerifiedAt": created_at},
            },
            evidence=proposal_evidence,
            created_at=created_at,
        )
        action_assets[asset.asset_id] = asset
        ordered_action_ids.append(asset.asset_id)
        transitions.append({"actionId": asset.asset_id, "preState": pre_state, "postState": post_state})
        current_state = post_state
    required_parameters = sorted(placeholders([step["action"] for step in clean]))
    workflow_schema = {name: parameter_schema[name] for name in required_parameters}
    workflow_asset = CanonicalAsset.create(
        kind="workflow",
        app_id=str(journal["appId"]),
        goal=str(journal["goal"]),
        aliases=[str(item) for item in journal.get("aliases", [])],
        payload={
            "actionIds": ordered_action_ids,
            "parameterSchema": workflow_schema,
            "requiredParameters": required_parameters,
            "compatibility": _compatibility(
                journal,
                pre_state=str(journal["preState"]),
                post_state=current_state,
                risk=workflow_risk,
            ),
            "transitions": transitions,
            "stats": {"successCount": 1, "failureCount": 0, "lastVerifiedAt": created_at},
        },
        evidence=proposal_evidence,
        created_at=created_at,
    )
    proposals = [action_assets[asset_id].to_dict() for asset_id in sorted(action_assets)]
    proposals.append(workflow_asset.to_dict())
    payload: dict[str, Any] = {
        "schemaVersion": 2,
        "pendingId": journal["runId"],
        "runId": journal["runId"],
        "status": "pending",
        "appId": journal["appId"],
        "appVersion": journal["appVersion"],
        "screenDigest": journal["screenDigest"],
        "preState": journal["preState"],
        "proposals": proposals,
        "actionAssetIds": ordered_action_ids,
        "workflowAssetId": workflow_asset.asset_id,
        "evidence": pending_evidence,
        "risks": risks,
        "report": report_path,
        "reportDigest": canonical_digest(report),
    }
    payload["bundleFingerprint"] = canonical_digest(payload)
    return payload


def summary_markdown(report: dict[str, Any], pending_path: str | None) -> str:
    summary = report["summary"]
    lines = [
        f"# Electron UI Verification {report['runId']}",
        "",
        f"- Status: {report['status']}",
        f"- Goal: {report.get('goal') or '-'}",
        f"- Steps: {summary['stepCount']} ({summary['passed']} passed, {summary['failed']} failed, {summary['unknown']} unknown)",
        f"- Artifacts: {summary['artifactCount']}",
        f"- Pending: {pending_path or 'none'}",
        "",
    ]
    return "\n".join(lines)
