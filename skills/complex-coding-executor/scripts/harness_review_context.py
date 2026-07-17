#!/usr/bin/env python3
"""把 managed review context 绑定到 contract 与当前验证证据。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness_review_errors import ReviewGateError
from harness_review_target import _stage_map
from harness_task_bundle import TaskBundle


def _workspace_relative(bundle: TaskBundle, path: Path) -> str:
    try:
        return path.resolve().relative_to(bundle.workspace.resolve()).as_posix()
    except ValueError as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONTEXT_INVALID",
            f"managed context 文件越出 workspace：{path}",
        ) from exc


def _record_ids(records: Any) -> list[str]:
    if not isinstance(records, list):
        return []
    return [
        str(item["id"])
        for item in records
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _managed_brief_refs(
    bundle: TaskBundle,
    *,
    scope_kind: str,
    stage_id: str | None,
) -> tuple[list[str], list[str]]:
    stages = _stage_map(bundle)
    if scope_kind == "stage-delta" and stage_id is not None:
        stage = stages.get(stage_id)
        if stage is None:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_CONTEXT_INVALID",
                f"managed review brief 引用了未知 stage：{stage_id}",
            )
        requirements: list[str] = []
        for field in ("requirement_ids", "acceptance_ids", "nonfunctional_ids"):
            values = stage.get(field)
            if isinstance(values, list):
                requirements.extend(item for item in values if isinstance(item, str))
        if not requirements:
            requirements.append(stage_id)
        constraints = [stage_id]
        validation_ids = stage.get("validation_ids")
        if isinstance(validation_ids, list):
            constraints.extend(item for item in validation_ids if isinstance(item, str))
        return sorted(set(requirements)), sorted(set(constraints))
    requirements = []
    goal = bundle.contract.get("goal")
    if isinstance(goal, dict) and isinstance(goal.get("id"), str):
        requirements.append(str(goal["id"]))
    for field in ("requirements", "acceptance_criteria", "nonfunctional_requirements"):
        requirements.extend(_record_ids(bundle.contract.get(field)))
    if not requirements:
        requirements.extend(stages)
    constraints = list(stages)
    constraints.extend(_record_ids(bundle.contract.get("validations")))
    return sorted(set(requirements)), sorted(set(constraints))


def _effective_validation_claims(
    events: list[dict[str, Any]],
    *,
    scope_kind: str,
    stage_id: str | None,
    attempt: int | None,
) -> tuple[set[str], list[dict[str, Any]]]:
    records: dict[tuple[str, str], tuple[list[str], dict[str, Any]]] = {}
    for event in events:
        if event.get("type") != "validation_recorded":
            continue
        current_stage = event.get("stage_id")
        current_attempt = event.get("attempt")
        if scope_kind == "stage-delta" and (
            current_stage != stage_id or current_attempt != attempt
        ):
            continue
        payload = event.get("payload")
        if not isinstance(current_stage, str) or not isinstance(payload, dict):
            continue
        validation_id = payload.get("validation_id")
        if not isinstance(validation_id, str):
            continue
        key = (current_stage, validation_id)
        if payload.get("result") == "passed":
            refs = [
                item
                for item in event.get("evidence_refs", [])
                if isinstance(item, str)
            ]
            records[key] = (refs, payload)
        else:
            records.pop(key, None)
    refs = {item for record_refs, _ in records.values() for item in record_refs}
    return refs, [payload for _, payload in records.values()]


def validate_managed_context(
    bundle: TaskBundle,
    receipt: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    scope_kind: str,
    stage_id: str | None,
    attempt: int | None,
) -> None:
    """约束 managed brief/context 必须覆盖批准需求与当前验证证据。"""

    context = receipt.get("context")
    identity = context.get("identity") if isinstance(context, dict) else None
    manifest = context.get("manifest") if isinstance(context, dict) else None
    if (
        not isinstance(context, dict)
        or not isinstance(identity, dict)
        or identity.get("root") != "workspace"
        or not isinstance(manifest, list)
    ):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONTEXT_INVALID",
            "managed code-review context 必须使用 workspace root。",
        )
    entries = [item for item in manifest if isinstance(item, dict)]
    context_paths = {
        str(item["path"])
        for item in entries
        if isinstance(item.get("path"), str)
    }
    briefs = [
        item
        for item in entries
        if item.get("role") == "brief" and item.get("state") == "present"
    ]
    if len(briefs) != 1:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONTEXT_INVALID",
            "managed context 必须包含且只包含一个 present brief。",
        )
    brief_relative = str(briefs[0]["path"])
    brief_path = bundle.workspace / brief_relative
    review_root = (bundle.task_dir / "artifacts" / "reviews").resolve()
    try:
        resolved_brief = brief_path.resolve(strict=True)
        resolved_brief.relative_to(review_root)
        brief = json.loads(resolved_brief.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONTEXT_INVALID",
            f"managed review brief 必须位于 task-local review root：{exc}",
        ) from exc
    if not isinstance(brief, dict):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONTEXT_INVALID",
            "managed review brief 根节点必须是 object。",
        )
    expected_requirements, expected_constraints = _managed_brief_refs(
        bundle,
        scope_kind=scope_kind,
        stage_id=stage_id,
    )
    if brief.get("requirement_refs") != expected_requirements:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_REQUIREMENTS_MISMATCH",
            "managed review brief.requirement_refs 未精确覆盖当前 contract scope。",
        )
    if brief.get("constraint_refs") != expected_constraints:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONSTRAINTS_MISMATCH",
            "managed review brief.constraint_refs 未精确覆盖 stage/validation 约束。",
        )
    evidence_refs, validation_records = _effective_validation_claims(
        events,
        scope_kind=scope_kind,
        stage_id=stage_id,
        attempt=attempt,
    )
    workspace_evidence = {
        _workspace_relative(bundle, bundle.task_dir / ref) for ref in evidence_refs
    }
    claim_refs = brief.get("claim_refs")
    if not isinstance(claim_refs, list) or not workspace_evidence <= set(claim_refs):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_VALIDATION_CONTEXT_MISSING",
            "managed review brief.claim_refs 未包含当前 validation evidence。",
        )
    required_paths = {
        brief_relative,
        _workspace_relative(bundle, bundle.plan_path),
        _workspace_relative(bundle, bundle.contract_path),
        *workspace_evidence,
    }
    for artifact in bundle.contract.get("artifacts", []):
        if (
            isinstance(artifact, dict)
            and artifact.get("kind") == "standards"
            and isinstance(artifact.get("path"), str)
        ):
            required_paths.add(
                _workspace_relative(bundle, bundle.task_dir / str(artifact["path"]))
            )
    missing = sorted(required_paths - context_paths)
    if missing:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_CONTEXT_INCOMPLETE",
            "managed context 缺少 plan、contract、standards 或 validation evidence："
            + ", ".join(missing),
        )
    if scope_kind == "stage-delta":
        target = receipt.get("target")
        target_digest = target.get("digest") if isinstance(target, dict) else None
        stale = sorted(
            str(item.get("validation_id"))
            for item in validation_records
            if item.get("target_digest") != target_digest
            or item.get("stage_attempt") != attempt
        )
        if stale:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_VALIDATION_TARGET_MISMATCH",
                "managed review 消费了其它 target/attempt 的 validation evidence："
                + ", ".join(stale),
            )
