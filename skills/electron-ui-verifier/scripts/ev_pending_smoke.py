#!/usr/bin/env python3
"""验证 pending 审核包、detour 清洗和持久化门禁。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ev_common import config_from_data, print_json, write_json
from ev_pending import validate_proposed_workflow, write_pending_package
from ev_persist import approve


def config_for(root: Path):
    state = root / ".harness" / "electron-ui-verifier"
    return config_from_data(
        {
            "host": "127.0.0.1",
            "port": 18180,
            "workspaceRoot": str(root),
            "stateRoot": str(state),
            "tokenFile": str(state / "token"),
            "serverFile": str(state / "server.json"),
            "sessionsFile": str(state / "sessions.json"),
            "reportsDir": str(state / "reports"),
            "pendingDir": str(state / "pending"),
            "workflowsDir": str(state / "workflows"),
            "artifactsDir": str(state / "artifacts"),
            "logsDir": str(state / "logs"),
            "tmpDir": str(state / "tmp"),
            "portRetry": {"enabled": True, "maxSwitches": 3},
        }
    )


def fixture_report(report_path: Path) -> dict[str, Any]:
    artifact = report_path.parent / "snapshot.json"
    write_json(
        artifact,
        {
            "title": "Mock",
            "url": "app://mock/index.html#/result",
            "text": "首页 历史记录 查看 扫描结果",
            "elements": [{"text": "查看", "role": "button", "x": 10, "y": 20, "width": 60, "height": 24}],
        },
    )
    report = {
        "schemaVersion": 1,
        "generatedAt": "2026-07-02T00:00:00Z",
        "backend": "raw-cdp",
        "cdp": "http://127.0.0.1:9223",
        "appId": "mockApp",
        "goal": "打开案件详情",
        "version": {"Browser": "MockElectron/1.0", "User-Agent": "MockElectron/1.0"},
        "selectedTarget": {"id": "target-1", "type": "page", "title": "Mock", "url": "app://mock/index.html#/result"},
        "steps": [
            {"id": "open-case", "action": "clickText", "status": "passed", "artifacts": [], "data": {"text": "查看", "candidate": {"text": "查看"}}},
            {"id": "result", "action": "waitText", "status": "passed", "artifacts": [], "data": {"text": "扫描结果"}},
        ],
        "artifacts": [str(artifact)],
        "status": "passed",
    }
    write_json(report_path, report)
    return report


def fixture_workflow() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "appId": "mockApp",
        "goal": "打开案件详情",
        "steps": [
            {"id": "wrong-settings", "clickText": {"text": "设置"}, "persistence": "detour", "detourReason": "进入无关设置页"},
            {"id": "back-home", "pressKey": {"key": "Escape"}, "recoveryOnly": True, "detourReason": "从错误页面恢复"},
            {"id": "open-case", "clickText": {"text": "查看", "index": 0}},
            {"id": "result", "waitText": {"text": "扫描结果"}},
        ],
    }


class Args:
    def __init__(self, workspace: Path, pending: Path) -> None:
        self.workspace = str(workspace)
        self.config = None
        self.pending = str(pending)
        self.decision = "用户确认 smoke 正确路径"
        self.app_id = "mockApp"
        self.notes = None
        self.include_assets = True


def run_smoke(root: Path) -> dict[str, Any]:
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    config = config_for(root)
    for folder in (config.state_root, config.reports_dir, config.pending_dir, config.workflows_dir, config.artifacts_dir, config.logs_dir, config.tmp_dir):
        folder.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text("token\n", encoding="utf-8")
    write_json(
        config.state_root / "config.json",
        {
            "host": "127.0.0.1",
            "port": 18180,
            "workspaceRoot": str(root),
            "stateRoot": str(config.state_root),
            "tokenFile": str(config.token_file),
            "serverFile": str(config.server_file),
            "sessionsFile": str(config.sessions_file),
            "reportsDir": str(config.reports_dir),
            "pendingDir": str(config.pending_dir),
            "workflowsDir": str(config.workflows_dir),
            "artifactsDir": str(config.artifacts_dir),
            "logsDir": str(config.logs_dir),
            "tmpDir": str(config.tmp_dir),
            "portRetry": {"enabled": True, "maxSwitches": 3},
        },
    )
    report_dir = config.reports_dir / "mock" / "20260702-000000-workflow"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"
    summary_path = report_dir / "summary.md"
    summary_path.write_text("# summary\n", encoding="utf-8")
    report = fixture_report(report_path)
    pending = write_pending_package(config, "mock", "20260702-000000-workflow", fixture_workflow(), report, report_path, summary_path)
    proposed = validate_proposed_workflow(Path(pending["workflow"]))
    if len(proposed.get("steps", [])) != 2:
        raise AssertionError("detour steps were not removed from proposed workflow")
    flow = pending.get("flowSummary") or {}
    if "扫描结果" not in str(flow.get("text")) or "设置" in str(flow.get("text")):
        raise AssertionError("flow summary did not describe only the cleaned correct path")
    evidence = Path(pending["evidence"]).read_text(encoding="utf-8")
    if "flowSummary" not in evidence:
        raise AssertionError("evidence-index.json did not include flow summary")
    review = Path(pending["review"]).read_text(encoding="utf-8")
    if "## 步骤链路" not in review:
        raise AssertionError("workflow-review.md did not include flow summary section")
    bad_pending = Path(pending["path"]) / "bad"
    bad_pending.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(pending["workflow"]), bad_pending / "workflow.proposed.json")
    bad_workflow = proposed
    bad_workflow["steps"].append({"id": "bad", "clickText": {"text": "错误"}, "detour": True})
    write_json(bad_pending / "workflow.proposed.json", bad_workflow)
    write_json(bad_pending / "evidence-index.json", {"report": str(report_path)})
    try:
        approve(Args(root, bad_pending))
    except Exception as exc:
        guard = str(exc)
    else:
        raise AssertionError("detour approve guard did not reject bad pending package")
    approved = approve(Args(root, Path(pending["path"])))
    return {"pending": pending, "approved": approved, "guard": guard}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 pending 审核包 smoke。")
    parser.add_argument("--workspace", help="临时 workspace；未指定时使用 ignored runtime tmp")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve() / ".harness" / "electron-ui-verifier" / "tmp" / "pending-smoke"
    print_json({"ok": True, "workspace": str(root), "result": run_smoke(root)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
