#!/usr/bin/env python3
"""计算 dependency preflight 新鲜度与 stage 执行映射。"""

from __future__ import annotations

import fnmatch
from datetime import date
from typing import Any

from harness_dependency_gate import (
    CHANGE_ACTIONS,
    FRESHNESS_DAYS,
    DependencyGateError,
    approved_evidence_date,
    dependency_selection,
    validate_runtime_receipt,
)
from harness_task_bundle import TaskBundle


def path_matches(path: str, pattern: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized_pattern = pattern.replace("\\", "/")
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
    if fnmatch.fnmatchcase(normalized_path, normalized_pattern):
        return True
    return normalized_pattern.startswith("**/") and fnmatch.fnmatchcase(
        normalized_path,
        normalized_pattern[3:],
    )


def stage_map(
    bundle: TaskBundle,
    decisions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    stages = [item for item in bundle.contract.get("stages", []) if isinstance(item, dict)]
    mapping: dict[str, list[str]] = {}
    for decision in decisions:
        decision_id = str(decision.get("id", ""))
        manifests = [str(item) for item in decision.get("manifest_paths", [])]
        stage_ids: set[str] = set()
        uncovered: list[str] = []
        for manifest in manifests:
            matching = {
                str(stage.get("id"))
                for stage in stages
                if any(
                    path_matches(manifest, str(pattern))
                    for pattern in stage.get("allowed_changes", [])
                )
            }
            if not matching and decision.get("action") in CHANGE_ACTIONS:
                uncovered.append(manifest)
            stage_ids.update(matching)
        if not stage_ids and decision.get("action") == "retain":
            decision_validations = set(decision.get("validation_ids", []))
            validation_stage = next(
                (
                    str(stage.get("id"))
                    for stage in stages
                    if decision_validations & set(stage.get("validation_ids", []))
                ),
                None,
            )
            if validation_stage:
                stage_ids.add(validation_stage)
            else:
                uncovered.extend(manifests)
        if uncovered:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_STAGE_UNMAPPED",
                f"{decision_id} manifest 未映射到批准 stage：{sorted(uncovered)}",
            )
        mapping[decision_id] = sorted(stage_ids)
    return mapping


def freshness_summary(
    bundle: TaskBundle,
    decisions: list[dict[str, Any]],
    today: date,
) -> tuple[list[dict[str, Any]], list[str]]:
    summaries: list[dict[str, Any]] = []
    stale: list[str] = []
    for decision in decisions:
        decision_id = str(decision.get("id", ""))
        criticality = str(decision.get("criticality", ""))
        maximum_age = decision.get("freshness_max_age_days")
        expected_age = FRESHNESS_DAYS.get(criticality)
        if expected_age is None or maximum_age != expected_age:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_APPROVAL_INVALID",
                f"{decision_id} criticality 与 freshness policy 不一致。",
            )
        approved_as_of = approved_evidence_date(bundle, decision, today)
        age = (today - approved_as_of).days
        is_stale = age > expected_age
        if is_stale:
            stale.append(decision_id)
        summaries.append(
            {
                "decision_id": decision_id,
                "approved_as_of": approved_as_of.isoformat(),
                "age_days": age,
                "maximum_age_days": expected_age,
                "stale": is_stale,
            }
        )
    return summaries, sorted(stale)


def evaluate_dependency_preflight(
    bundle: TaskBundle,
    runtime_receipt: str | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    reference_date = today or date.today()
    mode, decisions = dependency_selection(bundle)
    if mode == "none":
        if runtime_receipt:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_RECEIPT_UNEXPECTED",
                "none mode 不接受 runtime dependency receipt。",
            )
        return {
            "mode": "none",
            "decision_ids": [],
            "stale_approved_decision_ids": [],
            "runtime_recheck": None,
            "stage_map": {},
            "result": "not-applicable",
        }

    freshness, stale = freshness_summary(bundle, decisions, reference_date)
    mapping = stage_map(bundle, decisions)
    runtime: dict[str, Any] | None = None
    if runtime_receipt:
        runtime = validate_runtime_receipt(
            bundle,
            runtime_receipt,
            decisions,
            today=reference_date,
            require_manifest=False,
        )
    elif stale:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_EVIDENCE_STALE",
            f"批准 dependency evidence 已过期：{stale}；需要在线复核 receipt。",
        )
    return {
        "mode": mode,
        "decision_ids": sorted(str(item.get("id")) for item in decisions),
        "freshness": freshness,
        "stale_approved_decision_ids": stale,
        "runtime_recheck": runtime,
        "stage_map": mapping,
        "result": "passed",
    }


def evaluate_dependency_stage(
    bundle: TaskBundle,
    stage_id: str,
    runtime_receipt: str | None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    mode, decisions = dependency_selection(bundle)
    if mode == "none":
        return {
            "mode": "none",
            "stage_id": stage_id,
            "decision_ids": [],
            "result": "not-applicable",
        }
    stage_ids = {
        str(item.get("id"))
        for item in bundle.contract.get("stages", [])
        if isinstance(item, dict)
    }
    if stage_id not in stage_ids:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_STAGE_INVALID",
            f"未知 stage：{stage_id}",
        )
    mapping = stage_map(bundle, decisions)
    relevant = [
        item
        for item in decisions
        if stage_id in mapping.get(str(item.get("id")), [])
    ]
    if not relevant:
        return {
            "mode": mode,
            "stage_id": stage_id,
            "decision_ids": [],
            "result": "not-applicable",
        }
    if not runtime_receipt:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_MISSING",
            f"{stage_id} 涉及批准 manifest，完成前必须提供 runtime receipt。",
        )
    runtime = validate_runtime_receipt(
        bundle,
        runtime_receipt,
        relevant,
        today=today or date.today(),
        require_manifest=True,
    )
    return {
        "mode": mode,
        "stage_id": stage_id,
        "decision_ids": sorted(str(item.get("id")) for item in relevant),
        "runtime_receipt": runtime,
        "result": "passed",
    }
