"""校验 delegated reviewer 返回的封闭语义结果。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .coverage import coverage_summary, validate_coverage
from .errors import ReviewError
from .review_parts import (
    _evidence_refs,
    derive_gap_counts,
    derive_open_counts,
    expected_verdict,
    validate_findings,
    validate_gaps,
    validate_open_counts,
    validate_strengths,
)


RESULT_FIELDS = {
    "kind",
    "review_id",
    "profile",
    "scope",
    "target_digest",
    "context_digest",
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
RECEIPT_SEMANTIC_FIELDS = RESULT_FIELDS - {
    "kind",
    "review_id",
    "profile",
    "scope",
    "target_digest",
    "context_digest",
}
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
LENS_STATUSES = {"reviewed", "not-applicable", "blocked"}
VERDICTS = {"passed", "changes_required", "blocked"}
REVIEW_ID = re.compile(r"^REV-[A-Z0-9][A-Z0-9._-]{2,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _invalid(message: str, path: str | None = None) -> ReviewError:
    return ReviewError("REVIEW_RESULT_INVALID", message, path=path)


def _closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid("值必须是 object。", path)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise _invalid(f"封闭字段不匹配：unknown={unknown}, missing={missing}", path)
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid("值必须是非空字符串。", path)
    if "REPLACE-ME" in value or value.startswith("REV-TEMPLATE"):
        raise _invalid("模板占位值必须在审查前替换。", path)
    return value


def _strings(value: Any, path: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise _invalid("值必须是非空字符串数组。", path)
    if not allow_empty and not value:
        raise _invalid("数组不能为空。", path)
    return value


def validate_scope(profile: str, raw: Any, *, path: str = "$.scope") -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _invalid("scope 必须是 object。", path)
    kind = raw.get("kind")
    if profile == "plan-review":
        scope = _closed(raw, {"kind", "task_id", "plan_revision"}, path)
        if kind != "managed-plan":
            raise _invalid("plan-review scope 必须是 managed-plan。", path)
        _nonempty(scope["task_id"], f"{path}.task_id")
        revision = scope["plan_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise _invalid("plan_revision 必须是正整数。", f"{path}.plan_revision")
        return scope
    if kind == "stage-delta":
        scope = _closed(raw, {"kind", "stage_id", "attempt"}, path)
        stage_id = _nonempty(scope["stage_id"], f"{path}.stage_id")
        if not re.fullmatch(r"STG-[0-9]{2,}", stage_id):
            raise _invalid("stage_id 必须使用 STG-NN 格式。", f"{path}.stage_id")
        attempt = scope["attempt"]
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise _invalid("attempt 必须是正整数。", f"{path}.attempt")
        return scope
    if kind in {"final-integration", "standalone"}:
        return _closed(raw, {"kind"}, path)
    raise _invalid("code-review scope 必须是 stage-delta、final-integration 或 standalone。", path)


def _validate_standards(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise _invalid("standards 必须是数组。", "$.standards")
    result = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        path = f"$.standards[{index}]"
        standard = _closed(item, STANDARD_FIELDS, path)
        standard_id = _nonempty(standard["id"], f"{path}.id")
        for field in ("title", "source", "applicability"):
            _nonempty(standard[field], f"{path}.{field}")
        if standard_id in ids:
            raise _invalid("standard id 重复。", path)
        ids.add(standard_id)
        result.append(standard)
    return result


def _validate_lenses(
    profile: str,
    raw: Any,
    allowed_paths: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise _invalid("lenses 必须是数组。", "$.lenses")
    expected = PLAN_LENSES if profile == "plan-review" else CODE_LENSES
    result = []
    ids: list[str] = []
    for index, item in enumerate(raw):
        path = f"$.lenses[{index}]"
        lens = _closed(item, LENS_FIELDS, path)
        lens_id = _nonempty(lens["id"], f"{path}.id")
        if lens["status"] not in LENS_STATUSES:
            raise _invalid("未知 lens status。", f"{path}.status")
        evidence = _evidence_refs(
            lens["evidence_refs"],
            f"{path}.evidence_refs",
            allowed_paths,
            allow_empty=lens["status"] == "not-applicable",
        )
        _nonempty(lens["summary"], f"{path}.summary")
        if lens["status"] in {"reviewed", "blocked"} and not evidence:
            raise _invalid("reviewed/blocked lens 需要 evidence。", path)
        ids.append(lens_id)
        result.append(lens)
    if tuple(ids) != expected:
        raise _invalid(
            f"lens 必须按 profile 规定顺序完整出现：expected={list(expected)}, actual={ids}",
            "$.lenses",
        )
    return result


def _parse_timestamp(value: Any) -> str:
    text = _nonempty(value, "$.reviewed_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid("reviewed_at 必须是 RFC3339。", "$.reviewed_at") from exc
    if parsed.tzinfo is None:
        raise _invalid("reviewed_at 必须包含时区。", "$.reviewed_at")
    return text


def validate_semantic_timeline(
    result: dict[str, Any],
    dispatch: dict[str, Any],
) -> None:
    """把语义结果时间绑定到已验证的派发生命周期。"""

    reviewed_at = _parse_timestamp(result["reviewed_at"])
    reviewed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    lifecycle = dispatch["lifecycle"]
    lower_bound = lifecycle["started_at"] or dispatch["prepared_at"]
    completed_at = lifecycle["completed_at"]
    lower = datetime.fromisoformat(lower_bound.replace("Z", "+00:00"))
    if reviewed < lower:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "semantic reviewed_at 不能早于审查开始时间。",
        )
    if completed_at is not None:
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        if reviewed > completed:
            raise ReviewError(
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
                "semantic reviewed_at 不能晚于 lifecycle.completed_at。",
            )


def _validate_result(
    value: Any,
    *,
    target: dict[str, Any],
    context: dict[str, Any],
    brief: dict[str, Any] | None,
    expected_review_id: str | None,
    expected_profile: str | None,
    expected_scope: dict[str, Any] | None,
) -> dict[str, Any]:
    result = _closed(value, RESULT_FIELDS, "$")
    if result["kind"] != "review-semantic-result":
        raise _invalid("kind 必须是 review-semantic-result。", "$.kind")
    review_id = _nonempty(result["review_id"], "$.review_id")
    if REVIEW_ID.fullmatch(review_id) is None:
        raise _invalid("review_id 必须使用 REV- 前缀和大写稳定标识。", "$.review_id")
    if expected_review_id is not None and review_id != expected_review_id:
        raise _invalid("review_id 与 dispatch 不一致。", "$.review_id")
    profile = result["profile"]
    if profile not in PROFILES:
        raise _invalid("profile 只能是 plan-review 或 code-review。", "$.profile")
    if expected_profile is not None and profile != expected_profile:
        raise _invalid("profile 与调用方期望不一致。", "$.profile")
    scope = validate_scope(profile, result["scope"])
    if expected_scope is not None and scope != expected_scope:
        raise _invalid("scope 与 dispatch 不一致。", "$.scope")
    for field, expected in (
        ("target_digest", target["digest"]),
        ("context_digest", context["digest"]),
    ):
        digest = result[field]
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise _invalid(f"{field} 必须是小写 SHA-256。", f"$.{field}")
        if digest != expected:
            raise _invalid(f"{field} 与冻结输入不一致。", f"$.{field}")
    target_paths = [item["path"] for item in target["manifest"]]
    context_paths = {item["path"] for item in context["manifest"]}
    allowed_paths = set(target_paths) | context_paths
    _validate_standards(result["standards"])
    lenses = _validate_lenses(profile, result["lenses"], allowed_paths)
    findings = validate_findings(result["findings"], allowed_paths)
    strengths = validate_strengths(result["strengths"], allowed_paths)
    gaps = validate_gaps(result["verification_gaps"], allowed_paths)
    coverage = validate_coverage(
        result["coverage"],
        target_paths=target_paths,
        context_paths=context_paths,
        findings=findings,
        gaps=gaps,
        expected_requirement_refs=(brief["requirement_refs"] if brief is not None else None),
        requested_risks=(brief["requested_risk_focus"] if brief is not None else []),
    )
    counts = validate_open_counts(result["open_counts"], derive_open_counts(findings))
    verdict = result["verdict"]
    if verdict not in VERDICTS:
        raise _invalid("未知 verdict。", "$.verdict")
    derived_verdict = expected_verdict(lenses, findings, gaps)
    if verdict != derived_verdict:
        raise _invalid(
            f"verdict 必须由 lenses/findings/gaps 派生：expected={derived_verdict}, actual={verdict}",
            "$.verdict",
        )
    _nonempty(result["summary"], "$.summary")
    limitations = _strings(result["limitations"], "$.limitations")
    if gaps and not limitations:
        raise _invalid("存在 verification gap 时 limitations 不能为空。", "$.limitations")
    supersedes = result["supersedes_review_id"]
    if supersedes is not None:
        _nonempty(supersedes, "$.supersedes_review_id")
    _parse_timestamp(result["reviewed_at"])
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
        "strength_count": len(strengths),
        "summary": result["summary"],
    }


def validate_semantic_result(
    value: Any,
    *,
    target: dict[str, Any],
    context: dict[str, Any],
    brief: dict[str, Any] | None = None,
    expected_review_id: str | None = None,
    expected_profile: str | None = None,
    expected_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """校验子 Agent 语义结果，并把内部诊断收敛到稳定错误族。"""

    try:
        return _validate_result(
            value,
            target=target,
            context=context,
            brief=brief,
            expected_review_id=expected_review_id,
            expected_profile=expected_profile,
            expected_scope=expected_scope,
        )
    except ReviewError as exc:
        if exc.code == "REVIEW_RESULT_INVALID":
            raise
        raise ReviewError(
            "REVIEW_RESULT_INVALID",
            f"{exc.code}: {exc.message}",
            path=exc.path,
        ) from exc
