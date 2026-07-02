#!/usr/bin/env python3
"""验证 report 到 action/workflow 资产整理的 smoke。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from ev_common import print_json, write_json
from ev_asset_extract import extract_assets
from ev_knowledge_store import knowledge_paths_for_state, open_store_from_paths


def fixture_report(path: Path) -> None:
    artifact = path.parent / "snapshot.json"
    write_json(
        artifact,
        {
            "title": "Mock",
            "url": "app://mock/index.html#/home",
            "text": "首页 查看 扫描结果",
            "elements": [{"text": "查看", "role": "button", "x": 10, "y": 20, "width": 60, "height": 24}],
        },
    )
    write_json(
        path,
        {
            "schemaVersion": 1,
            "generatedAt": "2026-07-02T00:00:00Z",
            "backend": "raw-cdp",
            "cdp": "http://127.0.0.1:9223",
            "version": {"Browser": "MockElectron/1.0", "User-Agent": "MockElectron/1.0"},
            "selectedTarget": {"id": "target-1", "type": "page", "title": "Mock", "url": "app://mock/index.html#/home"},
            "steps": [
                {"id": "open", "action": "clickText", "status": "passed", "artifacts": [], "data": {"text": "查看", "candidate": {"text": "查看"}}},
                {"id": "path", "action": "waitText", "status": "passed", "artifacts": [], "data": {"text": r"D:\Case\202607020001"}},
                {"id": "coord", "action": "clickXY", "status": "passed", "artifacts": [], "data": {"x": 10, "y": 20}},
                {"id": "optional", "action": "screenshot", "status": "skipped", "artifacts": [str(path.parent / "optional.png")], "data": {"continueOnFailure": True}},
                {"id": "failed", "action": "snapshot", "status": "failed", "artifacts": [], "data": {}, "error": "boom"},
                {"id": "eval", "action": "evaluate", "status": "passed", "artifacts": [], "data": {"value": 1}},
            ],
            "artifacts": [str(artifact)],
            "status": "passed",
        },
    )


def assert_assets(payload: dict[str, Any]) -> None:
    actions = payload["actionAssets"]
    workflows = payload["workflowAssets"]
    filtered = payload["filteredSteps"]
    if len(actions) != 4:
        raise AssertionError(f"expected 4 action assets, got {len(actions)}")
    if len(workflows) != 1:
        raise AssertionError(f"expected 1 workflow asset, got {len(workflows)}")
    by_kind = {item["kind"]: item for item in actions}
    if "coordinateFallback" not in by_kind["clickXY"]["riskFlags"]:
        raise AssertionError("clickXY must be marked as coordinate fallback")
    if "parameterized:localPath" not in by_kind["waitText"]["riskFlags"]:
        raise AssertionError("local path text must be parameterized")
    if not by_kind["waitText"]["params"]:
        raise AssertionError("parameterized waitText must declare params")
    if "optionalSkippedStep" not in by_kind["screenshot"]["riskFlags"]:
        raise AssertionError("optional skipped step must be marked")
    reasons = {item.get("reason") for item in filtered}
    if "failed step" not in reasons or "evaluate 不从 report 反推表达式" not in reasons:
        raise AssertionError(f"unexpected filtered reasons: {sorted(str(item) for item in reasons)}")


def run_smoke(temp_root: Path) -> dict[str, Any]:
    report_dir = temp_root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"
    fixture_report(report_path)
    payload = extract_assets(report_path, app_id_override="mockApp", notes="smoke workflow")
    assert_assets(payload)
    with open_store_from_paths(knowledge_paths_for_state(temp_root / "state"), reset=True) as store:
        store.upsert_app(payload["app"])
        for screen in payload["screens"]:
            store.upsert_screen(screen)
        evidence = store.add_evidence(payload["evidence"])
        evidence_id = str(evidence.get("evidenceId") or evidence.get("evidence_id") or "")
        for item in payload["actionAssets"]:
            item = dict(item)
            item["evidenceRefs"] = [evidence_id]
            store.upsert_action_asset(item)
        for item in payload["workflowAssets"]:
            item = dict(item)
            item["evidenceRefs"] = [evidence_id]
            store.upsert_workflow_asset(item)
        meta = store.meta()
        if meta["counts"]["actionAssets"] != 4 or meta["counts"]["workflowAssets"] != 1:
            raise AssertionError(f"unexpected store counts: {meta['counts']}")
        return {"stats": payload["stats"], "counts": meta["counts"], "filteredSteps": payload["filteredSteps"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 action/workflow 资产抽取 smoke。")
    parser.add_argument("--workspace", help="临时 workspace；未指定时自动创建")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve() / ".harness" / "electron-ui-verifier" / "tmp" / "asset-smoke"
    if not args.workspace and root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    result = run_smoke(root)
    print_json({"ok": True, "workspace": str(root), "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
