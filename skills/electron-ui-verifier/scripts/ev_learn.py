#!/usr/bin/env python3
"""从 verifier report 学习应用 UI 知识。"""

from __future__ import annotations

import argparse

from pathlib import Path

from ev_common import EVError, add_common_args, fail, load_config, paths_for_workspace, print_json, read_json, resolve_config_path
from ev_knowledge_extract import extract_knowledge, safe_report_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 Electron verifier report 抽取并写入候选知识。")
    add_common_args(parser)
    parser.add_argument("--report", help="report.json 绝对路径")
    parser.add_argument("--session", help="配合 --latest 读取 session 最新 report")
    parser.add_argument("--latest", action="store_true", help="从 sessions.json 查找指定 session 最新 report")
    parser.add_argument("--app-id", help="覆盖自动识别的 appId")
    parser.add_argument("--notes", help="写入 evidence 的简短说明")
    parser.add_argument("--dry-run", action="store_true", help="只输出候选知识，不写入知识库")
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


def persist(payload: dict[str, object], config_path_args: argparse.Namespace) -> dict[str, object]:
    config = load_config(resolve_config_path(config_path_args))
    with open_store_from_paths(knowledge_paths_from_config(config)) as store:
        app = store.upsert_app(payload["app"])  # type: ignore[arg-type]
        screens = [store.upsert_screen(item) for item in payload.get("screens", [])]  # type: ignore[arg-type]
        elements = [store.upsert_element(item) for item in payload.get("elements", [])]  # type: ignore[arg-type]
        workflows = [store.upsert_workflow(item) for item in payload.get("workflows", [])]  # type: ignore[arg-type]
        evidence = store.add_evidence(payload["evidence"])  # type: ignore[arg-type]
        return {
            "app": app,
            "screens": screens,
            "elements": elements,
            "workflows": workflows,
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
        if args.dry_run:
            print_json({"ok": True, "dryRun": True, "knowledge": payload})
            return 0
        result = persist(payload, args)
        print_json({"ok": True, "dryRun": False, "result": result, "stats": payload.get("stats")})
        return 0
    except EVError as exc:
        return fail(str(exc), "learn_failed")


if __name__ == "__main__":
    raise SystemExit(main())
