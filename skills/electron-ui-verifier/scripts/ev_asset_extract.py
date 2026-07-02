#!/usr/bin/env python3
"""从 verifier report 整理 action/workflow 资产候选。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ev_common import EVError, fail, print_json, read_json
from ev_knowledge_extract import extract_knowledge, safe_report_path
from ev_knowledge_store import clip_text, hash_key, stable_id


TEXT_PARAMETER_LIMIT = 120
PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/[^/])")
LONG_NUMBER_RE = re.compile(r"\d{8,}")
DIAGNOSTIC_ACTIONS = {
    "collectConsole",
    "collectExceptions",
    "collectNetwork",
    "domSnapshot",
    "accessibilitySnapshot",
}


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return name or "value"


def step_id(step: dict[str, Any], index: int) -> str:
    return str(step.get("id") or f"step-{index + 1}")


def step_data(step: dict[str, Any]) -> dict[str, Any]:
    data = step.get("data")
    return data if isinstance(data, dict) else {}


def step_artifacts(step: dict[str, Any]) -> list[str]:
    artifacts = step.get("artifacts")
    return [str(item) for item in artifacts if isinstance(item, str)] if isinstance(artifacts, list) else []


def basename_or_default(path_text: str | None, default: str) -> str:
    if not path_text:
        return default
    return Path(path_text).name or default


def should_parameterize(text: str) -> tuple[bool, str | None]:
    if PATH_RE.search(text):
        return True, "localPath"
    if len(text) > TEXT_PARAMETER_LIMIT:
        return True, "longText"
    if LONG_NUMBER_RE.search(text):
        return True, "businessLikeNumber"
    return False, None


def parameterized_text(value: Any, step_key: str, field: str) -> tuple[str, dict[str, Any], list[str]]:
    text = str(value or "")
    need_param, reason = should_parameterize(text)
    if not need_param:
        return text, {}, []
    name = safe_name(f"{step_key}_{field}")
    return (
        "${" + name + "}",
        {
            name: {
                "type": "string",
                "required": True,
                "reason": reason,
                "sampleLength": len(text),
            }
        },
        [f"parameterized:{reason}"],
    )


def selector_candidates(action: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if action in {"clickText", "waitText"}:
        text = payload.get("text")
        return [{"type": "text", "value": text}] if text else []
    if action == "fillText":
        selector = payload.get("selector")
        return [{"type": "css", "value": selector}] if selector else []
    if action == "clickXY":
        return [{"type": "coordinate", "x": payload.get("x"), "y": payload.get("y")}]
    if action == "waitUrlContains":
        text = payload.get("text")
        return [{"type": "urlContains", "value": text}] if text else []
    return []


def action_label(action: str, payload: dict[str, Any]) -> str:
    if action in {"clickText", "waitText", "waitUrlContains"}:
        return f"{action}: {clip_text(payload.get('text'), 80)}"
    if action == "fillText":
        return f"fillText: {clip_text(payload.get('selector'), 80)}"
    if action == "pressKey":
        return f"pressKey: {clip_text(payload.get('key'), 40)}"
    return action


def confidence_for(action: str, risks: list[str]) -> float:
    if action == "clickXY":
        return 0.25
    if action in DIAGNOSTIC_ACTIONS:
        return 0.45
    base = 0.65 if action in {"clickText", "waitText", "waitUrlContains", "pressKey"} else 0.55
    return max(0.2, base - 0.1 * len(risks))


def build_action_payload(step: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, dict[str, Any], list[str], str | None]:
    action = str(step.get("action") or "")
    data = step_data(step)
    key = step_id(step, index)
    params: dict[str, Any] = {}
    risks: list[str] = []

    if action == "clickText":
        text, extra_params, extra_risks = parameterized_text(data.get("text"), key, "text")
        if not text:
            return None, params, risks, "clickText 缺少可复原 text"
        params.update(extra_params)
        risks.extend(extra_risks)
        candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
        payload: dict[str, Any] = {"text": text}
        if isinstance(candidate.get("text"), str) and str(candidate.get("text")).strip() != str(data.get("text") or "").strip():
            risks.append("textMatchedByContains")
        return {"clickText": payload}, params, risks, None

    if action == "clickXY":
        if "x" not in data or "y" not in data:
            return None, params, risks, "clickXY 缺少坐标"
        risks.append("coordinateFallback")
        return {"clickXY": {"x": data.get("x"), "y": data.get("y")}}, params, risks, None

    if action == "waitText":
        text, extra_params, extra_risks = parameterized_text(data.get("text"), key, "text")
        if not text:
            return None, params, risks, "waitText 缺少可复原 text"
        params.update(extra_params)
        risks.extend(extra_risks)
        return {"waitText": {"text": text}}, params, risks, None

    if action == "waitUrlContains":
        text, extra_params, extra_risks = parameterized_text(data.get("urlContains"), key, "url")
        if not text:
            return None, params, risks, "waitUrlContains 缺少 urlContains"
        params.update(extra_params)
        risks.extend(extra_risks)
        return {"waitUrlContains": {"text": text}}, params, risks, None

    if action == "pressKey":
        key_value = str(data.get("key") or "")
        if not key_value:
            return None, params, risks, "pressKey 缺少 key"
        return {"pressKey": {"key": key_value}}, params, risks, None

    if action == "fillText":
        selector = data.get("selector")
        if not selector:
            return None, params, risks, "fillText 缺少 selector"
        risks.append("valueNotCaptured")
        params[f"{safe_name(key)}_value"] = {"type": "string", "required": True, "reason": "fillText value is not stored in report"}
        return {"fillText": {"selector": selector, "value": "${" + f"{safe_name(key)}_value" + "}"}}, params, risks, None

    if action in {"snapshot", "screenshot", "extractText", "extractTable"}:
        if action == "screenshot":
            name = basename_or_default(step_artifacts(step)[0] if step_artifacts(step) else None, f"{key}.png")
            return {"screenshot": name}, params, risks, None
        if action in {"extractText", "extractTable"}:
            return {action: {"name": data.get("name", key)}}, params, risks, None
        return {"snapshot": True}, params, risks, None

    if action in DIAGNOSTIC_ACTIONS:
        name = str(data.get("name") or key)
        if action in {"domSnapshot", "accessibilitySnapshot"}:
            risks.append("largeArtifact")
        return {action: {"name": name}}, params, risks, None

    if action == "evaluate":
        risks.append("evaluateNotReplayable")
        return None, params, risks, "evaluate 不从 report 反推表达式"

    return None, params, risks, f"不支持的 action: {action}"


def workflow_step_from_action(step: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, dict[str, Any], list[str], str | None]:
    payload, params, risks, reason = build_action_payload(step, index)
    if payload is None:
        return None, params, risks, reason
    result = {"id": step_id(step, index), **payload}
    if step.get("status") == "skipped":
        result["continueOnFailure"] = True
        risks.append("optionalSkippedStep")
    return result, params, risks, None


def merge_params(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        target.setdefault(key, value)


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def source_artifacts(report: dict[str, Any], step: dict[str, Any]) -> list[str]:
    refs = [str(item) for item in report.get("artifacts") or [] if isinstance(item, str)]
    refs.extend(step_artifacts(step))
    return unique(refs)


def build_action_asset(app_id: str, screen_id: str, report_path: Path, report: dict[str, Any], step: dict[str, Any], index: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if step.get("status") == "failed":
        return None, {"stepId": step_id(step, index), "action": step.get("action"), "reason": "failed step"}
    if step.get("status") == "skipped" and step_data(step).get("continueOnFailure") is not True:
        return None, {"stepId": step_id(step, index), "action": step.get("action"), "reason": "skipped step"}
    workflow_step, params, risks, reason = workflow_step_from_action(step, index)
    if workflow_step is None:
        return None, {"stepId": step_id(step, index), "action": step.get("action"), "reason": reason}
    action = str(step.get("action") or "")
    asset = {
        "appId": app_id,
        "screenId": screen_id,
        "kind": action,
        "label": action_label(action, workflow_step.get(action, {}) if isinstance(workflow_step.get(action), dict) else {"text": workflow_step.get(action)}),
        "stepJson": workflow_step,
        "selectorCandidates": selector_candidates(action, workflow_step.get(action, {}) if isinstance(workflow_step.get(action), dict) else {"text": workflow_step.get(action)}),
        "params": params,
        "riskFlags": unique(risks),
        "sourceReport": str(report_path),
        "sourceStepIds": [step_id(step, index)],
        "artifactRefs": source_artifacts(report, step),
        "status": "candidate",
        "confidence": confidence_for(action, risks),
        "dedupeKey": hash_key(app_id, screen_id, action, workflow_step),
    }
    asset["actionAssetId"] = stable_id("action", asset["dedupeKey"])
    return asset, None


def workflow_goal(report: dict[str, Any], notes: str | None) -> str:
    if notes:
        return notes
    target = report.get("selectedTarget") if isinstance(report.get("selectedTarget"), dict) else {}
    title = str(target.get("title") or "Electron UI")
    return f"复用 {title} 验证流程"


def build_workflow_asset(app_id: str, report_path: Path, report: dict[str, Any], action_assets: list[dict[str, Any]], notes: str | None) -> dict[str, Any] | None:
    if report.get("status") != "passed":
        return None
    steps = [asset["stepJson"] for asset in action_assets if isinstance(asset.get("stepJson"), dict)]
    if not steps:
        return None
    params: dict[str, Any] = {}
    risk_flags: list[str] = []
    action_refs: list[str] = []
    source_step_ids: list[str] = []
    artifact_refs: list[str] = []
    for asset in action_assets:
        merge_params(params, asset.get("params") if isinstance(asset.get("params"), dict) else {})
        risk_flags.extend(asset.get("riskFlags") if isinstance(asset.get("riskFlags"), list) else [])
        action_refs.append(str(asset.get("actionAssetId")))
        source_step_ids.extend(str(item) for item in asset.get("sourceStepIds", []) if item)
        artifact_refs.extend(str(item) for item in asset.get("artifactRefs", []) if item)
    workflow = {
        "appId": app_id,
        "goal": workflow_goal(report, notes),
        "readiness": [],
        "steps": steps,
        "assertions": [{"status": report.get("status")}],
        "actionRefs": unique(action_refs),
        "params": params,
        "riskFlags": unique(risk_flags),
        "sourceReport": str(report_path),
        "sourceStepIds": unique(source_step_ids),
        "artifactRefs": unique(artifact_refs),
        "status": "candidate",
        "confidence": min([float(asset.get("confidence", 0.3)) for asset in action_assets] + [0.6]),
    }
    workflow["dedupeKey"] = hash_key(app_id, workflow["goal"], workflow["steps"], workflow["assertions"])
    workflow["workflowAssetId"] = stable_id("workflow", workflow["dedupeKey"])
    return workflow


def extract_assets(report_path: Path, app_id_override: str | None = None, notes: str | None = None) -> dict[str, Any]:
    report = read_json(report_path)
    if not isinstance(report, dict):
        raise EVError("report must be a JSON object")
    base = extract_knowledge(report_path, app_id_override=app_id_override, notes=notes)
    app = base["app"]
    screens = base.get("screens") if isinstance(base.get("screens"), list) else []
    if not screens:
        raise EVError("report did not produce a screen candidate")
    app_id = str(app["appId"])
    screen_id = str(screens[0]["screenId"])
    steps = report.get("steps") if isinstance(report.get("steps"), list) else []
    action_assets: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for index, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict):
            filtered.append({"stepId": f"step-{index + 1}", "reason": "step is not an object"})
            continue
        asset, reason = build_action_asset(app_id, screen_id, report_path, report, raw_step, index)
        if asset is not None:
            action_assets.append(asset)
        if reason is not None:
            filtered.append(reason)
    workflow = build_workflow_asset(app_id, report_path, report, action_assets, notes)
    return {
        "app": app,
        "screens": screens,
        "evidence": base.get("evidence"),
        "actionAssets": action_assets,
        "workflowAssets": [workflow] if workflow is not None else [],
        "filteredSteps": filtered,
        "stats": {
            "stepCount": len(steps),
            "actionAssetCandidates": len(action_assets),
            "workflowAssetCandidates": 1 if workflow is not None else 0,
            "filteredSteps": len(filtered),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 verifier report dry-run 整理 action/workflow 资产候选。")
    parser.add_argument("--report", required=True, help="report.json 绝对路径")
    parser.add_argument("--app-id", help="覆盖自动识别的 appId")
    parser.add_argument("--notes", help="作为 workflow goal 和 evidence notes 的简短说明")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report_path = safe_report_path(args.report)
        print_json({"ok": True, "assets": extract_assets(report_path, app_id_override=args.app_id, notes=args.notes)})
        return 0
    except EVError as exc:
        return fail(str(exc), "asset_extract_failed")


if __name__ == "__main__":
    raise SystemExit(main())
