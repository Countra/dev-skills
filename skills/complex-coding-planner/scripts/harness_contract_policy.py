#!/usr/bin/env python3
"""Research、approval 与风险 profile 的契约规则。"""

from __future__ import annotations

from typing import Any

from harness_contract import (
    APPROVAL_POLICY_FIELDS,
    ValidationIssue,
    add_issue,
    check_closed_object,
    check_references,
    check_string_list,
)


def invalid_type(
    issues: list[ValidationIssue],
    path: str,
    message: str,
) -> None:
    add_issue(
        issues,
        "TASK_CONTRACT_INVALID_TYPE",
        path,
        message,
        "按 task-contract.md 使用正确 JSON 类型。",
    )


def validate_policy_and_profile(
    contract: dict[str, Any],
    *,
    profile: Any,
    artifact_ids: set[str],
    artifact_kinds: set[str],
    artifact_count: int,
    stage_ids: set[str],
    high_risk: bool,
    mode: str,
    issues: list[ValidationIssue],
) -> None:
    research = contract.get("research")
    research_fields = {"mode", "evidence_artifact_ids", "unresolved"}
    if check_closed_object(research, "$.research", research_fields, issues):
        modes = {"none", "local-only", "online-required", "blocked-by-access"}
        if research.get("mode") not in modes:
            add_issue(
                issues,
                "TASK_CONTRACT_INVALID_VALUE",
                "$.research.mode",
                "未知 research mode。",
                "使用 task-contract.md 定义的模式。",
            )
        evidence_ids = check_string_list(
            research.get("evidence_artifact_ids"),
            "$.research.evidence_artifact_ids",
            issues,
        )
        check_references(
            evidence_ids,
            artifact_ids,
            "$.research.evidence_artifact_ids",
            issues,
        )
        unresolved = research.get("unresolved")
        if not isinstance(unresolved, list):
            invalid_type(issues, "$.research.unresolved", "必须是数组。")
        elif mode == "approval" and unresolved:
            add_issue(
                issues,
                "TASK_CONTRACT_UNRESOLVED",
                "$.research.unresolved",
                "approval 模式不允许未解决项。",
                "关闭、转 blocker 或停止在 discovery-first。",
            )

    policy = contract.get("approval_policy")
    if check_closed_object(policy, "$.approval_policy", APPROVAL_POLICY_FIELDS, issues):
        for field in APPROVAL_POLICY_FIELDS:
            if not isinstance(policy.get(field), bool):
                invalid_type(issues, f"$.approval_policy.{field}", "必须是 boolean。")
            elif policy[field] is not True:
                add_issue(
                    issues,
                    "TASK_CONTRACT_APPROVAL_POLICY_WEAK",
                    f"$.approval_policy.{field}",
                    "managed task 不得弱化显式授权门禁。",
                    "保持 implementation、commit、external write 和 elevated tool 显式授权。",
                )
    check_string_list(
        contract.get("reapproval_triggers"),
        "$.reapproval_triggers",
        issues,
        allow_empty=False,
    )
    check_string_list(
        contract.get("stop_conditions"),
        "$.stop_conditions",
        issues,
        allow_empty=False,
    )

    required_kinds = {"architecture"} if profile == "standard" else set()
    if profile == "full":
        required_kinds = {
            "research",
            "standards",
            "architecture",
            "validation",
            "review",
        }
    elif high_risk:
        add_issue(
            issues,
            "TASK_CONTRACT_PROFILE_UNDERSCOPED",
            "$.plan_profile",
            "包含 high-risk stage 的 managed task 必须使用 full profile。",
            "升级为 full 并补齐独立 artifacts 与 critique。",
        )
    for kind in sorted(required_kinds - artifact_kinds):
        add_issue(
            issues,
            "TASK_CONTRACT_PROFILE_ARTIFACT_MISSING",
            "$.artifacts",
            f"{profile} profile 缺少 {kind} artifact。",
            "创建并索引 profile 必需 artifact。",
        )
    if profile == "lite" and artifact_count > 3:
        add_issue(
            issues,
            "TASK_CONTRACT_LITE_OVERHEAD",
            "$.artifacts",
            "lite profile artifact 过多。",
            "内联低风险证据或升级 profile。",
            level="warning",
        )
    stage_ranges = {"lite": (1, 3), "standard": (2, 5), "full": (3, 7)}
    if profile in stage_ranges:
        minimum, maximum = stage_ranges[profile]
        if not minimum <= len(stage_ids) <= maximum:
            add_issue(
                issues,
                "TASK_CONTRACT_PROFILE_STAGE_COUNT",
                "$.stages",
                f"{profile} profile 通常需要 {minimum}-{maximum} 个 stages，当前为 {len(stage_ids)}。",
                "合并/拆分阶段、调整 profile，或在计划中解释例外。",
                level="warning",
            )
