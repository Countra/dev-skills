#!/usr/bin/env python3
"""根据本地知识库为 UI 验证目标生成候选建议。"""

from __future__ import annotations

import argparse
import re
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

SUBGOAL_KEYWORDS = [
    "设置",
    "AI设置",
    "工具箱",
    "历史记录",
    "案件",
    "详情",
    "任务列表",
    "苍穹AI本地版",
    "苍穹AI网络版",
    "苍穹AI局域网",
    "连接状态",
    "配置",
]


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


def derived_queries(goal: str, limit: int = 8) -> list[dict[str, str]]:
    text = str(goal or "").strip()
    if not text:
        return []
    queries: list[dict[str, str]] = []

    def add(query: str, reason: str) -> None:
        query = re.sub(r"\s+", " ", query).strip(" ，,。.;；:：")
        if not query or query == text:
            return
        if any(item["query"] == query for item in queries):
            return
        queries.append({"query": query, "reason": reason})

    for keyword in SUBGOAL_KEYWORDS:
        if keyword in text:
            add(keyword, "keyword")
    if "AI" in text and "设置" in text:
        add("AI设置", "compound")
        add("打开设置", "entry")
    if "AI" in text and any(keyword in text for keyword in ("状态", "配置", "供应商", "引擎", "局域网", "网络版", "本地版")):
        add("设置", "inferred-entry")
        add("AI设置", "inferred-page")
    if "状态" in text:
        add("连接状态", "assertion")
    if "配置" in text:
        add("配置", "target-object")
    parts = [part for part in re.split(r"[\s，,。.;；:：、]+", text) if len(part) >= 2]
    for part in parts:
        add(part, "token")
    return queries[: max(0, limit)]


def compact_workflow(item: dict[str, Any]) -> dict[str, Any]:
    workflow_id = item.get("workflow_id")
    return {
        "workflowId": workflow_id,
        "goal": item.get("goal"),
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "score": score_item(item),
        "preconditions": item.get("preconditions", []),
        "steps": item.get("steps", []),
        "assertions": item.get("assertions", []),
        "riskFlags": item.get("risk_flags", []),
        "params": item.get("params", {}),
        "directRun": {"command": "ev_workflow.py", "argument": "--workflow-id", "id": workflow_id} if workflow_id else None,
    }


def compact_action(item: dict[str, Any]) -> dict[str, Any]:
    action_id = item.get("action_id")
    return {
        "actionId": action_id,
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
        "directRun": {"command": "ev_action.py", "argument": "--action-id", "id": action_id} if action_id else None,
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
        "warning": "组合建议只供规划参考；单个命中资产应优先用 --action-id 复验，确需组合时再创建最小 workflow 并真实复验。",
        "steps": [item["step"] for item in reusable],
        "actionIds": [item["actionId"] for item in reusable],
        "riskFlags": sorted({flag for item in reusable for flag in item.get("riskFlags", [])}),
        "requiredParams": {key: value for item in reusable for key, value in item.get("params", {}).items()},
    }


def compact_progressive_hits(store: Any, query: str, app_id: str | None, limit: int) -> dict[str, Any]:
    raw_hits = store.search(query, app_id=app_id, limit=max(limit * 3, 10))
    workflow_ids = [hit["entity_id"] for hit in raw_hits if hit.get("kind") == "workflow"][:limit]
    action_ids = [hit["entity_id"] for hit in raw_hits if hit.get("kind") == "action"][:limit]
    element_hits = [hit for hit in raw_hits if hit.get("kind") == "element"][:limit]
    screen_hits = [hit for hit in raw_hits if hit.get("kind") == "screen"][:limit]
    workflows = [compact_workflow(store.get_workflow(entity_id)) for entity_id in workflow_ids]
    actions = [compact_action(store.get_action_asset(entity_id)) for entity_id in action_ids]
    workflows.sort(key=lambda item: item["score"], reverse=True)
    actions.sort(key=lambda item: item["score"], reverse=True)
    direct = []
    for item in workflows:
        if item.get("directRun"):
            direct.append({"kind": "workflow", "id": item["workflowId"], "score": item["score"], "status": item.get("status")})
    for item in actions:
        if item.get("directRun"):
            direct.append({"kind": "action", "id": item["actionId"], "score": item["score"], "status": item.get("status")})
    return {
        "query": query,
        "status": "hit" if raw_hits else "empty",
        "workflowHits": len(workflows),
        "actionHits": len(actions),
        "elementHits": len(element_hits),
        "screenHits": len(screen_hits),
        "directRunCandidates": direct,
        "topWorkflows": workflows[: min(3, limit)],
        "topActions": actions[: min(3, limit)],
        "topElements": element_hits[: min(3, limit)],
        "topScreens": screen_hits[: min(3, limit)],
    }


