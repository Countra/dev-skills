#!/usr/bin/env python3
"""把 approved canonical asset 转换为 verifier typed input。"""

from __future__ import annotations

import urllib.parse
from typing import Any

from ev_asset_extract import executable_from_asset
from ev_common import EVConfig, EVError, request_json


def _load(config: EVConfig, asset_id: str, kind: str) -> dict[str, Any]:
    path = "/knowledge/assets/get?" + urllib.parse.urlencode({"assetId": asset_id})
    result = request_json(config, "GET", path)
    if result.get("ok") is False:
        raise EVError(str(result.get("error") or result.get("code") or "asset 读取失败"))
    return executable_from_asset(result.get("asset"), kind)


def _usage(item: dict[str, Any]) -> dict[str, Any]:
    compatibility = item.get("compatibility") if isinstance(item.get("compatibility"), dict) else {}
    schema = item.get("parameterSchema") if isinstance(item.get("parameterSchema"), dict) else {}
    return {
        "type": f"knowledge.{item['kind']}_asset",
        "assetId": item["assetId"],
        "appId": item["appId"],
        "goal": item["goal"],
        "requiredParams": sorted(name for name, value in schema.items() if isinstance(value, dict) and value.get("required", True) is not False),
        "parameterSchema": schema,
        "risk": compatibility.get("risk", "low"),
        "preState": compatibility.get("preState"),
        "postState": compatibility.get("postState"),
    }


def load_action_asset(config: EVConfig, action_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    item = _load(config, action_id, "action")
    action = dict(item["executable"])
    usage = _usage(item)
    return action, dict(usage), usage


def load_workflow_asset(config: EVConfig, workflow_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    item = _load(config, workflow_id, "workflow")
    workflow = dict(item["executable"])
    workflow.setdefault("schemaVersion", 1)
    workflow.setdefault("appId", item["appId"])
    workflow.setdefault("goal", item["goal"])
    if item.get("parameterSchema"):
        workflow["parameterSchema"] = item["parameterSchema"]
    usage = _usage(item)
    return workflow, dict(usage), usage
