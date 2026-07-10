#!/usr/bin/env python3
"""任务契约的字段、引用、覆盖和 profile 规则。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_contract import (
    ROOT_FIELDS,
    STAGE_FIELDS,
    ValidationIssue,
    add_issue,
    check_closed_object,
    check_id,
    check_references,
    check_relative_path,
    check_string,
    check_string_list,
    collect_ids,
    graph_has_cycle,
)
from harness_contract_artifacts import validate_artifacts
from harness_contract_policy import validate_policy_and_profile


def invalid_value(
    issues: list[ValidationIssue],
    path: str,
    message: str,
    hint: str,
) -> None:
    add_issue(issues, "TASK_CONTRACT_INVALID_VALUE", path, message, hint)


def invalid_type(
    issues: list[ValidationIssue],
    path: str,
    message: str = "类型不符合任务契约。",
) -> None:
    add_issue(
        issues,
        "TASK_CONTRACT_INVALID_TYPE",
        path,
        message,
        "按 task-contract.md 使用正确 JSON 类型。",
    )


def validate_contract(
    contract: dict[str, Any],
    task_dir: Path,
    mode: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    check_closed_object(contract, "$", ROOT_FIELDS, issues)
    check_string(contract.get("task_id"), "$.task_id", issues)

    revision = contract.get("plan_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        invalid_value(issues, "$.plan_revision", "必须是从 1 开始的整数。", "设置有效修订号。")
    if contract.get("lifecycle_route") != "managed":
        invalid_value(
            issues,
            "$.lifecycle_route",
            "task bundle 只允许 managed。",
            "direct 任务不要创建 task bundle。",
        )
    profile = contract.get("plan_profile")
    if profile not in {"lite", "standard", "full"}:
        invalid_value(
            issues,
            "$.plan_profile",
            "必须是 lite、standard 或 full。",
            "按风险画像选择 profile。",
        )

    goal = contract.get("goal")
    if check_closed_object(goal, "$.goal", {"id", "summary"}, issues):
        check_id(goal.get("id"), "goal", "$.goal.id", issues)
        check_string(goal.get("summary"), "$.goal.summary", issues)

    requirements, requirement_ids = collect_ids(
        contract.get("requirements"), "requirement", "$.requirements", issues
    )
    for index, item in enumerate(requirements):
        path = f"$.requirements[{index}]"
        if check_closed_object(item, path, {"id", "priority", "summary"}, issues):
            if item.get("priority") not in {"must", "should", "could"}:
                invalid_value(
                    issues,
                    f"{path}.priority",
                    "优先级必须是 must、should 或 could。",
                    "选择受控优先级。",
                )
            check_string(item.get("summary"), f"{path}.summary", issues)

    acceptances, acceptance_ids = collect_ids(
        contract.get("acceptance_criteria"),
        "acceptance",
        "$.acceptance_criteria",
        issues,
    )
    acceptance_requirement_refs: dict[str, set[str]] = {}
    for index, item in enumerate(acceptances):
        path = f"$.acceptance_criteria[{index}]"
        if not check_closed_object(
            item,
            path,
            {"id", "requirement_ids", "summary"},
            issues,
        ):
            continue
        refs = set(
            check_string_list(
                item.get("requirement_ids"),
                f"{path}.requirement_ids",
                issues,
                allow_empty=False,
            )
        )
        check_references(refs, requirement_ids, f"{path}.requirement_ids", issues)
        if isinstance(item.get("id"), str):
            acceptance_requirement_refs[item["id"]] = refs
        check_string(item.get("summary"), f"{path}.summary", issues)

    nonfunctionals, nonfunctional_ids = collect_ids(
        contract.get("nonfunctional_requirements"),
        "nonfunctional",
        "$.nonfunctional_requirements",
        issues,
    )
    for index, item in enumerate(nonfunctionals):
        path = f"$.nonfunctional_requirements[{index}]"
        if check_closed_object(item, path, {"id", "summary"}, issues):
            check_string(item.get("summary"), f"{path}.summary", issues)

    artifacts, artifact_ids, artifact_kinds = validate_artifacts(
        contract,
        task_dir,
        mode,
        issues,
    )

    stages, stage_ids = collect_ids(
        contract.get("stages"), "stage", "$.stages", issues
    )
    stage_requirements: set[str] = set()
    stage_acceptances: set[str] = set()
    stage_nonfunctionals: set[str] = set()
    assigned_validations: set[str] = set()
    stage_validation_refs: dict[int, list[str]] = {}
    graph: dict[str, set[str]] = {}
    high_risk = False
    for index, item in enumerate(stages):
        path = f"$.stages[{index}]"
        if not check_closed_object(item, path, STAGE_FIELDS, issues):
            continue
        check_string(item.get("title"), f"{path}.title", issues)
        stage_id = str(item.get("id", ""))
        dependencies = set(
            check_string_list(item.get("depends_on"), f"{path}.depends_on", issues)
        )
        graph[stage_id] = dependencies
        check_references(dependencies, stage_ids, f"{path}.depends_on", issues)
        if stage_id in dependencies:
            add_issue(
                issues,
                "TASK_CONTRACT_STAGE_CYCLE",
                f"{path}.depends_on",
                "stage 不能依赖自身。",
                "删除自依赖。",
            )

        refs = set(
            check_string_list(
                item.get("requirement_ids"), f"{path}.requirement_ids", issues
            )
        )
        stage_requirements.update(refs)
        check_references(refs, requirement_ids, f"{path}.requirement_ids", issues)
        for field, known in (
            ("acceptance_ids", acceptance_ids),
            ("nonfunctional_ids", nonfunctional_ids),
        ):
            values = check_string_list(item.get(field), f"{path}.{field}", issues)
            check_references(values, known, f"{path}.{field}", issues)
            if field == "acceptance_ids":
                stage_acceptances.update(values)
            else:
                stage_nonfunctionals.update(values)
        stage_validation_refs[index] = check_string_list(
            item.get("validation_ids"),
            f"{path}.validation_ids",
            issues,
            allow_empty=False,
        )
        assigned_validations.update(stage_validation_refs[index])

        allowed = set(
            check_string_list(
                item.get("allowed_changes"),
                f"{path}.allowed_changes",
                issues,
                allow_empty=False,
            )
        )
        forbidden = set(
            check_string_list(
                item.get("forbidden_changes"),
                f"{path}.forbidden_changes",
                issues,
                allow_empty=False,
            )
        )
        for overlap in sorted(allowed & forbidden):
            add_issue(
                issues,
                "TASK_CONTRACT_SCOPE_CONFLICT",
                path,
                f"同时允许和禁止：{overlap}",
                "澄清 stage 修改边界。",
            )
        for field in ("entry_conditions", "exit_conditions"):
            check_string_list(
                item.get(field), f"{path}.{field}", issues, allow_empty=False
            )
        if item.get("risk") not in {"low", "medium", "high"}:
            invalid_value(
                issues,
                f"{path}.risk",
                "risk 必须是 low、medium 或 high。",
                "按影响和可逆性分级。",
            )
        high_risk = high_risk or item.get("risk") == "high"
        if item.get("commit_expectation") not in {"none", "stage", "final"}:
            invalid_value(
                issues,
                f"{path}.commit_expectation",
                "未知提交期望。",
                "使用 none、stage 或 final。",
            )
    if graph_has_cycle(graph):
        add_issue(
            issues,
            "TASK_CONTRACT_STAGE_CYCLE",
            "$.stages",
            "Stage DAG 包含循环依赖。",
            "调整 depends_on 形成有向无环图。",
        )

    validations, validation_ids = collect_ids(
        contract.get("validations"), "validation", "$.validations", issues
    )
    required_coverage: set[str] = set()
    required_validation_ids: set[str] = set()
    validation_kinds = {
        "test",
        "lint",
        "typecheck",
        "build",
        "smoke",
        "review",
        "manual",
        "other",
    }
    for index, item in enumerate(validations):
        path = f"$.validations[{index}]"
        fields = {"id", "kind", "required", "covers", "command", "evidence_path"}
        if not check_closed_object(item, path, fields, issues):
            continue
        if item.get("kind") not in validation_kinds:
            invalid_value(
                issues,
                f"{path}.kind",
                "未知 validation kind。",
                "使用受控 kind。",
            )
        if not isinstance(item.get("required"), bool):
            invalid_type(issues, f"{path}.required", "必须是 boolean。")
        covers = set(
            check_string_list(
                item.get("covers"), f"{path}.covers", issues, allow_empty=False
            )
        )
        check_references(
            covers,
            acceptance_ids | nonfunctional_ids,
            f"{path}.covers",
            issues,
        )
        if item.get("required") is True:
            required_coverage.update(covers)
            validation_id = item.get("id")
            if isinstance(validation_id, str) and validation_id in validation_ids:
                required_validation_ids.add(validation_id)
        check_string(item.get("command"), f"{path}.command", issues)
        check_relative_path(
            item.get("evidence_path"), f"{path}.evidence_path", task_dir, issues
        )
    for index, refs in stage_validation_refs.items():
        check_references(
            refs, validation_ids, f"$.stages[{index}].validation_ids", issues
        )

    must_ids = {
        str(item.get("id"))
        for item in requirements
        if item.get("priority") == "must"
    }
    acceptance_requirements = (
        set().union(*acceptance_requirement_refs.values())
        if acceptance_requirement_refs
        else set()
    )
    for requirement_id in sorted(must_ids - acceptance_requirements):
        add_issue(
            issues,
            "TASK_CONTRACT_UNCOVERED_REQUIREMENT",
            "$.acceptance_criteria",
            f"{requirement_id} 没有验收覆盖。",
            "增加引用该 requirement 的 AC。",
        )
    for requirement_id in sorted(must_ids - stage_requirements):
        add_issue(
            issues,
            "TASK_CONTRACT_UNCOVERED_REQUIREMENT",
            "$.stages",
            f"{requirement_id} 没有实施阶段覆盖。",
            "把 requirement 映射到 stage。",
        )
    for item_id in sorted((acceptance_ids | nonfunctional_ids) - required_coverage):
        add_issue(
            issues,
            "TASK_CONTRACT_UNCOVERED_ACCEPTANCE",
            "$.validations",
            f"{item_id} 没有 required validation 覆盖。",
            "增加 required VAL covers 引用。",
        )
    for item_id in sorted(acceptance_ids - stage_acceptances):
        add_issue(
            issues,
            "TASK_CONTRACT_UNCOVERED_STAGE_TRACE",
            "$.stages",
            f"{item_id} 没有 stage 归属。",
            "把 acceptance criterion 映射到实施 stage。",
        )
    for item_id in sorted(nonfunctional_ids - stage_nonfunctionals):
        add_issue(
            issues,
            "TASK_CONTRACT_UNCOVERED_STAGE_TRACE",
            "$.stages",
            f"{item_id} 没有 stage 归属。",
            "把 nonfunctional requirement 映射到验证它的 stage。",
        )
    for validation_id in sorted(required_validation_ids - assigned_validations):
        add_issue(
            issues,
            "TASK_CONTRACT_UNASSIGNED_VALIDATION",
            "$.stages",
            f"required validation 未分配到 stage：{validation_id}",
            "在执行该验证的 stage.validation_ids 中引用它。",
        )
    for path, values, label in (
        ("$.requirements", requirement_ids, "requirement"),
        ("$.acceptance_criteria", acceptance_ids, "acceptance criterion"),
        ("$.stages", stage_ids, "stage"),
        ("$.validations", validation_ids, "validation"),
    ):
        if not values:
            add_issue(
                issues,
                "TASK_CONTRACT_EMPTY_LIST",
                path,
                f"managed task 至少需要一个 {label}。",
                "补充可执行、可验证的定义。",
            )

    validate_policy_and_profile(
        contract,
        profile=profile,
        artifact_ids=artifact_ids,
        artifact_kinds=artifact_kinds,
        artifact_count=len(artifacts),
        stage_ids=stage_ids,
        high_risk=high_risk,
        mode=mode,
        issues=issues,
    )
    return issues
