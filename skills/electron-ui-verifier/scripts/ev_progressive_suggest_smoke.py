#!/usr/bin/env python3
"""验证渐进式知识建议能命中子目标资产。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ev_asset_reuse_smoke import build_config
from ev_common import print_json
from ev_knowledge_store import knowledge_paths_for_state, open_store_from_paths
from ev_suggest import suggest


def run_smoke(root: Path) -> dict[str, object]:
    config = build_config(root)
    paths = knowledge_paths_for_state(config.state_root)
    with open_store_from_paths(paths, reset=True) as store:
        store.upsert_app({"appId": "progressive-smoke", "displayName": "Progressive Smoke"})
        action = store.upsert_action_asset(
            {
                "appId": "progressive-smoke",
                "kind": "clickText",
                "label": "打开设置",
                "stepJson": {"clickText": {"text": "设置"}},
                "status": "verified",
                "confidence": 0.9,
            }
        )
        result = suggest("检查苍穹AI局域网连接状态", "progressive-smoke", 5, store)
    plan = result.get("progressivePlan") or {}
    subgoals = plan.get("subgoals") or []
    setting_hit = next((item for item in subgoals if item.get("query") == "设置"), None)
    if not setting_hit:
        raise AssertionError("progressive plan did not derive 设置 query")
    if not setting_hit.get("directRunCandidates"):
        raise AssertionError("progressive subgoal did not expose reusable asset")
    if result.get("knowledgePreflight", {}).get("status") != "hit":
        raise AssertionError("preflight summary did not see progressive hit")
    return {
        "actionId": action["action_asset_id"],
        "progressiveStatus": plan.get("status"),
        "fallbackReason": plan.get("fallbackReason"),
        "settingCandidates": setting_hit.get("directRunCandidates"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行渐进式建议 smoke。")
    parser.add_argument("--workspace", help="临时 workspace；未指定时使用 ignored runtime tmp")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve() / ".harness" / "electron-ui-verifier" / "tmp" / "progressive-suggest-smoke"
    if not args.workspace and root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    print_json({"ok": True, "workspace": str(root), "result": run_smoke(root)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
