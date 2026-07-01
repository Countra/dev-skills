#!/usr/bin/env python3
"""运行知识库存储层 smoke 检查。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

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
        workflow = store.upsert_workflow(
            {
                "appId": app["app_id"],
                "goal": "打开案件详情",
                "steps": [{"clickText": "查看"}],
                "assertions": [{"waitText": "结果"}],
                "confidence": 0.7,
            }
        )
        evidence = store.add_evidence({"sourceReport": str(workspace_root / "report.json"), "artifactRefs": ["snapshot.json"], "notes": "smoke"})
        hits = store.search("案件 工具栏", app_id=app["app_id"])
        cleanup = store.cleanup(keep_inactive=20)
        return {
            "ok": bool(hits),
            "meta": store.meta(),
            "app": app["app_id"],
            "screen": screen["screen_id"],
            "element": element["element_id"],
            "workflow": workflow["workflow_id"],
            "evidence": evidence["evidence_id"],
            "hits": hits,
            "cleanup": cleanup["removed"],
        }


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
        else:
            result = run_smoke(discover_workspace_root(args.workspace))
        print_json(result)
        return 0 if result.get("ok") else 2
    except EVError as exc:
        return fail(str(exc), "knowledge_smoke_failed")


if __name__ == "__main__":
    raise SystemExit(main())
