"""Canonical review receipt 的交叉绑定与门禁语义。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .context import (
    load_context_brief,
    validate_context_target_shape,
    verify_context_freshness,
)
from .dispatch_lifecycle import validate_dispatch
from .errors import ReviewError
from .io import (
    load_json_object,
    normalize_review_ref,
    resolve_review_ref,
    sha256_file,
)
from .review_parts import derive_open_counts, validate_lineage
from .semantic_result import (
    CODE_LENSES,
    PLAN_LENSES,
    PROFILES,
    RECEIPT_SEMANTIC_FIELDS,
    REVIEW_ID,
    validate_scope,
    validate_semantic_result,
    validate_semantic_timeline,
)
from .target import validate_target_shape, verify_target_freshness


ROOT_FIELDS = {
    "review_id",
    "profile",
    "scope",
    "target",
    "context",
    "reviewer",
    *RECEIPT_SEMANTIC_FIELDS,
}
REVIEWER_FIELDS = {
    "mode",
    "identity",
    "independence_claim",
    "capability_limits",
    "dispatch_id",
    "dispatch_ref",
    "dispatch_digest",
    "semantic_result_ref",
    "semantic_result_digest",
}
PROVENANCE_MODES = {"same-context", "external-agent"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError("REVIEW_CONTRACT_VALUE_INVALID", "值必须是非空字符串。", path=path)
    if "REPLACE-ME" in value or value.startswith("REV-TEMPLATE"):
        raise ReviewError("REVIEW_CONTRACT_PLACEHOLDER", "模板占位值必须在审查前替换。", path=path)
    return value


def _digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ReviewError("REVIEW_DISPATCH_PROVENANCE_MISMATCH", "摘要必须是小写 SHA-256。", path=path)
    return value


def _validate_reviewer(raw: Any) -> dict[str, Any]:
    reviewer = _closed(raw, REVIEWER_FIELDS, "$.reviewer")
    if reviewer["mode"] not in PROVENANCE_MODES:
        raise ReviewError("REVIEW_PROVENANCE_MODE_INVALID", "未知 reviewer provenance mode。")
    _nonempty(reviewer["identity"], "$.reviewer.identity")
    if not isinstance(reviewer["independence_claim"], bool):
        raise ReviewError("REVIEW_PROVENANCE_VALUE_INVALID", "independence_claim 必须是 boolean。")
    limits = reviewer["capability_limits"]
    if not isinstance(limits, list) or not all(
        isinstance(item, str) and item.strip() for item in limits
    ):
        raise ReviewError("REVIEW_PROVENANCE_VALUE_INVALID", "capability_limits 必须是字符串数组。")
    if reviewer["mode"] == "same-context" and reviewer["independence_claim"]:
        raise ReviewError(
            "REVIEW_PROVENANCE_CLAIM_INVALID",
            "same-context reviewer 不能声明独立审查。",
        )
    _nonempty(reviewer["dispatch_id"], "$.reviewer.dispatch_id")
    for field in ("dispatch_ref", "semantic_result_ref"):
        reference = _nonempty(reviewer[field], f"$.reviewer.{field}")
        if normalize_review_ref(reference) != reference:
            raise ReviewError("REVIEW_DISPATCH_PROVENANCE_MISMATCH", "supporting ref 未 canonicalize。")
    _digest(reviewer["dispatch_digest"], "$.reviewer.dispatch_digest")
    _digest(reviewer["semantic_result_digest"], "$.reviewer.semantic_result_digest")
    return reviewer


def _verify_freshness(
    target: dict[str, Any],
    context: dict[str, Any],
    *,
    workspace: Path | None,
    task_dir: Path | None,
) -> None:
    try:
        verify_target_freshness(target, workspace=workspace, task_dir=task_dir)
        verify_context_freshness(context, workspace=workspace, task_dir=task_dir)
    except ReviewError as exc:
        if exc.code in {"REVIEW_TARGET_STALE", "REVIEW_CONTEXT_STALE"}:
            raise ReviewError(
                "REVIEW_DISPATCH_STALE",
                f"冻结 target/context 已变化：{exc.message}",
                path=exc.path,
            ) from exc
        raise


def _validate_profile_target(profile: str, target: dict[str, Any]) -> None:
    if profile == "plan-review" and target["kind"] != "plan-bundle":
        raise ReviewError(
            "REVIEW_PROFILE_TARGET_MISMATCH",
            "plan-review 必须使用 plan-bundle target。",
        )
    if profile == "code-review" and target["kind"] == "plan-bundle":
        raise ReviewError(
            "REVIEW_PROFILE_TARGET_MISMATCH",
            "code-review 不能使用 plan-bundle target。",
        )


def _load_supporting(
    reviewer: dict[str, Any],
    *,
    review_root: Path,
    workspace: Path | None,
    task_dir: Path | None,
    expected_policy: str | None,
    check_freshness: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    dispatch_path = resolve_review_ref(reviewer["dispatch_ref"], review_root)
    result_path = resolve_review_ref(reviewer["semantic_result_ref"], review_root)
    if sha256_file(dispatch_path) != reviewer["dispatch_digest"]:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "receipt 引用的 final dispatch 摘要不匹配。",
        )
    if sha256_file(result_path) != reviewer["semantic_result_digest"]:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "receipt 引用的 semantic result 摘要不匹配。",
        )
    dispatch = load_json_object(dispatch_path)
    dispatch_summary = validate_dispatch(
        dispatch,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
        expected_policy=expected_policy,
        require_receipt_ready=True,
        check_freshness=check_freshness,
    )
    semantic = load_json_object(result_path, code="REVIEW_RESULT_INVALID")
    return dispatch, dispatch_summary, semantic


def _validate_supporting_bindings(
    receipt: dict[str, Any],
    reviewer: dict[str, Any],
    dispatch: dict[str, Any],
    semantic: dict[str, Any],
    *,
    review_root: Path,
    brief: dict[str, Any] | None,
) -> dict[str, Any]:
    if reviewer["dispatch_id"] != dispatch["dispatch_id"]:
        raise ReviewError("REVIEW_DISPATCH_PROVENANCE_MISMATCH", "dispatch_id 不匹配。")
    expected_reviewer = {
        field: dispatch["reviewer"][field]
        for field in ("mode", "identity", "independence_claim", "capability_limits")
    }
    actual_reviewer = {field: reviewer[field] for field in expected_reviewer}
    if actual_reviewer != expected_reviewer:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "receipt reviewer provenance 与 final dispatch 不一致。",
        )
    inputs = dispatch["inputs"]
    if (
        reviewer["semantic_result_ref"] != inputs["semantic_result_ref"]
        or dispatch["review_id"] != receipt["review_id"]
        or dispatch["profile"] != receipt["profile"]
        or dispatch["scope"] != receipt["scope"]
    ):
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "dispatch、result 与 receipt 身份绑定不一致。",
        )
    bound_target = load_json_object(resolve_review_ref(inputs["target_ref"], review_root))
    bound_context = load_json_object(resolve_review_ref(inputs["context_ref"], review_root))
    if bound_target != receipt["target"] or bound_context != receipt["context"]:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "receipt 未精确复用 dispatch 冻结的 target/context。",
        )
    summary = validate_semantic_result(
        semantic,
        target=receipt["target"],
        context=receipt["context"],
        brief=brief,
        expected_review_id=receipt["review_id"],
        expected_profile=receipt["profile"],
        expected_scope=receipt["scope"],
    )
    validate_semantic_timeline(semantic, dispatch)
    mismatched = sorted(
        field
        for field in RECEIPT_SEMANTIC_FIELDS
        if receipt[field] != semantic[field]
    )
    if mismatched:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "receipt 语义字段未原样复制 semantic result：" + ", ".join(mismatched),
        )
    return summary


def _validate_supersedes(
    receipt: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    review_root: Path,
    workspace: Path | None,
    task_dir: Path | None,
) -> None:
    previous_id = receipt["supersedes_review_id"]
    if previous_id is None:
        if previous is not None:
            raise ReviewError("REVIEW_SUPERSEDES_UNEXPECTED", "未声明 supersedes_review_id 却提供了前序 receipt。")
        return
    _nonempty(previous_id, "$.supersedes_review_id")
    if previous is None:
        raise ReviewError("REVIEW_SUPERSEDES_MISSING", "声明 supersedes_review_id 时必须提供前序 receipt。")
    validate_receipt(
        previous,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
        check_freshness=False,
        _skip_lineage=True,
    )
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
    review_root: Path,
    workspace: Path | None = None,
    task_dir: Path | None = None,
    check_freshness: bool = True,
    expected_profile: str | None = None,
    expected_scope: str | None = None,
    expected_stage_id: str | None = None,
    expected_attempt: int | None = None,
    expected_dispatch_policy: str | None = None,
    previous_receipt: dict[str, Any] | None = None,
    _skip_lineage: bool = False,
) -> dict[str, Any]:
    """校验 canonical receipt 及其 dispatch/result supporting artifacts。"""

    value = _closed(receipt, ROOT_FIELDS, "$")
    review_id = _nonempty(value["review_id"], "$.review_id")
    if REVIEW_ID.fullmatch(review_id) is None:
        raise ReviewError("REVIEW_CONTRACT_ID_INVALID", "review_id 必须使用 REV- 前缀和大写稳定标识。")
    profile = value["profile"]
    if profile not in PROFILES:
        raise ReviewError("REVIEW_PROFILE_INVALID", "profile 只能是 plan-review 或 code-review。")
    if expected_profile is not None and profile != expected_profile:
        raise ReviewError("REVIEW_PROFILE_MISMATCH", f"期望 profile={expected_profile}，实际为 {profile}。")
    scope = validate_scope(profile, value["scope"])
    if expected_scope is not None and scope["kind"] != expected_scope:
        raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", f"期望 scope={expected_scope}，实际为 {scope['kind']}。")
    if expected_stage_id is not None and scope.get("stage_id") != expected_stage_id:
        raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", "stage_id 与调用方期望不一致。")
    if expected_attempt is not None and scope.get("attempt") != expected_attempt:
        raise ReviewError("REVIEW_PROFILE_SCOPE_MISMATCH", "attempt 与调用方期望不一致。")
    target = validate_target_shape(value["target"])
    context = validate_context_target_shape(value["context"])
    _validate_profile_target(profile, target)
    brief = None
    if check_freshness:
        _verify_freshness(target, context, workspace=workspace, task_dir=task_dir)
        brief = load_context_brief(context, workspace=workspace, task_dir=task_dir)
        if brief["profile"] != profile or brief["scope"] != scope:
            raise ReviewError("REVIEW_CONTEXT_SCOPE_MISMATCH", "review brief 与 receipt profile/scope 不一致。")
    reviewer = _validate_reviewer(value["reviewer"])
    dispatch, dispatch_summary, semantic = _load_supporting(
        reviewer,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
        expected_policy=expected_dispatch_policy,
        check_freshness=check_freshness,
    )
    semantic_summary = _validate_supporting_bindings(
        value,
        reviewer,
        dispatch,
        semantic,
        review_root=review_root,
        brief=brief,
    )
    if _skip_lineage:
        lineage = {
            "predecessor_review_id": value["supersedes_review_id"],
            "accounted_finding_count": 0,
        }
    else:
        _validate_supersedes(
            value,
            previous_receipt,
            review_root=review_root,
            workspace=workspace,
            task_dir=task_dir,
        )
        lineage = validate_lineage(value, previous_receipt)
    return {
        **semantic_summary,
        "lineage_summary": lineage,
        "reviewer_mode": reviewer["mode"],
        "independence_claim": reviewer["independence_claim"],
        "dispatch_id": reviewer["dispatch_id"],
        "dispatch_policy": dispatch["policy"],
        "lifecycle_status": dispatch_summary["lifecycle_status"],
    }
