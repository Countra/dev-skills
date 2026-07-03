#!/usr/bin/env python3
"""用户确认后持久化 pending 审核包。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json, resolve_config_path, write_json
from ev_learn import persist as persist_knowledge
from ev_asset_extract import extract_assets
from ev_knowledge_extract import extract_knowledge, safe_report_path
from ev_pending import approve_workflow, safe_pending_dir, validate_proposed_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="批准或拒绝 electron-ui-verifier pending 审核包。")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    approve = subparsers.add_parser("approve", help="用户确认后持久化 workflow 和知识库")
    approve.add_argument("--pending", required=True, help="pending 审核包绝对路径")
    approve.add_argument("--decision", required=True, help="用户确认说明")
    approve.add_argument("--app-id", help="覆盖学习 appId")
    approve.add_argument("--notes", help="写入 evidence 的说明；默认使用 --decision")
    approve.add_argument("--include-assets", action="store_true", help="写入 action/workflow 资产")

    reject = subparsers.add_parser("reject", help="标记 pending 审核包不持久化")
    reject.add_argument("--pending", required=True, help="pending 审核包绝对路径")
    reject.add_argument("--reason", required=True, help="拒绝或暂不保存原因")
    return parser


def report_path_from_pending(pending_dir: Path) -> Path:
    evidence_path = pending_dir / "evidence-index.json"
    if not evidence_path.exists():
        raise EVError(f"evidence-index.json does not exist: {evidence_path}")
    evidence = read_json(evidence_path)
    if not isinstance(evidence, dict):
        raise EVError("evidence-index.json must be an object")
    report = evidence.get("report")
    if not isinstance(report, str) or not report:
        raise EVError("evidence-index.json missing report path")
    return safe_report_path(report)


def approve(args: argparse.Namespace) -> dict[str, object]:
    config = load_config(resolve_config_path(args))
    pending_dir = safe_pending_dir(config, args.pending)
    validate_proposed_workflow(pending_dir / "workflow.proposed.json")
    report_path = report_path_from_pending(pending_dir)
    approved_workflow = approve_workflow(config, pending_dir)
    approved_report_path = report_path.parent / "report.approved.json"
    report = read_json(report_path)
    if not isinstance(report, dict):
        raise EVError("report.json must be an object")
    report["approvedWorkflowPath"] = str(approved_workflow)
    report["workflowPath"] = str(approved_workflow)
    report["workflowPersistenceStatus"] = "approved"
    report["knowledgeWriteback"] = {"status": "approved_for_writeback", "decision": args.decision}
    write_json(approved_report_path, report)
    notes = args.notes or args.decision
    payload = extract_knowledge(approved_report_path, app_id_override=args.app_id, notes=notes)
    assets = extract_assets(approved_report_path, app_id_override=args.app_id, notes=notes) if args.include_assets else None
    result = persist_knowledge(payload, args, assets=assets)
    record = {
        "status": "approved",
        "decision": args.decision,
        "pending": str(pending_dir),
        "report": str(report_path),
        "approvedReport": str(approved_report_path),
        "approvedWorkflow": str(approved_workflow),
        "knowledge": result,
    }
    write_json(pending_dir / "persistence.json", record)
    return {"ok": True, **record}


def reject(args: argparse.Namespace) -> dict[str, object]:
    config = load_config(resolve_config_path(args))
    pending_dir = safe_pending_dir(config, args.pending)
    record = {"status": "rejected", "reason": args.reason, "pending": str(pending_dir)}
    write_json(pending_dir / "persistence.json", record)
    return {"ok": True, **record}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "approve":
            print_json(approve(args))
        elif args.command == "reject":
            print_json(reject(args))
        else:
            raise EVError(f"unknown command: {args.command}")
        return 0
    except EVError as exc:
        return fail(str(exc), "persist_failed")


if __name__ == "__main__":
    raise SystemExit(main())
