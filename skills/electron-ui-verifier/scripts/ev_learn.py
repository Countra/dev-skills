#!/usr/bin/env python3
"""从 verifier report 学习应用 UI 知识。"""

from __future__ import annotations

import argparse

from pathlib import Path

from ev_common import EVError, add_common_args, fail, load_config, paths_for_workspace, print_json, read_json, resolve_config_path
from ev_asset_extract import extract_assets
from ev_knowledge_extract import extract_knowledge, safe_report_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


def evidence_id(item: dict[str, object]) -> str:
    value = str(item.get("evidenceId") or item.get("evidence_id") or "")
    if not value:
        raise EVError("evidence id is missing after store write")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 Electron verifier report 抽取并写入候选知识。")
    add_common_args(parser)
    parser.add_argument("--report", help="report.json 绝对路径")
    parser.add_argument("--session", help="配合 --latest 读取 session 最新 report")
    parser.add_argument("--latest", action="store_true", help="从 sessions.json 查找指定 session 最新 report")
    parser.add_argument("--app-id", help="覆盖自动识别的 appId")
    parser.add_argument("--notes", help="写入 evidence 的简短说明")
    parser.add_argument("--dry-run", action="store_true", help="只输出候选知识，不写入知识库")
    parser.add_argument("--include-assets", action="store_true", help="显式写入 action/workflow 资产候选")
    return parser


def latest_report_for_session(args: argparse.Namespace) -> Path:
    if not args.session:
        raise EVError("--latest requires --session")
    workspace_root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    sessions_file = paths_for_workspace(workspace_root).sessions_file
    data = read_json(sessions_file)
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, list):
        raise EVError(f"sessions file has no sessions list: {sessions_file}")
    for item in sessions:
        if not isinstance(item, dict):
            continue
        if args.session in {item.get("name"), item.get("sessionId")}:
            latest = item.get("latestReport")
            if not isinstance(latest, str) or not latest:
                raise EVError(f"session has no latestReport: {args.session}")
            return safe_report_path(latest)
    raise EVError(f"session not found: {args.session}")


def persist(payload: dict[str, object], config_path_args: argparse.Namespace, assets: dict[str, object] | None = None) -> dict[str, object]:
    config = load_config(resolve_config_path(config_path_args))
    with open_store_from_paths(knowledge_paths_from_config(config)) as store:
        app = store.upsert_app(payload["app"])  # type: ignore[arg-type]
        screens = [store.upsert_screen(item) for item in payload.get("screens", [])]  # type: ignore[arg-type]
        elements = [store.upsert_element(item) for item in payload.get("elements", [])]  # type: ignore[arg-type]
        evidence = store.add_evidence(payload["evidence"])  # type: ignore[arg-type]
        action_assets: list[dict[str, object]] = []
        workflow_assets: list[dict[str, object]] = []
        if assets:
            for item in assets.get("actionAssets", []):  # type: ignore[union-attr]
                item = dict(item)  # type: ignore[arg-type]
                item["evidenceRefs"] = [evidence_id(evidence)]
                action_assets.append(store.upsert_action_asset(item))
            for item in assets.get("workflowAssets", []):  # type: ignore[union-attr]
                item = dict(item)  # type: ignore[arg-type]
                item["evidenceRefs"] = [evidence_id(evidence)]
                workflow_assets.append(store.upsert_workflow_asset(item))
        return {
            "app": app,
            "screens": screens,
            "elements": elements,
            "workflows": [],
            "actionAssets": action_assets,
            "workflowAssets": workflow_assets,
            "evidence": evidence,
            "meta": store.meta(),
        }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.latest:
            report_path = latest_report_for_session(args)
        elif args.report:
            report_path = safe_report_path(args.report)
        else:
            raise EVError("use --report <abs-report> or --latest --session <name>")
        payload = extract_knowledge(report_path, app_id_override=args.app_id, notes=args.notes)
        payload["workflows"] = []
        assets = extract_assets(report_path, app_id_override=args.app_id, notes=args.notes) if args.include_assets else None
        if args.dry_run:
            print_json({"ok": True, "dryRun": True, "knowledge": payload, "assets": assets})
            return 0
        result = persist(payload, args, assets=assets)
        stats = dict(payload.get("stats") or {})
        if assets:
            stats["assets"] = assets.get("stats")
        print_json({"ok": True, "dryRun": False, "result": result, "stats": stats})
        return 0
    except EVError as exc:
        return fail(str(exc), "learn_failed")


if __name__ == "__main__":
    raise SystemExit(main())
