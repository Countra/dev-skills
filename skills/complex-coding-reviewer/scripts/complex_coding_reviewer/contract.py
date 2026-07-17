"""Canonical review receipt 的封闭结构与门禁语义。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import (
    load_context_brief,
    validate_context_target_shape,
    verify_context_freshness,
)
from .coverage import coverage_summary, validate_coverage
from .errors import ReviewError
from .review_parts import (
    _evidence_refs,
    derive_gap_counts,
    derive_open_counts,
    expected_verdict,
    validate_findings,
    validate_gaps,
    validate_lineage,
    validate_open_counts,
    validate_strengths,
)
from .target import validate_target_shape, verify_target_freshness


ROOT_FIELDS = {
    "review_id",
    "profile",
    "scope",
    "target",
    "context",
    "reviewer",
    "standards",
    "coverage",
    "lenses",
    "strengths",
    "findings",
    "verification_gaps",
    "verdict",
    "open_counts",
    "summary",
    "limitations",
    "supersedes_review_id",
    "reviewed_at",
}
REVIEWER_FIELDS = {"mode", "identity", "independence_claim", "capability_limits"}
STANDARD_FIELDS = {"id", "title", "source", "applicability"}
LENS_FIELDS = {"id", "status", "evidence_refs", "summary"}

PLAN_LENSES = (
    "PLAN-INTENT",
    "PLAN-TRACEABILITY",
    "PLAN-EVIDENCE",
    "PLAN-OPTIONS",
    "PLAN-ARCHITECTURE",
    "PLAN-EXECUTION",
    "PLAN-VALIDATION",
    "PLAN-GOVERNANCE",
    "PLAN-SIMPLICITY",
)
CODE_LENSES = (
    "CODE-CORRECTNESS",
    "CODE-BOUNDARIES",
    "CODE-ARCHITECTURE",
    "CODE-RISK",
    "CODE-TESTS",
    "CODE-DELIVERY",
    "CODE-SCOPE",
)

PROFILES = {"plan-review", "code-review"}
PROVENANCE_MODES = {"same-context", "fresh-context", "external-agent", "human"}
LENS_STATUSES = {"reviewed", "not-applicable", "blocked"}
VERDICTS = {"passed", "changes_required", "blocked"}
REVIEW_ID = re.compile(r"^REV-[A-Z0-9][A-Z0-9._-]{2,127}$")


def _closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "值必须是 object。", path=path)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ReviewError(
            "REVIEW_CONTRACT_FIELDS_INVALID",
            f"unknown={unknown}, missing={missing}",
            path=path,
        )
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError("REVIEW_CONTRACT_VALUE_INVALID", "值必须是非空字符串。", path=path)
    if "REPLACE-ME" in value or value.startswith("REV-TEMPLATE"):
        raise ReviewError("REVIEW_CONTRACT_PLACEHOLDER", "模板占位值必须在审查前替换。", path=path)
    return value


def _string_list(value: Any, path: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "值必须是非空字符串数组。", path=path)
    if not allow_empty and not value:
        raise ReviewError("REVIEW_CONTRACT_VALUE_INVALID", "数组不能为空。", path=path)
    return value


def _positive_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReviewError("REVIEW_CONTRACT_VALUE_INVALID", "值必须是正整数。", path=path)
    return value


def _parse_reviewed_at(value: Any) -> str:
    text = _nonempty_string(value, "$.reviewed_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewError("REVIEW_CONTRACT_TIMESTAMP_INVALID", "reviewed_at 必须是 RFC3339。") from exc
    if parsed.tzinfo is None:
        raise ReviewError("REVIEW_CONTRACT_TIMESTAMP_INVALID", "reviewed_at 必须包含时区。")
    return text


def _validate_scope(profile: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ReviewError("REVIEW_PROFILE_SCOPE_INVALID", "scope 必须是 object。", path="$.scope")
    kind = raw.get("kind")
    if profile == "plan-review":
        scope = _closed(raw, {"kind", "task_id", "plan_revision"}, "$.scope")
        if kind != "managed-plan":
            raise ReviewError("REVIEW_PROFILE_SCOPE_INVALID", "plan-review scope 必须是 managed-plan。")
        _nonempty_string(scope["task_id"], "$.scope.task_id")
        _positive_integer(scope["plan_revision"], "$.scope.plan_revision")
        return scope
    if kind == "stage-delta":
        scope = _closed(raw, {"kind", "stage_id", "attempt"}, "$.scope")
        if not re.fullmatch(r"STG-[0-9]{2,}", _nonempty_string(scope["stage_id"], "$.scope.stage_id")):
            raise ReviewError("REVIEW_PROFILE_SCOPE_INVALID", "stage_id 必须使用 STG-NN 格式。")
        _positive_integer(scope["attempt"], "$.scope.attempt")
        return scope
    if kind in {"final-integration", "standalone"}:
        return _closed(raw, {"kind"}, "$.scope")
    raise ReviewError(
        "REVIEW_PROFILE_SCOPE_INVALID",
        "code-review scope 必须是 stage-delta、final-integration 或 standalone。",
    )


def _validate_reviewer(raw: Any) -> dict[str, Any]:
    reviewer = _closed(raw, REVIEWER_FIELDS, "$.reviewer")
    mode = reviewer["mode"]
    if mode not in PROVENANCE_MODES:
        raise ReviewError("REVIEW_PROVENANCE_MODE_INVALID", "未知 reviewer provenance mode。")
    _nonempty_string(reviewer["identity"], "$.reviewer.identity")
    if not isinstance(reviewer["independence_claim"], bool):
        raise ReviewError("REVIEW_PROVENANCE_VALUE_INVALID", "independence_claim 必须是 boolean。")
    _string_list(reviewer["capability_limits"], "$.reviewer.capability_limits")
    if mode == "same-context" and reviewer["independence_claim"]:
        raise ReviewError(
            "REVIEW_PROVENANCE_CLAIM_INVALID",
            "same-context reviewer 不能声明独立审查。",
        )
    return reviewer


def _validate_standards(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "standards 必须是数组。", path="$.standards")
    result = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        path = f"$.standards[{index}]"
        standard = _closed(item, STANDARD_FIELDS, path)
        standard_id = _nonempty_string(standard["id"], f"{path}.id")
        for field in ("title", "source", "applicability"):
            _nonempty_string(standard[field], f"{path}.{field}")
        if standard_id in ids:
            raise ReviewError("REVIEW_CONTRACT_DUPLICATE_ID", "standard id 重复。", path=path)
        ids.add(standard_id)
        result.append(standard)
    return result


def _validate_lenses(
    profile: str,
    raw: Any,
    allowed_paths: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "lenses 必须是数组。", path="$.lenses")
    expected = PLAN_LENSES if profile == "plan-review" else CODE_LENSES
    result = []
    ids: list[str] = []
    for index, item in enumerate(raw):
        path = f"$.lenses[{index}]"
        lens = _closed(item, LENS_FIELDS, path)
        lens_id = _nonempty_string(lens["id"], f"{path}.id")
        status = lens["status"]
        if status not in LENS_STATUSES:
            raise ReviewError("REVIEW_PROFILE_LENS_INVALID", "未知 lens status。", path=f"{path}.status")
        evidence = _evidence_refs(
            lens["evidence_refs"],
            f"{path}.evidence_refs",
            allowed_paths,
            allow_empty=status == "not-applicable",
        )
        _nonempty_string(lens["summary"], f"{path}.summary")
        if status in {"reviewed", "blocked"} and not evidence:
            raise ReviewError("REVIEW_PROFILE_LENS_EVIDENCE_MISSING", "reviewed/blocked lens 需要 evidence。", path=path)
        ids.append(lens_id)
        result.append(lens)
    if tuple(ids) != expected:
        raise ReviewError(
            "REVIEW_PROFILE_LENSES_INCOMPLETE",
            f"lens 必须按 profile 规定顺序完整出现：expected={list(expected)}, actual={ids}",
        )
    return result


def _validate_supersedes(receipt: dict[str, Any], previous: dict[str, Any] | None) -> None:
    previous_id = receipt["supersedes_review_id"]
    if previous_id is None:
        if previous is not None:
            raise ReviewError("REVIEW_SUPERSEDES_UNEXPECTED", "未声明 supersedes_review_id 却提供了前序 receipt。")
        return
    _nonempty_string(previous_id, "$.supersedes_review_id")
    if previous is None:
        raise ReviewError("REVIEW_SUPERSEDES_MISSING", "声明 supersedes_review_id 时必须提供前序 receipt。")
    validate_receipt(previous, check_freshness=False, _skip_lineage=True)
    if previous.get("review_id") != previous_id:
        raise ReviewError("REVIEW_SUPERSEDES_MISMATCH", "前序 receipt 的 review_id 不匹配。")
    if previous_id == receipt["review_id"] or previous.get("supersedes_review_id") == receipt["review_id"]:
        raise ReviewError("REVIEW_SUPERSEDES_CYCLE", "supersedes 链不能形成环。")
    if previous.get("profile") != receipt["profile"]:
        raise ReviewError("REVIEW_SUPERSEDES_PROFILE_MISMATCH", "supersedes 不能跨 profile。")
    previous_scope = previous.get("scope")
    if not isinstance(previous_scope, dict) or previous_scope.get("kind") != receipt["scope"]["kind"]:
        raise ReviewError("REVIEW_SUPERSEDES_SCOPE_MISMATCH", "supersedes 不能跨 scope kind。")


def validate_receipt(
    receipt: Any,
    *,
    workspace: Path | None = None,
    task_dir: Path | None = None,
    check_freshness: bool = True,
    expected_profile: str | None = None,
    expected_scope: str | None = None,
    expected_stage_id: str | None = None,
    expected_attempt: int | None = None,
    previous_receipt: dict[str, Any] | None = None,
    _skip_lineage: bool = False,
) -> dict[str, Any]:
    value = _closed(receipt, ROOT_FIELDS, "$")
    review_id = _nonempty_string(value["review_id"], "$.review_id")
    if not REVIEW_ID.fullmatch(review_id):
        raise ReviewError("REVIEW_CONTRACT_ID_INVALID", "review_id 必须使用 REV- 前缀和大写稳定标识。")
    profile = value["profile"]
    if profile not in PROFILES:
        raise ReviewError("REVIEW_PROFILE_INVALID", "profile 只能是 plan-review 或 code-review。")
    if expected_profile is not None and profile != expected_profile:
        raise ReviewError("REVIEW_PROFILE_MISMATCH", f"期望 profile={expected_profile}，实际为 {profile}。")
    scope = _validate_scope(profile, value["scope"])
    if expected_scope is not None and scope["kind"] != expected_scope:
        raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", f"期望 scope={expected_scope}，实际为 {scope['kind']}。")
    if expected_stage_id is not None and scope.get("stage_id") != expected_stage_id:
        raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", "stage_id 与调用方期望不一致。")
    if expected_attempt is not None and scope.get("attempt") != expected_attempt:
        raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", "attempt 与调用方期望不一致。")
    target = validate_target_shape(value["target"])
    if profile == "plan-review" and target["kind"] != "plan-bundle":
        raise ReviewError("REVIEW_PROFILE_TARGET_MISMATCH", "plan-review 必须绑定 plan-bundle target。")
    if profile == "code-review" and target["kind"] == "plan-bundle":
        raise ReviewError("REVIEW_PROFILE_TARGET_MISMATCH", "code-review 不能绑定 plan-bundle target。")
    if profile == "plan-review":
        identity = target["identity"]
        if identity["task_id"] != scope["task_id"] or identity["plan_revision"] != scope["plan_revision"]:
            raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", "plan target identity 与 receipt scope 不一致。")
    if scope["kind"] == "stage-delta":
        identity = target["identity"]
        if identity.get("stage_id") != scope["stage_id"] or identity.get("attempt") != scope["attempt"]:
            raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", "stage target identity 与 receipt scope 不一致。")
    context = validate_context_target_shape(value["context"])
    brief = None
    if check_freshness:
        verify_target_freshness(target, workspace=workspace, task_dir=task_dir)
        verify_context_freshness(context, workspace=workspace, task_dir=task_dir)
        brief = load_context_brief(context, workspace=workspace, task_dir=task_dir)
        if brief["profile"] != profile or brief["scope"] != scope:
            raise ReviewError(
                "REVIEW_CONTEXT_SCOPE_MISMATCH",
                "review brief 的 profile/scope 与 receipt 不一致。",
            )
    target_paths = [item["path"] for item in target["manifest"]]
    context_paths = {item["path"] for item in context["manifest"]}
    allowed_paths = set(target_paths) | context_paths
    _validate_reviewer(value["reviewer"])
    _validate_standards(value["standards"])
    lenses = _validate_lenses(profile, value["lenses"], allowed_paths)
    findings = validate_findings(value["findings"], allowed_paths)
    strengths = validate_strengths(value["strengths"], allowed_paths)
    gaps = validate_gaps(value["verification_gaps"], allowed_paths)
    coverage = validate_coverage(
        value["coverage"],
        target_paths=target_paths,
        context_paths=context_paths,
        findings=findings,
        gaps=gaps,
        expected_requirement_refs=(brief["requirement_refs"] if brief is not None else None),
        requested_risks=(brief["requested_risk_focus"] if brief is not None else []),
    )
    counts = validate_open_counts(value["open_counts"], derive_open_counts(findings))
    verdict = value["verdict"]
    if verdict not in VERDICTS:
        raise ReviewError("REVIEW_CONTRACT_VERDICT_INVALID", "未知 verdict。")
    derived_verdict = expected_verdict(lenses, findings, gaps)
    if verdict != derived_verdict:
        raise ReviewError(
            "REVIEW_CONTRACT_VERDICT_MISMATCH",
            f"verdict 必须由 lenses/findings/gaps 派生：expected={derived_verdict}, actual={verdict}",
        )
    _nonempty_string(value["summary"], "$.summary")
    limitations = _string_list(value["limitations"], "$.limitations")
    if gaps and not limitations:
        raise ReviewError("REVIEW_GAP_LIMITATION_MISSING", "存在 verification gap 时 limitations 不能为空。")
    _parse_reviewed_at(value["reviewed_at"])
    if _skip_lineage:
        lineage = {
            "predecessor_review_id": value["supersedes_review_id"],
            "accounted_finding_count": 0,
        }
    else:
        _validate_supersedes(value, previous_receipt)
        lineage = validate_lineage(value, previous_receipt)
    return {
        "review_id": review_id,
        "profile": profile,
        "scope": scope,
        "target_digest": target["digest"],
        "context_digest": context["digest"],
        "verdict": verdict,
        "open_counts": counts,
        "gap_counts": derive_gap_counts(gaps),
        "coverage_summary": coverage_summary(coverage),
        "lineage_summary": lineage,
        "strength_count": len(strengths),
        "summary": value["summary"],
    }
