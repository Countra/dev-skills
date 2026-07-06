#!/usr/bin/env python3
"""运行知识库存储层 smoke 检查。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
import sqlite3

from ev_common import EVError, add_common_args, discover_workspace_root, fail, paths_for_workspace, print_json
from ev_knowledge_store import KnowledgePaths, knowledge_paths_from_ev_paths, open_store_from_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="验证 electron-ui-verifier 知识库存储层。")
    add_common_args(parser)
    parser.add_argument("--temp", action="store_true", help="使用当前 workspace 的 ignored runtime tmp 目录")
    return parser


def run_smoke(workspace_root: Path) -> dict[str, object]:
    ev_paths = paths_for_workspace(workspace_root)
    return run_smoke_with_paths(knowledge_paths_from_ev_paths(ev_paths), workspace_root)


def run_smoke_with_paths(knowledge_paths: KnowledgePaths, workspace_root: Path) -> dict[str, object]:
    with open_store_from_paths(knowledge_paths) as store:
        app = store.upsert_app({"appId": "demo-app", "displayName": "Demo App", "productName": "Demo"})
        screen = store.upsert_screen(
            {
                "appId": app["app_id"],
                "route": "#/home",
                "title": "Home",
                "summary": "首页包含案件列表和工具栏",
                "keyTexts": ["案件", "工具栏", "查看"],
            }
        )
        element = store.upsert_element(
            {
                "appId": app["app_id"],
                "screenId": screen["screen_id"],
                "name": "查看",
                "role": "button",
                "text": "查看",
                "selectorCandidates": [{"type": "text", "value": "查看"}],
                "anchors": ["案件列表"],
                "confidence": 0.8,
            }
        )
        action = store.upsert_action_asset(
            {
                "appId": app["app_id"],
                "screenId": screen["screen_id"],
                "kind": "clickText",
                "label": "点击查看",
                "stepJson": {"clickText": {"text": "查看", "index": 0}},
                "selectorCandidates": [{"type": "text", "value": "查看"}],
                "confidence": 0.8,
                "status": "candidate",
                "sourceStepIds": ["step-1"],
            }
        )
        action_again = store.upsert_action_asset(
            {
                "appId": app["app_id"],
                "screenId": screen["screen_id"],
                "kind": "clickText",
                "label": "点击查看",
                "stepJson": {"clickText": {"text": "查看", "index": 0}},
                "selectorCandidates": [{"type": "text", "value": "查看"}],
                "confidence": 0.8,
                "status": "candidate",
                "sourceStepIds": ["step-1"],
            }
        )
        workflow = store.upsert_workflow_asset(
            {
                "appId": app["app_id"],
                "goal": "打开案件详情",
                "readiness": [{"waitText": "案件"}],
                "steps": [{"clickText": {"text": "查看", "index": 0}}],
                "assertions": [{"waitText": "结果"}],
                "actionRefs": [action["action_asset_id"]],
                "confidence": 0.7,
            }
        )
        evidence = store.add_evidence({"sourceReport": str(workspace_root / "report.json"), "artifactRefs": ["snapshot.json"], "notes": "smoke"})
        hits = store.search("案件 工具栏", app_id=app["app_id"])
        cleanup_dry = store.cleanup(keep_inactive=20, dry_run=True)
        cleanup = store.cleanup(keep_inactive=20)
        if action["action_asset_id"] != action_again["action_asset_id"] or int(action_again.get("seen_count", 0)) < 2:
            raise EVError("action asset dedupe failed")
        return {
            "ok": bool(hits),
            "meta": store.meta(),
            "app": app["app_id"],
            "screen": screen["screen_id"],
            "element": element["element_id"],
            "actionAsset": action["action_asset_id"],
            "workflowAsset": workflow["workflow_asset_id"],
            "evidence": evidence["evidence_id"],
            "hits": hits,
            "cleanupDryRun": cleanup_dry["removed"],
            "cleanup": cleanup["removed"],
        }


def run_old_schema_guard(knowledge_paths: KnowledgePaths) -> dict[str, object]:
    knowledge_paths.root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(knowledge_paths.db_file))
    try:
        conn.executescript(
            """
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta(key, value) VALUES('schemaVersion', '1');
            CREATE TABLE workflows(workflow_id TEXT PRIMARY KEY);
            """
        )
        conn.commit()
    finally:
        conn.close()
    try:
        open_store_from_paths(knowledge_paths).close()
    except EVError as exc:
        rejected = "not migrated automatically" in str(exc)
    else:
        raise EVError("old schema should be rejected without explicit reset")
    with open_store_from_paths(knowledge_paths, reset=True) as store:
        meta = store.meta()
    return {"rejected": rejected, "resetSchemaVersion": meta["schemaVersion"]}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.temp:
            base = discover_workspace_root(args.workspace)
            stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
            temp_root = base / ".harness" / "electron-ui-verifier" / "tmp" / f"ev-knowledge-{stamp}"
            knowledge_paths = KnowledgePaths(
                root=temp_root / "knowledge",
                db_file=temp_root / "knowledge" / "knowledge.sqlite",
                manifest_file=temp_root / "knowledge" / "manifest.json",
            )
            result = run_smoke_with_paths(knowledge_paths, temp_root)
            old_schema_paths = KnowledgePaths(
                root=temp_root / "old-schema-knowledge",
                db_file=temp_root / "old-schema-knowledge" / "knowledge.sqlite",
                manifest_file=temp_root / "old-schema-knowledge" / "manifest.json",
            )
            result["oldSchemaGuard"] = run_old_schema_guard(old_schema_paths)
        else:
            result = run_smoke(discover_workspace_root(args.workspace))
        print_json(result)
        return 0 if result.get("ok") else 2
    except EVError as exc:
        return fail(str(exc), "knowledge_smoke_failed")


if __name__ == "__main__":
    raise SystemExit(main())
