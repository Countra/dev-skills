#!/usr/bin/env python3
"""生成并校验提交前 final review 与提交结果的确定性等价证明。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_cli import add_bundle_arguments, emit_failure, emit_success, resolve_from_args
from harness_commit_equivalence_git import (
    build_commit_target,
    compare_targets,
    resolve_commit,
)
from harness_commit_equivalence_schema import (
    CHECK_FIELDS,
    PROOF_FIELDS,
    CommitEquivalenceError,
    file_digest,
    read_json,
    resolve_task_ref,
)
from harness_state_io import write_json_atomic
from harness_state_schema import (
    StateError,
    read_events,
    validate_commit_equivalence_reference,
    validate_review_record,
)
from harness_task_bundle import TaskBundle
from harness_time import parse_rfc3339


def _validate_review_record_for_equivalence(
    bundle: TaskBundle,
    review_record: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    try:
        compact = validate_review_record(review_record, stage_id=None, attempt=None)
    except StateError as exc:
        raise CommitEquivalenceError(exc.code, exc.message) from exc
    if (
        compact["result"] != "passed"
        or compact["scope"] != {"kind": "final-integration"}
        or compact["reviewer_mode"] != "external-agent"
        or compact["independence_claim"] is not True
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
            "快速路径需要提交前已通过的 strict 独立 final review。",
        )
    report_digest = compact.get("report_digest")
    if not isinstance(report_digest, str):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
            "旧 review event 未绑定 report_digest；请使用 post-commit strict review。",
        )
    report = resolve_task_ref(
        bundle,
        str(compact["report_ref"]),
        prefix=("artifacts", "reviews"),
    )
    if file_digest(report) != report_digest:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final review receipt bytes 与 ledger report_digest 不一致。",
        )
    receipt = read_json(report, label="final review receipt")
    target = receipt.get("target")
    if (
        receipt.get("review_id") != compact["review_id"]
        or receipt.get("profile") != "code-review"
        or receipt.get("scope") != {"kind": "final-integration"}
        or not isinstance(target, dict)
        or target.get("digest") != compact["target_digest"]
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final review receipt 与 ledger compact evidence 不一致。",
        )
    _validate_strict_dispatch(bundle, receipt, compact)
    return report, receipt


def _validate_strict_dispatch(
    bundle: TaskBundle,
    receipt: dict[str, Any],
    compact: dict[str, Any],
) -> None:
    """重验 supporting dispatch，避免非 strict receipt 冒充快速路径输入。"""

    reviewer = receipt.get("reviewer")
    if not isinstance(reviewer, dict):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
            "final receipt 未绑定 supporting dispatch；请使用 post-commit strict review。",
        )
    dispatch_ref = reviewer.get("dispatch_ref")
    dispatch_digest = reviewer.get("dispatch_digest")
    if not isinstance(dispatch_ref, str) or not isinstance(dispatch_digest, str):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
            "final receipt 缺少 supporting dispatch 引用；请使用 post-commit strict review。",
        )
    dispatch_relative = Path(dispatch_ref)
    if (
        dispatch_relative.is_absolute()
        or "\\" in dispatch_ref
        or ".." in dispatch_relative.parts
        or tuple(dispatch_relative.parts[:1]) != ("dispatches",)
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final receipt 的 dispatch_ref 不是 review-root 内的 dispatches 引用。",
        )
    dispatch_path = resolve_task_ref(
        bundle,
        f"artifacts/reviews/{dispatch_ref}",
        prefix=("artifacts", "reviews", "dispatches"),
    )
    if file_digest(dispatch_path) != dispatch_digest:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final receipt 绑定的 dispatch bytes 已变化。",
        )
    dispatch = read_json(dispatch_path, label="final review dispatch")
    lifecycle = dispatch.get("lifecycle")
    close = lifecycle.get("close") if isinstance(lifecycle, dict) else None
    if (
        dispatch.get("dispatch_id") != compact["dispatch_id"]
        or dispatch.get("review_id") != compact["review_id"]
        or reviewer.get("dispatch_id") != compact["dispatch_id"]
        or reviewer.get("mode") != compact["reviewer_mode"]
        or reviewer.get("independence_claim")
        != compact["independence_claim"]
        or not isinstance(lifecycle, dict)
        or lifecycle.get("status") != "completed"
        or not isinstance(close, dict)
        or close.get("status") != "closed"
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final receipt、dispatch 与 ledger provenance 不一致或生命周期未关闭。",
        )
    if dispatch.get("policy") != "strict":
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
            "commit equivalence 只复用 strict final review。",
        )


def _next_artifact_refs(
    bundle: TaskBundle,
    review_id: str,
    commit: str,
) -> tuple[int, str, str]:
    stem = f"{review_id}-{commit[:12]}"
    for attempt in range(1, 101):
        proof_ref = f"artifacts/reviews/equivalences/{stem}-A{attempt}.json"
        target_ref = f"artifacts/reviews/targets/{stem}-commit-A{attempt}.json"
        if not (bundle.task_dir / proof_ref).exists() and not (
            bundle.task_dir / target_ref
        ).exists():
            return attempt, proof_ref, target_ref
    raise CommitEquivalenceError(
        "RUN_STATE_REVIEW_EQUIVALENCE_EXISTS",
        "同一 review/commit 已存在 100 个 equivalence attempt。",
    )


def _write_artifact(path: Path, payload: dict[str, Any], *, label: str) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            error_code="RUN_STATE_REVIEW_EQUIVALENCE_WRITE_FAILED",
            label=label,
        )
    except StateError as exc:
        raise CommitEquivalenceError(exc.code, exc.message) from exc


def create_commit_equivalence(
    bundle: TaskBundle,
    review_record: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """在 final commit 后生成 postcommit target 与封闭 proof。"""

    report, receipt = _validate_review_record_for_equivalence(bundle, review_record)
    commit = resolve_commit(bundle.workspace, "HEAD")
    precommit_target = receipt["target"]
    identity = precommit_target.get("identity")
    if not isinstance(identity, dict):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final review receipt 缺少 target identity。",
        )
    postcommit_target = build_commit_target(
        bundle,
        baseline=str(identity.get("baseline") or ""),
        commit=commit,
        paths=list(identity.get("paths") or []),
        excludes=list(identity.get("excludes") or []),
    )
    comparison = compare_targets(bundle, precommit_target, postcommit_target, commit)
    attempt, proof_ref, target_ref = _next_artifact_refs(
        bundle,
        str(review_record["review_id"]),
        commit,
    )
    target_path = bundle.task_dir / target_ref
    _write_artifact(target_path, postcommit_target, label="postcommit review target")
    receipt_ref = report.relative_to(bundle.task_dir).as_posix()
    proof = {
        "kind": "commit-equivalence-proof",
        "task_id": bundle.task_id,
        "plan_revision": bundle.plan_revision,
        "attempt": attempt,
        "review_id": review_record["review_id"],
        "receipt_ref": receipt_ref,
        "receipt_digest": review_record["report_digest"],
        "precommit_target_digest": precommit_target["digest"],
        "postcommit_target_ref": target_ref,
        "postcommit_target_digest": postcommit_target["digest"],
        "repository": ".",
        "baseline": comparison["baseline"],
        "precommit_head": comparison["precommit_head"],
        "commit": commit,
        "allowed_paths": comparison["allowed_paths"],
        "excludes": comparison["excludes"],
        "runtime_excludes": comparison["runtime_excludes"],
        "manifest_digest": comparison["manifest_digest"],
        "file_statuses": comparison["file_statuses"],
        "worktree_status": comparison["worktree_status"],
        "checks": {field: True for field in sorted(CHECK_FIELDS)},
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    proof_path = bundle.task_dir / proof_ref
    _write_artifact(proof_path, proof, label="commit equivalence proof")
    proof_digest = file_digest(proof_path)
    return {
        "proof_ref": proof_ref,
        "proof_digest": proof_digest,
        "postcommit_target_ref": target_ref,
        "postcommit_target_digest": postcommit_target["digest"],
        "commit_payload": {
            "commit": commit,
            "repository": ".",
            "review_equivalence_ref": proof_ref,
            "review_equivalence_digest": proof_digest,
        },
        "evidence_refs": [proof_ref, target_ref],
    }


def _validate_proof_header(proof: dict[str, Any], commit_payload: dict[str, Any]) -> None:
    if set(proof) != PROOF_FIELDS:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"commit equivalence proof 字段不封闭：{sorted(set(proof) ^ PROOF_FIELDS)}",
        )
    checks = proof.get("checks")
    if not isinstance(checks, dict) or set(checks) != CHECK_FIELDS or any(
        value is not True for value in checks.values()
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit equivalence checks 必须封闭且全部为 true。",
        )
    if (
        proof.get("kind") != "commit-equivalence-proof"
        or not isinstance(proof.get("attempt"), int)
        or isinstance(proof.get("attempt"), bool)
        or proof["attempt"] < 1
        or not isinstance(proof.get("created_at"), str)
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit equivalence kind、attempt 或 created_at 无效。",
        )
    try:
        parse_rfc3339(proof["created_at"])
    except ValueError as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit equivalence created_at 不是 RFC3339。",
        ) from exc
    if commit_payload.get("repository") != ".":
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit equivalence 快速路径的 repository 必须为当前 workspace（.）。",
        )


def validate_commit_equivalence(
    bundle: TaskBundle,
    review_record: dict[str, Any],
    commit_payload: dict[str, Any],
    evidence_refs: list[str],
) -> dict[str, Any]:
    """重算 proof 所有输入，拒绝 stale、篡改和非等价提交。"""

    try:
        reference = validate_commit_equivalence_reference(commit_payload)
    except StateError as exc:
        raise CommitEquivalenceError(exc.code, exc.message) from exc
    if reference is None:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
            "final commit 未引用 commit equivalence proof。",
        )
    report, receipt = _validate_review_record_for_equivalence(bundle, review_record)
    proof_ref = reference["proof_ref"]
    proof_path = resolve_task_ref(
        bundle,
        proof_ref,
        prefix=("artifacts", "reviews", "equivalences"),
    )
    if proof_ref not in evidence_refs or file_digest(proof_path) != reference["proof_digest"]:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit event 未精确绑定 proof bytes。",
        )
    proof = read_json(proof_path, label="commit equivalence proof")
    _validate_proof_header(proof, commit_payload)
    commit_value = commit_payload.get("commit")
    if not isinstance(commit_value, str):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit payload.commit 无效。",
        )
    commit = resolve_commit(bundle.workspace, commit_value)
    if resolve_commit(bundle.workspace, "HEAD") != commit:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
            "当前 HEAD 已偏离 equivalence proof 对应的 final commit。",
        )
    target_ref = proof.get("postcommit_target_ref")
    if not isinstance(target_ref, str) or target_ref not in evidence_refs:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit event 未引用 proof 绑定的 postcommit target。",
        )
    target_path = resolve_task_ref(
        bundle,
        target_ref,
        prefix=("artifacts", "reviews", "targets"),
    )
    postcommit_target = read_json(target_path, label="postcommit target")
    precommit_target = receipt.get("target")
    identity = precommit_target.get("identity") if isinstance(precommit_target, dict) else None
    if not isinstance(precommit_target, dict) or not isinstance(identity, dict):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "final receipt 缺少合法 precommit target。",
        )
    rebuilt = build_commit_target(
        bundle,
        baseline=str(identity.get("baseline") or ""),
        commit=commit,
        paths=list(identity.get("paths") or []),
        excludes=list(identity.get("excludes") or []),
    )
    if rebuilt != postcommit_target:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
            "postcommit target 已 stale 或被篡改。",
        )
    comparison = compare_targets(bundle, precommit_target, postcommit_target, commit)
    expected = {
        "kind": "commit-equivalence-proof",
        "task_id": bundle.task_id,
        "plan_revision": bundle.plan_revision,
        "attempt": proof["attempt"],
        "review_id": review_record["review_id"],
        "receipt_ref": report.relative_to(bundle.task_dir).as_posix(),
        "receipt_digest": review_record["report_digest"],
        "precommit_target_digest": precommit_target["digest"],
        "postcommit_target_ref": target_ref,
        "postcommit_target_digest": postcommit_target["digest"],
        "repository": ".",
        "baseline": comparison["baseline"],
        "precommit_head": comparison["precommit_head"],
        "commit": commit,
        "allowed_paths": comparison["allowed_paths"],
        "excludes": comparison["excludes"],
        "runtime_excludes": comparison["runtime_excludes"],
        "manifest_digest": comparison["manifest_digest"],
        "file_statuses": comparison["file_statuses"],
        "worktree_status": comparison["worktree_status"],
        "checks": {field: True for field in sorted(CHECK_FIELDS)},
        "created_at": proof["created_at"],
    }
    if proof != expected:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "commit equivalence proof 与当前 task/review/target 不一致。",
        )
    return {
        "equivalent": True,
        "review_id": review_record["review_id"],
        "commit": commit,
        "proof_ref": proof_ref,
        "proof_digest": reference["proof_digest"],
        "postcommit_target_ref": target_ref,
        "postcommit_target_digest": postcommit_target["digest"],
    }


def _latest_final_commit(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event.get("type") == "commit_recorded" and event.get("stage_id") is None
    ]
    return matches[-1] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或校验 final commit equivalence proof")
    add_bundle_arguments(parser)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("create", help="在 final commit 后生成等价证明")
    subparsers.add_parser("validate", help="校验 ledger 已记录的等价证明")
    args = parser.parse_args()
    action = f"commit equivalence {args.operation}"
    try:
        from harness_execution import replay_bundle, require_clean_snapshot

        bundle = resolve_from_args(args, require_attestation=True)
        replayed, _ = replay_bundle(bundle)
        require_clean_snapshot(bundle, replayed)
        events = read_events(bundle.ledger_path)
        if replayed.final_review is None:
            raise CommitEquivalenceError(
                "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
                "当前 ledger 缺少可绑定的 precommit final review。",
            )
        final_commit = _latest_final_commit(events)
        if args.operation == "create":
            if final_commit is not None:
                raise CommitEquivalenceError(
                    "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
                    "final commit event 已记录，不能再生成 precommit review equivalence。",
                )
            if (
                replayed.state["lifecycle"] != "in_progress"
                or replayed.state["current_stage_id"] is not None
                or replayed.state["remaining_stage_ids"]
            ):
                raise CommitEquivalenceError(
                    "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
                    "equivalence create 只能在全部 stage 完成且 final commit event 未记录时执行。",
                )
            result = create_commit_equivalence(bundle, replayed.final_review)
        else:
            if final_commit is None:
                raise CommitEquivalenceError(
                    "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
                    "ledger 尚未记录 final commit event。",
                )
            result = validate_commit_equivalence(
                bundle,
                replayed.final_review,
                final_commit["payload"],
                final_commit["evidence_refs"],
            )
    except Exception as exc:  # noqa: BLE001 - CLI 统一转换为稳定诊断
        emit_failure(action, exc, args.output_format)
        return 1
    emit_success(action, result, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
