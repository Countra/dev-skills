#!/usr/bin/env python3
"""通过 Reviewer 公共 CLI 校验 managed execution review 回执。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness_review_errors import ReviewGateError
from harness_review_context import validate_managed_context
from harness_review_target import validate_managed_target
from harness_state_schema import StateError, read_events, validate_review_record
from harness_task_bundle import TaskBundle


MAX_REVIEW_BYTES = 1024 * 1024
MAX_REVIEW_FILES = 256
VALIDATOR_TIMEOUT_SECONDS = 30
SUPPORTING_REVIEW_DIRS = {
    "briefs",
    "contexts",
    "dispatches",
    "outcomes",
    "packages",
    "results",
    "targets",
}


def reviewer_validator_path() -> Path:
    skills_dir = Path(__file__).resolve().parents[2]
    return skills_dir / "complex-coding-reviewer" / "scripts" / "review_validate.py"


def _review_root(bundle: TaskBundle) -> Path:
    root = (bundle.task_dir / "artifacts" / "reviews").resolve()
    if not root.is_dir():
        raise ReviewGateError(
            "RUN_STATE_REVIEW_ROOT_MISSING",
            f"缺少 task-local review root：{root}",
        )
    return root


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > MAX_REVIEW_BYTES:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_REPORT_TOO_LARGE",
                f"review JSON 超过 {MAX_REVIEW_BYTES} bytes：{path}",
            )
        value = json.loads(path.read_text(encoding="utf-8"))
    except ReviewGateError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_REPORT_INVALID",
            f"无法读取 review JSON：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_REPORT_INVALID",
            f"review JSON 根节点必须是 object：{path}",
        )
    return value


def _resolve_report(bundle: TaskBundle, report_ref: str) -> tuple[Path, Path]:
    root = _review_root(bundle)
    try:
        report = (bundle.task_dir / report_ref).resolve(strict=True)
        report.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_REPORT_INVALID",
            f"review report 不存在或越出 artifacts/reviews：{report_ref}",
        ) from exc
    if not report.is_file():
        raise ReviewGateError(
            "RUN_STATE_REVIEW_REPORT_INVALID",
            f"review report 必须是普通文件：{report_ref}",
        )
    return root, report


def _execution_baseline(bundle: TaskBundle) -> str:
    try:
        events = read_events(bundle.ledger_path)
    except StateError as exc:
        raise ReviewGateError(exc.code, exc.message) from exc
    for event in events:
        if event.get("type") != "review_recorded":
            continue
        payload = event.get("payload")
        scope = payload.get("scope") if isinstance(payload, dict) else None
        if (
            not isinstance(scope, dict)
            or scope.get("kind") != "stage-delta"
            or payload.get("result") != "passed"
        ):
            continue
        report_ref = payload.get("report_ref")
        if not isinstance(report_ref, str):
            continue
        _, report = _resolve_report(bundle, report_ref)
        receipt = _read_json_object(report)
        target = receipt.get("target")
        identity = target.get("identity") if isinstance(target, dict) else None
        if (
            not isinstance(target, dict)
            or target.get("digest") != payload.get("target_digest")
        ):
            raise ReviewGateError(
                "RUN_STATE_REVIEW_BASELINE_INVALID",
                "stage receipt target digest 与 ledger compact evidence 不一致。",
            )
        baseline = identity.get("baseline") if isinstance(identity, dict) else None
        if isinstance(baseline, str) and len(baseline) in {40, 64}:
            return baseline
        raise ReviewGateError(
            "RUN_STATE_REVIEW_BASELINE_INVALID",
            "stage receipt 缺少可解析的 Git baseline。",
        )
    raise ReviewGateError(
        "RUN_STATE_REVIEW_BASELINE_MISSING",
        "final-integration 前缺少可解析的当前 revision stage baseline。",
    )


def _find_predecessor(
    root: Path,
    current: Path,
    supersedes_review_id: str | None,
) -> Path | None:
    if supersedes_review_id is None:
        return None
    matches: list[Path] = []
    scanned = 0
    for candidate in root.rglob("*.json"):
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if relative.parts and relative.parts[0] in SUPPORTING_REVIEW_DIRS:
            continue
        scanned += 1
        if scanned > MAX_REVIEW_FILES:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_SEARCH_LIMIT",
                f"review root 的 canonical receipt 候选超过有界上限 {MAX_REVIEW_FILES}。",
            )
        if resolved == current or not resolved.is_file():
            continue
        try:
            value = _read_json_object(resolved)
        except ReviewGateError:
            continue
        if (
            value.get("review_id") == supersedes_review_id
            and value.get("kind") is None
            and all(field in value for field in ("target", "context", "reviewer"))
        ):
            matches.append(resolved)
    if len(matches) != 1:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SUPERSEDES_INVALID",
            "supersedes_review_id 必须在 review root 中唯一解析："
            f"id={supersedes_review_id}, matches={len(matches)}",
        )
    return matches[0]


def _run_validator(
    bundle: TaskBundle,
    report: Path,
    root: Path,
    *,
    scope_kind: str,
    stage_id: str | None,
    attempt: int | None,
    predecessor: Path | None,
    dispatch_policy: str,
) -> dict[str, Any]:
    validator = reviewer_validator_path()
    if not validator.is_file():
        raise ReviewGateError(
            "RUN_STATE_REVIEW_VALIDATOR_MISSING",
            f"缺少 Reviewer 公共校验器：{validator}",
        )
    command = [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        "-B",
        str(validator),
        "--receipt",
        str(report),
        "--review-root",
        str(root),
        "--workspace",
        str(bundle.workspace),
        "--task-dir",
        str(bundle.task_dir),
        "--expected-profile",
        "code-review",
        "--expected-scope",
        scope_kind,
        "--expected-dispatch-policy",
        dispatch_policy,
    ]
    if stage_id is not None and attempt is not None:
        command.extend(
            ["--expected-stage-id", stage_id, "--expected-attempt", str(attempt)]
        )
    if predecessor is not None:
        command.extend(["--supersedes", str(predecessor)])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=VALIDATOR_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_VALIDATOR_FAILED",
            f"无法运行 Reviewer 公共校验器：{exc}",
        ) from exc
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_VALIDATOR_INVALID_OUTPUT",
            "Reviewer 公共校验器未返回合法 JSON。",
        ) from exc
    if not isinstance(envelope, dict):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_VALIDATOR_INVALID_OUTPUT",
            "Reviewer 公共校验器返回值必须是 object。",
        )
    if completed.returncode != 0 or envelope.get("ok") is not True:
        error = envelope.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            code = str(error["code"])
            message = str(error.get("message") or "Reviewer 拒绝 review receipt。")
        else:
            code = "RUN_STATE_REVIEW_VALIDATOR_REJECTED"
            message = "Reviewer 公共校验器拒绝 receipt。"
        raise ReviewGateError(code, message)
    result = envelope.get("result")
    if envelope.get("operation") != "review.validate" or not isinstance(result, dict):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_VALIDATOR_INVALID_OUTPUT",
            "Reviewer 公共校验器 envelope 不符合 review.validate 契约。",
        )
    return result


def _expected_dispatch_policy(
    bundle: TaskBundle,
    *,
    scope_kind: str,
    stage_id: str | None,
) -> str:
    if scope_kind == "final-integration":
        return "strict"
    if scope_kind != "stage-delta" or stage_id is None:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_INVALID",
            "无法为未知 review scope 推导 dispatch policy。",
        )
    stage = next(
        (
            item
            for item in bundle.contract.get("stages", [])
            if isinstance(item, dict) and item.get("id") == stage_id
        ),
        None,
    )
    if not isinstance(stage, dict) or stage.get("risk") not in {
        "low",
        "medium",
        "high",
    }:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_RISK_INVALID",
            f"stage {stage_id} 缺少合法 risk，无法推导 dispatch policy。",
        )
    return "strict" if stage["risk"] == "high" else "conditional"


def validate_review_gate(
    bundle: TaskBundle,
    payload: dict[str, Any],
    *,
    stage_id: str | None,
    attempt: int | None,
    final_commit_recorded: bool = False,
    require_lifecycle_baseline: bool = False,
) -> dict[str, Any]:
    """校验 receipt freshness，并确认 ledger compact payload 精确派生。"""

    try:
        compact = validate_review_record(
            payload,
            stage_id=stage_id,
            attempt=attempt,
        )
    except StateError as exc:
        raise ReviewGateError(exc.code, exc.message) from exc
    report_ref = str(compact["report_ref"])
    root, report = _resolve_report(bundle, report_ref)
    receipt = _read_json_object(report)
    scope_kind = str(compact["scope"]["kind"])
    expected_baseline = (
        _execution_baseline(bundle)
        if scope_kind == "final-integration" and require_lifecycle_baseline
        else None
    )
    validate_managed_target(
        bundle,
        receipt,
        scope_kind=scope_kind,
        stage_id=stage_id,
        attempt=attempt,
        final_commit_recorded=final_commit_recorded,
        expected_baseline=expected_baseline,
    )
    supersedes = receipt.get("supersedes_review_id")
    if supersedes is not None and not isinstance(supersedes, str):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SUPERSEDES_INVALID",
            "supersedes_review_id 必须是字符串或 null。",
        )
    predecessor = _find_predecessor(root, report, supersedes)
    dispatch_policy = _expected_dispatch_policy(
        bundle,
        scope_kind=scope_kind,
        stage_id=stage_id,
    )
    result = _run_validator(
        bundle,
        report,
        root,
        scope_kind=scope_kind,
        stage_id=stage_id,
        attempt=attempt,
        predecessor=predecessor,
        dispatch_policy=dispatch_policy,
    )
    try:
        events = read_events(bundle.ledger_path)
    except StateError as exc:
        raise ReviewGateError(exc.code, exc.message) from exc
    validate_managed_context(
        bundle,
        receipt,
        events,
        scope_kind=scope_kind,
        stage_id=stage_id,
        attempt=attempt,
    )
    expected = {
        "result": "passed" if result.get("verdict") == "passed" else "failed",
        "review_id": result.get("review_id"),
        "profile": result.get("profile"),
        "scope": result.get("scope"),
        "target_digest": result.get("target_digest"),
        "context_digest": result.get("context_digest"),
        "verdict": result.get("verdict"),
        "report_ref": report_ref,
        "open_counts": result.get("open_counts"),
        "gap_counts": result.get("gap_counts"),
        "coverage_summary": result.get("coverage_summary"),
        "lineage_summary": result.get("lineage_summary"),
        "strength_count": result.get("strength_count"),
        "summary": result.get("summary"),
        "reviewer_mode": result.get("reviewer_mode"),
        "independence_claim": result.get("independence_claim"),
        "dispatch_id": result.get("dispatch_id"),
    }
    if compact != expected:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_PAYLOAD_MISMATCH",
            "ledger compact payload 与 Reviewer 公共校验结果不一致。",
        )
    return expected
