#!/usr/bin/env python3
"""把知识库资产转换为 verifier 可执行输入。"""

from __future__ import annotations

from typing import Any

from ev_common import EVConfig, EVError
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


def usage_from_asset(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    asset_id_key = "action_asset_id" if kind == "action" else "workflow_asset_id"
    alias_key = "action_id" if kind == "action" else "workflow_id"
    asset_id = str(item.get(asset_id_key) or item.get(alias_key) or "").strip()
    if not asset_id:
        raise EVError(f"{kind} asset id is missing")
    return {
        "type": f"knowledge.{kind}_asset",
        "assetId": asset_id,
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "riskFlags": item.get("risk_flags", []),
        "sourceReport": item.get("source_report"),
    }


def load_action_asset(config: EVConfig, action_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    with open_store_from_paths(knowledge_paths_from_config(config)) as store:
        item = store.get_action_asset(action_id)
    step = item.get("step")
    if not isinstance(step, dict) or not step:
        raise EVError(f"action asset is not executable: {action_id}")
    usage = usage_from_asset("action", item)
    source = dict(usage)
    source["actionId"] = usage["assetId"]
    return step, source, usage


def load_workflow_asset(config: EVConfig, workflow_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    with open_store_from_paths(knowledge_paths_from_config(config)) as store:
        item = store.get_workflow_asset(workflow_id)
    readiness = item.get("readiness", [])
    steps = item.get("steps", [])
    assertions = item.get("assertions", [])
    if not isinstance(readiness, list) or not isinstance(steps, list) or not steps:
        raise EVError(f"workflow asset is not executable: {workflow_id}")
    if not isinstance(assertions, list):
        raise EVError(f"workflow asset assertions must be a list: {workflow_id}")
    workflow: dict[str, Any] = {
        "schemaVersion": 1,
        "appId": item.get("app_id"),
        "goal": item.get("goal"),
        "readiness": readiness,
        "steps": steps,
        "assertions": assertions,
    }
    usage = usage_from_asset("workflow", item)
    source = dict(usage)
    source["workflowId"] = usage["assetId"]
    return workflow, source, usage
