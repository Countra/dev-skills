#!/usr/bin/env python3
"""根据本地知识库为 UI 验证目标生成候选建议。"""

from __future__ import annotations

import argparse
from typing import Any

from ev_common import EVError, add_common_args, fail, load_config, print_json, resolve_config_path
from ev_knowledge_extract import extract_knowledge, safe_report_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


STATUS_WEIGHT = {
    "stable": 1.0,
    "verified": 0.85,
    "candidate": 0.55,
    "observed": 0.35,
    "stale": 0.15,
    "deprecated": 0.0,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从知识库生成 Electron UI 验证建议。")
    add_common_args(parser)
    parser.add_argument("--goal", required=True, help="当前 UI 验证目标")
    parser.add_argument("--app-id", help="限定应用 ID")
    parser.add_argument("--current-report", help="当前 report.json 绝对路径，用于补充页面上下文")
    parser.add_argument("--limit", type=int, default=5)
    return parser


def score_item(item: dict[str, Any]) -> float:
    base = STATUS_WEIGHT.get(str(item.get("status") or "observed"), 0.2)
    confidence = float(item.get("confidence", 0.4) or 0.4)
    return round(max(0.0, min(1.0, (base * 0.7) + (confidence * 0.3))), 3)


def compact_workflow(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflowId": item.get("workflow_id"),
        "goal": item.get("goal"),
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "score": score_item(item),
        "preconditions": item.get("preconditions", []),
        "steps": item.get("steps", []),
        "assertions": item.get("assertions", []),
        "riskFlags": item.get("risk_flags", []),
        "params": item.get("params", {}),
    }


def compact_action(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "actionId": item.get("action_id"),
        "screenId": item.get("screen_id"),
        "kind": item.get("kind"),
        "label": item.get("label"),
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "score": score_item(item),
        "step": item.get("step", {}),
        "selectorCandidates": item.get("selector_candidates", []),
        "riskFlags": item.get("risk_flags", []),
        "params": item.get("params", {}),
    }


def compact_element(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "elementId": item.get("element_id"),
        "screenId": item.get("screen_id"),
        "name": item.get("name"),
        "role": item.get("role"),
        "text": item.get("text"),
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "score": score_item(item),
        "selectorCandidates": item.get("selectors", []),
        "anchors": item.get("anchors", []),
    }


def current_report_context(report: str | None, app_id: str | None) -> dict[str, Any] | None:
    if not report:
        return None
    payload = extract_knowledge(safe_report_path(report), app_id_override=app_id, notes="suggest current report context")
    return {
        "app": payload.get("app"),
        "screens": payload.get("screens", []),
        "elements": payload.get("elements", []),
        "workflows": payload.get("workflows", []),
        "stats": payload.get("stats", {}),
    }


def compose_candidate(actions: list[dict[str, Any]], limit: int) -> dict[str, Any] | None:
    reusable = [item for item in actions if item.get("step") and item.get("kind") != "clickXY"]
    reusable = sorted(reusable, key=lambda item: item["score"], reverse=True)[: min(limit, 5)]
    if len(reusable) < 2:
        return None
    return {
        "goal": "由高分 action 资产组合的候选 workflow",
        "status": "candidate",
        "warning": "组合建议只供规划参考，必须导出或手写 workflow 后真实复验。",
        "steps": [item["step"] for item in reusable],
        "actionIds": [item["actionId"] for item in reusable],
        "riskFlags": sorted({flag for item in reusable for flag in item.get("riskFlags", [])}),
        "requiredParams": {key: value for item in reusable for key, value in item.get("params", {}).items()},
    }


def supplemental_actions(store: Any, app_id: str | None, limit: int, known_ids: set[str]) -> list[dict[str, Any]]:
    if not app_id:
        return []
    items = store.list_items("action_assets", app_id=app_id, limit=max(limit * 4, limit))
    result = []
    for item in items:
        action_id = str(item.get("action_id") or item.get("action_asset_id") or "")
        if not action_id or action_id in known_ids:
            continue
        result.append(compact_action(item))
        if len(result) >= limit:
            break
    return result


def suggest(goal: str, app_id: str | None, limit: int, store: Any, report: str | None = None) -> dict[str, Any]:
    limit = max(1, min(20, int(limit)))
    raw_hits = store.search(goal, app_id=app_id, limit=max(limit * 4, 20))
    workflow_ids = [hit["entity_id"] for hit in raw_hits if hit.get("kind") == "workflow"]
    action_ids = [hit["entity_id"] for hit in raw_hits if hit.get("kind") == "action"]
    element_ids = [hit["entity_id"] for hit in raw_hits if hit.get("kind") == "element"]
    screen_hits = [hit for hit in raw_hits if hit.get("kind") == "screen"][:limit]
    workflows = [compact_workflow(store.get_workflow(entity_id)) for entity_id in workflow_ids[:limit]]
    actions = [compact_action(store.get_action_asset(entity_id)) for entity_id in action_ids[:limit]]
    known_action_ids = {str(item.get("actionId")) for item in actions if item.get("actionId")}
    if len(actions) < limit:
        actions.extend(supplemental_actions(store, app_id, limit - len(actions), known_action_ids))
    elements = [compact_element(store.get_element(entity_id)) for entity_id in element_ids[:limit]]
    workflows.sort(key=lambda item: item["score"], reverse=True)
    actions.sort(key=lambda item: item["score"], reverse=True)
    elements.sort(key=lambda item: item["score"], reverse=True)
    composed = compose_candidate(actions, limit)
    return {
        "goal": goal,
        "appId": app_id,
        "advice": [
            "建议仅作为候选入口使用，不能替代真实 UI 验证。",
            "candidate/observed 知识需要通过 action 或 workflow 复验后再提升状态。",
        ],
        "workflows": workflows[:limit],
        "actions": actions[:limit],
        "composedWorkflow": composed,
        "elements": elements[:limit],
        "screens": screen_hits,
        "rawHits": raw_hits[:limit],
        "currentReportContext": current_report_context(report, app_id),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        with open_store_from_paths(knowledge_paths_from_config(config)) as store:
            result = suggest(args.goal, args.app_id, args.limit, store, report=args.current_report)
        print_json({"ok": True, "result": result})
        return 0
    except EVError as exc:
        return fail(str(exc), "suggest_failed")


if __name__ == "__main__":
    raise SystemExit(main())
