"""把冻结输入、派发 provenance 与语义结果组装成 canonical receipt。"""

from __future__ import annotations

from copy import deepcopy
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
    resolve_review_artifact,
    review_artifact_ref,
    sha256_file,
)
from .semantic_result import (
    RECEIPT_SEMANTIC_FIELDS,
    validate_semantic_result,
    validate_semantic_timeline,
)
from .target import validate_target_shape, verify_target_freshness


def assemble_receipt(
    *,
    target_path: Path,
    context_path: Path,
    dispatch_path: Path,
    semantic_result_path: Path,
    review_root: Path,
    workspace: Path | None = None,
    task_dir: Path | None = None,
) -> dict[str, Any]:
    """组装 receipt；关闭失败时仅允许保留不可过门的候选证据。"""

    resolved_target = resolve_review_artifact(target_path, review_root)
    resolved_context = resolve_review_artifact(context_path, review_root)
    resolved_dispatch = resolve_review_artifact(dispatch_path, review_root)
    resolved_result = resolve_review_artifact(semantic_result_path, review_root)
    target = validate_target_shape(load_json_object(resolved_target))
    context = validate_context_target_shape(load_json_object(resolved_context))
    verify_target_freshness(target, workspace=workspace, task_dir=task_dir)
    verify_context_freshness(context, workspace=workspace, task_dir=task_dir)
    dispatch = load_json_object(resolved_dispatch)
    dispatch_summary = validate_dispatch(
        dispatch,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
    )
    inputs = dispatch["inputs"]
    if (
        review_artifact_ref(resolved_target, review_root) != inputs["target_ref"]
        or review_artifact_ref(resolved_context, review_root) != inputs["context_ref"]
        or target["digest"] != inputs["target_digest"]
        or context["digest"] != inputs["context_digest"]
    ):
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "assembler 输入与 final dispatch 冻结输入不一致。",
        )
    result_ref = review_artifact_ref(resolved_result, review_root)
    if result_ref != inputs["semantic_result_ref"]:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "semantic result 路径与 dispatch 预声明路径不一致。",
        )
    lifecycle = dispatch["lifecycle"]
    candidate_unclosed = (
        lifecycle["status"] == "failed"
        and lifecycle["close"]["status"] == "failed"
        and lifecycle["failure"] is not None
        and lifecycle["failure"]["code"] == "REVIEW_DISPATCH_AGENT_UNCLOSED"
    )
    if not dispatch_summary["receipt_ready"] and not candidate_unclosed:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "只有完成、合法回退或关闭失败候选可以组装 receipt。",
        )
    brief = load_context_brief(context, workspace=workspace, task_dir=task_dir)
    semantic = load_json_object(resolved_result, code="REVIEW_RESULT_INVALID")
    validate_semantic_result(
        semantic,
        target=target,
        context=context,
        brief=brief,
        expected_review_id=dispatch["review_id"],
        expected_profile=dispatch["profile"],
        expected_scope=dispatch["scope"],
    )
    validate_semantic_timeline(semantic, dispatch)
    reviewer = {
        **deepcopy(dispatch["reviewer"]),
        "dispatch_id": dispatch["dispatch_id"],
        "dispatch_ref": review_artifact_ref(resolved_dispatch, review_root),
        "dispatch_digest": sha256_file(resolved_dispatch),
        "semantic_result_ref": result_ref,
        "semantic_result_digest": sha256_file(resolved_result),
    }
    receipt = {
        "review_id": semantic["review_id"],
        "profile": semantic["profile"],
        "scope": deepcopy(semantic["scope"]),
        "target": deepcopy(target),
        "context": deepcopy(context),
        "reviewer": reviewer,
    }
    receipt.update(
        {
            field: deepcopy(semantic[field])
            for field in RECEIPT_SEMANTIC_FIELDS
        }
    )
    return receipt
