"""Run report、summary 和初始 pending bundle 构建。"""

from __future__ import annotations

from typing import Any

from .models import MUTATING_ACTIONS, canonical_digest


PERSISTABLE_ACTIONS = MUTATING_ACTIONS | {"waitText", "waitUrlContains"}


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


def build_pending(journal: dict[str, Any], report: dict[str, Any], report_path: str) -> dict[str, Any] | None:
    if report.get("status") != "passed" or not journal.get("appId") or not journal.get("goal"):
        return None
    clean = clean_passed_steps(journal)
    mutating = [step for step in clean if step.get("action", {}).get("type") in MUTATING_ACTIONS]
    if not mutating:
        return None
    workflow_steps = [step["action"] for step in clean]
    evidence = [
        {
            "artifactId": item["artifactId"],
            "sha256": item["sha256"],
            "mediaType": item["mediaType"],
        }
        for item in report.get("artifacts", [])
    ]
    evidence.append({"report": report_path, "reportDigest": canonical_digest(report)})
    risks = []
    for step in mutating:
        for risk in step.get("risks", []):
            risks.append(
                {
                    **risk,
                    "stepId": step.get("stepId"),
                    "confirmed": step.get("result", {}).get("riskConfirmed") is True,
                }
            )
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "pendingId": journal["runId"],
        "runId": journal["runId"],
        "status": "pending",
        "appId": journal["appId"],
        "workflow": {
            "schemaVersion": 1,
            "goal": journal["goal"],
            "appId": journal["appId"],
            "aliases": journal.get("aliases") or [],
            "parameterSchema": journal.get("parameterSchema") or {},
            "steps": workflow_steps,
        },
        "evidence": evidence,
        "parameterSchema": journal.get("parameterSchema") or {},
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
