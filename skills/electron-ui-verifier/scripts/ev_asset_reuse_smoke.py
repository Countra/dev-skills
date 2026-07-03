#!/usr/bin/env python3
"""验证 action/workflow asset ID 复用路径。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ev_asset_runner import load_action_asset, load_workflow_asset
from ev_assets import result_summary
from ev_common import EVConfig, print_json, write_json
from ev_knowledge_store import knowledge_paths_for_state, open_store_from_paths
from ev_suggest import suggest


def build_config(root: Path) -> EVConfig:
    state = root / "state"
    return EVConfig(
        host="127.0.0.1",
        port=18180,
        port_retry_enabled=True,
        port_retry_max_switches=3,
        workspace_root=root,
        state_root=state,
        token_file=state / "token",
        server_file=state / "server.json",
        sessions_file=state / "sessions.json",
        reports_dir=state / "reports",
        pending_dir=state / "pending",
        workflows_dir=state / "workflows",
        artifacts_dir=state / "artifacts",
        logs_dir=state / "logs",
        tmp_dir=state / "tmp",
    )


def run_smoke(root: Path) -> dict[str, object]:
    config = build_config(root)
    paths = knowledge_paths_for_state(config.state_root)
    with open_store_from_paths(paths, reset=True) as store:
        store.upsert_app({"appId": "asset-smoke", "displayName": "Asset Smoke"})
        action = store.upsert_action_asset(
            {
                "appId": "asset-smoke",
                "kind": "clickText",
                "label": "打开设置",
                "stepJson": {"clickText": {"text": "设置"}},
                "status": "verified",
                "confidence": 0.9,
            }
        )
        workflow = store.upsert_workflow_asset(
            {
                "appId": "asset-smoke",
                "goal": "打开设置页",
                "readiness": [{"waitText": "首页"}],
                "steps": [{"clickText": {"text": "设置"}}, {"snapshot": True}],
                "assertions": [{"waitText": "设置"}],
                "actionRefs": [action["action_asset_id"]],
                "status": "verified",
                "confidence": 0.85,
            }
        )
        summary = result_summary([action, workflow])
        suggestion = suggest("打开设置页", "asset-smoke", 5, store)
    step, action_source, action_usage = load_action_asset(config, action["action_asset_id"])
    workflow_doc, workflow_source, workflow_usage = load_workflow_asset(config, workflow["workflow_asset_id"])
    if step.get("clickText", {}).get("text") != "设置":
        raise AssertionError("action asset step was not loaded")
    if workflow_doc.get("steps", [])[0].get("clickText", {}).get("text") != "设置":
        raise AssertionError("workflow asset steps were not loaded")
    if action_source.get("type") != "knowledge.action_asset" or workflow_source.get("type") != "knowledge.workflow_asset":
        raise AssertionError("asset source type is not auditable")
    if action_usage.get("assetId") != action["action_asset_id"] or workflow_usage.get("assetId") != workflow["workflow_asset_id"]:
        raise AssertionError("knowledge usage did not preserve asset id")
    if summary.get("reusableCount") != 2 or "--workflow-id" not in str(summary.get("directRunHint")):
        raise AssertionError("asset summary does not expose direct run hint")
    if not suggestion["workflows"] or suggestion["workflows"][0].get("directRun", {}).get("argument") != "--workflow-id":
        raise AssertionError("suggestion workflow does not expose direct run metadata")
    if not suggestion["actions"] or suggestion["actions"][0].get("directRun", {}).get("argument") != "--action-id":
        raise AssertionError("suggestion action does not expose direct run metadata")
    return {
        "actionSource": action_source,
        "workflowSource": workflow_source,
        "workflowStepCount": len(workflow_doc["steps"]),
        "directRunHint": summary["directRunHint"],
        "db": str(paths.db_file),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 asset ID 复用 smoke。")
    parser.add_argument("--workspace", help="临时 workspace；未指定时使用 ignored runtime tmp")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve() / ".harness" / "electron-ui-verifier" / "tmp" / "asset-reuse-smoke"
    if not args.workspace and root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "marker.json", {"purpose": "asset reuse smoke"})
    print_json({"ok": True, "workspace": str(root), "result": run_smoke(root)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
