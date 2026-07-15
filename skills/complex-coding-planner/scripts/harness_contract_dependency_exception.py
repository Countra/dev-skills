#!/usr/bin/env python3
"""specialized dependency exception 的独立语义校验。"""

from __future__ import annotations

from typing import Any

from harness_contract import (
    ValidationIssue,
    check_closed_object,
    check_references,
    check_string,
    check_string_list,
)
from harness_contract_dependency_common import dependency_issue


EXCEPTION_FIELDS = {
    "mainstream_baseline_key",
    "unmet_requirement_ids",
    "why_baseline_fails",
    "accepted_risks",
    "mitigations",
    "rollback",
    "user_acceptance_required",
}


def validate_specialized_exception(
    value: Any,
    path: str,
    *,
    selected_class: str,
    candidates: dict[str, dict[str, Any]],
    requirement_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    if selected_class != "specialized-exception":
        if value is not None:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
                path,
                "非 specialized selection 不得声明 exception。",
                "将 exception 设为 null。",
            )
        return
    if not check_closed_object(value, path, EXCEPTION_FIELDS, issues):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
            path,
            "specialized selection 缺少完整 exception object。",
            "记录 mainstream baseline、未满足需求、风险、缓解和回滚。",
        )
        return
    assert isinstance(value, dict)
    baseline_key = value.get("mainstream_baseline_key")
    if not check_string(baseline_key, f"{path}.mainstream_baseline_key", issues):
        baseline_key = ""
    baseline = candidates.get(str(baseline_key))
    if not baseline or baseline.get("disposition") != "baseline":
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
            f"{path}.mainstream_baseline_key",
            "mainstream baseline 必须是同一 decision 的 baseline candidate。",
            "保留并引用被特化方案超越的主流基线。",
        )
    elif baseline.get("selection_class") != "ecosystem-mainstream":
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
            f"{path}.mainstream_baseline_key",
            "baseline candidate 必须标记 ecosystem-mainstream。",
            "修正候选分类。",
        )
    unmet = check_string_list(
        value.get("unmet_requirement_ids"),
        f"{path}.unmet_requirement_ids",
        issues,
        allow_empty=False,
    )
    if len(unmet) > 20:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
            f"{path}.unmet_requirement_ids",
            "exception REQ refs 超过 20 项。",
            "拆分 selection decision。",
        )
    check_references(unmet, requirement_ids, f"{path}.unmet_requirement_ids", issues)
    for field in ("why_baseline_fails", "rollback"):
        check_string(value.get(field), f"{path}.{field}", issues)
    for field in ("accepted_risks", "mitigations"):
        values = check_string_list(
            value.get(field),
            f"{path}.{field}",
            issues,
            allow_empty=False,
        )
        if len(values) > 20:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
                f"{path}.{field}",
                "exception 列表超过 20 项。",
                "合并重复项并保留关键风险。",
            )
    if value.get("user_acceptance_required") is not True:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
            f"{path}.user_acceptance_required",
            "specialized exception 必须由用户批准风险接受。",
            "设为 true，并在 plan approval 中明确该风险。",
        )
