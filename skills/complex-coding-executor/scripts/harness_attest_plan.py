#!/usr/bin/env python3
"""写入/校验批准证明，并管理 plan amendment revision。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from harness_amendment import (
    AmendmentError,
    activate_amendment,
    archive_current_revision,
    revision_archive_dir,
    validate_archive,
)
from harness_attestation import (
    build_attestation,
    load_attestation,
    validate_attestation,
    write_attestation,
)
from harness_cli import (
    CliInputError,
    add_bundle_arguments,
    emit_failure,
    emit_success,
    resolve_from_args,
)
from harness_execution import run_planner_approval_check


def attestation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": payload["task_id"],
        "plan_revision": payload["plan_revision"],
        "approved_at": payload["approved_at"],
        "approved_by": payload["approved_by"],
        "approval_summary": payload["approval_summary"],
        "authorizations": payload["authorizations"],
        "immutable_file_count": len(payload["immutable_files"]),
    }


def ensure_attestation_write_allowed(bundle: Any) -> None:
    if bundle.attestation_path.is_file():
        existing = load_attestation(bundle.attestation_path)
        if existing.get("task_id") != bundle.task_id:
            raise AmendmentError(
                "ATTESTATION_TASK_MISMATCH",
                "现有 attestation.task_id 与当前 contract 不一致。",
            )
        existing_revision = existing.get("plan_revision")
        if existing_revision == bundle.plan_revision:
            raise AmendmentError(
                "ATTESTATION_ALREADY_EXISTS",
                "同一 plan revision 的 attestation 不可覆盖；授权变化必须进入 amendment。",
            )
        if existing_revision != bundle.plan_revision - 1:
            raise AmendmentError(
                "ATTESTATION_REVISION_MISMATCH",
                "现有 attestation 必须属于紧邻的上一 plan revision。",
            )

    if bundle.plan_revision == 1:
        if bundle.ledger_path.exists() or bundle.run_state_path.exists():
            raise AmendmentError(
                "ATTESTATION_RUNTIME_ALREADY_EXISTS",
                "已有运行状态时不能重建初始 attestation。",
            )
        return

    archive_root = revision_archive_dir(bundle, bundle.plan_revision - 1)
    manifest = validate_archive(bundle, archive_root)
    if manifest.get("plan_revision") != bundle.plan_revision - 1:
        raise AmendmentError(
            "AMENDMENT_REVISION_INVALID",
            "新 attestation 缺少紧邻上一 revision 的有效归档。",
        )


def write_mode(bundle: Any, args: argparse.Namespace) -> dict[str, Any]:
    run_planner_approval_check(bundle)
    ensure_attestation_write_allowed(bundle)
    payload = build_attestation(
        bundle,
        approved_by=args.approved_by or "",
        approval_summary=args.approval_summary or "",
        commit_authorized=args.commit_authorized,
        external_write_authorized=args.external_write_authorized,
        elevated_tool_authorized=args.elevated_tool_authorized,
        approved_at=args.approved_at,
    )
    validate_attestation(bundle, payload)
    write_attestation(bundle.attestation_path, payload)
    return attestation_summary(payload)


def activate_mode(bundle: Any, args: argparse.Namespace) -> dict[str, Any]:
    if not args.archive_dir:
        raise CliInputError("activate-amendment 必须提供 --archive-dir。")
    run_planner_approval_check(bundle)
    archive_root = Path(args.archive_dir)
    if not archive_root.is_absolute():
        archive_root = bundle.task_dir / archive_root
    return activate_amendment(
        bundle,
        archive_root.resolve(),
        carried_completed_stage_ids=args.carry_stage,
        occurred_at=args.occurred_at,
    )


def run_mode(bundle: Any, args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "write":
        return write_mode(bundle, args)
    if args.mode == "check":
        return attestation_summary(validate_attestation(bundle))
    if args.mode == "archive":
        return archive_current_revision(bundle)
    return activate_mode(bundle, args)


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 task bundle 批准与 amendment")
    add_bundle_arguments(parser)
    parser.add_argument(
        "--mode",
        choices=["write", "check", "archive", "activate-amendment"],
        required=True,
    )
    parser.add_argument("--approved-by")
    parser.add_argument("--approval-summary")
    parser.add_argument("--approved-at", help="可选 RFC3339 批准时间")
    parser.add_argument("--commit-authorized", action="store_true")
    parser.add_argument("--external-write-authorized", action="store_true")
    parser.add_argument("--elevated-tool-authorized", action="store_true")
    parser.add_argument("--archive-dir", help="task-dir 内的上一 revision 归档目录")
    parser.add_argument("--carry-stage", action="append", default=[])
    parser.add_argument("--occurred-at", help="amendment event 的 RFC3339 时间")
    args = parser.parse_args()
    action = f"attestation {args.mode}"
    try:
        require_attestation = args.mode in {"check", "archive", "activate-amendment"}
        bundle = resolve_from_args(args, require_attestation=require_attestation)
        result = run_mode(bundle, args)
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