def progressive_plan(goal: str, app_id: str | None, limit: int, store: Any, root_result: dict[str, Any]) -> dict[str, Any]:
    queries = derived_queries(goal, limit=limit)
    subgoals = []
    for item in queries:
        hits = compact_progressive_hits(store, item["query"], app_id, max(1, min(5, limit)))
        hits["reason"] = item["reason"]
        subgoals.append(hits)
    has_direct_root = any(hit.get("kind") in {"workflow", "action"} for hit in root_result.get("rawHits") or [])
    has_subgoal_direct = any(item.get("directRunCandidates") for item in subgoals)
    fallback_reason = None
    if has_direct_root:
        fallback_reason = "full_goal_has_direct_candidates"
    elif has_subgoal_direct:
        fallback_reason = "full_goal_empty_but_subgoal_has_candidates"
    else:
        fallback_reason = "no_direct_or_subgoal_candidates"
    return {
        "status": "hit" if has_direct_root or has_subgoal_direct else "empty",
        "goal": goal,
        "appId": app_id,
        "derivedQueries": queries,
        "subgoals": subgoals,
        "reuseStrategy": [
            "先复用完整目标命中的 workflow/action asset。",
            "完整目标无直达命中时，按子目标复用入口、页面或前置步骤资产。",
            "子目标也不可复用时，才创建新的最小 action/workflow 并现场验证。",
        ],
        "fallbackReason": fallback_reason,
        "mustVerify": True,
    }


def preflight_summary(result: dict[str, Any]) -> dict[str, Any]:
    workflows = result.get("workflows") or []
    actions = result.get("actions") or []
    elements = result.get("elements") or []
    screens = result.get("screens") or []
    progressive = result.get("progressivePlan") if isinstance(result.get("progressivePlan"), dict) else {}
    progressive_hit = progressive.get("status") == "hit"
    has_hits = bool(workflows or actions or elements or screens or progressive_hit)
    return {
        "status": "hit" if has_hits else "empty",
        "goal": result.get("goal"),
        "appId": result.get("appId"),
        "workflowHits": len(workflows),
        "actionHits": len(actions),
        "elementHits": len(elements),
        "screenHits": len(screens),
        "progressiveStatus": progressive.get("status"),
        "progressiveFallbackReason": progressive.get("fallbackReason"),
        "rawHitCount": len(result.get("rawHits") or []),
        "topWorkflowIds": [item.get("workflowId") for item in workflows[:3] if item.get("workflowId")],
        "topActionIds": [item.get("actionId") for item in actions[:5] if item.get("actionId")],
        "recommendedNextAction": "优先直接复用命中的 workflow/action asset；完整目标无直达命中时先复用 progressivePlan 中的子目标资产" if has_hits else "未命中可复用候选，先现场探索，任务结束后等待用户确认是否持久化",
        "mustVerify": True,
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
    result = {
        "goal": goal,
        "appId": app_id,
        "advice": [
            "建议仅作为候选入口使用，不能替代真实 UI 验证。",
            "命中 workflow/action asset 时优先用 --workflow-id 或 --action-id 现场复验，不要重复生成等价文件。",
            "完整目标无直达命中时，继续查看 progressivePlan 的子目标命中，优先复用入口、页面或前置步骤。",
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
    result["progressivePlan"] = progressive_plan(goal, app_id, limit, store, result)
    result["knowledgePreflight"] = preflight_summary(result)
    return result


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
