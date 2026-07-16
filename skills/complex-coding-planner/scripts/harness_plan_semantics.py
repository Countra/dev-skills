#!/usr/bin/env python3
"""approval plan 的门禁语义与 dependency 摘要一致性校验。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness_contract import ValidationIssue, add_issue


DEP_ID_PATTERN = re.compile(r"\bDEP-\d{2,}\b")
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
URL_PATTERN = re.compile(r"https?://[^\s)>|]+", re.IGNORECASE)

GATE_RESULTS = {
    "调研门禁": ("Research result", {"passed", "not-applicable"}),
    "规范发现门禁": ("Standards result", {"passed", "not-applicable"}),
    "开发质量门禁": ("Development quality result", {"passed"}),
    "方案质量门禁": ("Quality result", {"passed"}),
    "就绪门禁": (
        "Readiness result",
        {"ready_for_review"},
    ),
}


def plan_section(plan: str, name: str) -> str:
    match = re.search(rf"^##\s+.*{re.escape(name)}.*$", plan, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    following = re.search(r"^##\s+", plan[start:], re.MULTILINE)
    end = start + following.start() if following else len(plan)
    return plan[start:end]


def controlled_value(text: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}[^\n`]*`([^`]+)`",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip().lower() if match else ""


def substantive_gate_lines(text: str, result_label: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or result_label.lower() in line.lower():
            continue
        if re.fullmatch(r"\|?(?:\s*:?-+:?\s*\|)+", line):
            continue
        normalized = re.sub(r"[`*_#>|\-]", "", line).strip().lower()
        if normalized in {"complete", "completed", "passed", "none", "无"}:
            continue
        if len(normalized) >= 12:
            lines.append(line)
    return lines


def has_evidence_anchor(lines: list[str]) -> bool:
    combined = "\n".join(lines)
    return bool(
        re.search(
            r"(?:\||https?://|\bART-\d+|\bVAL-\d+|\bSTG-\d+|"
            r"证据|evidence|source|来源|\.md\b|\.json\b)",
            combined,
            re.IGNORECASE,
        )
    )


def has_decision_reasoning(lines: list[str]) -> bool:
    combined = URL_PATTERN.sub(" ", "\n".join(lines))
    combined = re.sub(r"\b(?:ART|VAL|STG|REQ|AC|NFR)-\d+\b", " ", combined)
    normalized = re.sub(r"[`*_#>|\-\s]", "", combined)
    if len(normalized) < 40:
        return False
    return bool(
        re.search(
            r"决策|原因|影响|限制|适用|验证|标准|风险|结论|"
            r"decision|reason|impact|limit|appli|valid|standard|risk",
            combined,
            re.IGNORECASE,
        )
    )


def validate_gate_semantics(plan: str, issues: list[ValidationIssue]) -> None:
    for gate, (result_label, allowed_results) in GATE_RESULTS.items():
        gate_text = plan_section(plan, gate)
        result = controlled_value(gate_text, result_label)
        result_base = "passed" if result.startswith("passed") else result
        if result_base not in allowed_results:
            add_issue(
                issues,
                "TASK_PLAN_GATE_RESULT_INVALID",
                f"$plan.{gate}",
                f"{gate} 缺少受控通过结果。",
                f"填写 {result_label} 的受控值并保留证据。",
            )
        substantive = substantive_gate_lines(gate_text, result_label)
        if (
            len(substantive) < 3
            or not has_evidence_anchor(substantive)
            or not has_decision_reasoning(substantive)
        ):
            add_issue(
                issues,
                "TASK_PLAN_GATE_EMPTY",
                f"$plan.{gate}",
                f"{gate} 只有结论、URL 或形式文本，没有最低语义证据。",
                "补充决策依据、结构化引用以及对实施或验证的影响。",
            )


def validate_review_handoff(
    plan: str,
    contract: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    gate_text = plan_section(plan, "正式方案审查")
    artifacts = contract.get("artifacts")
    review_paths = (
        [
            item.get("path")
            for item in artifacts
            if isinstance(item, dict)
            and item.get("kind") == "review"
            and isinstance(item.get("path"), str)
        ]
        if isinstance(artifacts, list)
        else []
    )
    expected = ["plan-review", "managed-plan", "review_validate.py", *review_paths]
    missing = [value for value in expected if value not in gate_text]
    if missing:
        add_issue(
            issues,
            "TASK_PLAN_REVIEW_HANDOFF_DRIFT",
            "$plan.正式方案审查",
            f"正式方案审查缺少 Reviewer handoff：{', '.join(missing)}。",
            "同步 profile、scope、当前 receipt 路径和公共 validator。",
        )
    if re.search(r"(?:Review result|审查结论)\s*[:：]", gate_text, re.IGNORECASE):
        add_issue(
            issues,
            "TASK_PLAN_REVIEW_VERDICT_DUPLICATED",
            "$plan.正式方案审查",
            "计划正文不得复制正式 review verdict。",
            "只让 canonical JSON receipt 承载 verdict，由 approval checker 消费。",
        )


def validate_online_research(
    contract: dict[str, Any],
    context: str,
    issues: list[ValidationIssue],
) -> None:
    research = contract.get("research")
    if not isinstance(research, dict) or research.get("mode") != "online-required":
        return
    checks = {
        "URL": bool(URL_PATTERN.search(context)),
        "observation date": bool(DATE_PATTERN.search(context)),
        "evidence window": bool(
            re.search(r"窗口|近\s*\d+|\d+\s*天|window|last\s+\d+", context, re.IGNORECASE)
        ),
        "authority": bool(re.search(r"官方|一手|official|primary", context, re.IGNORECASE)),
        "applicability": bool(
            re.search(r"影响|限制|适用|impact|limit|applicability", context, re.IGNORECASE)
        ),
        "artifact receipt": bool(
            re.search(r"\bART-\d+\b|artifacts?[/\\].+\.(?:md|json)\b", context)
        ),
    }
    missing = [label for label, passed in checks.items() if not passed]
    if missing:
        add_issue(
            issues,
            "TASK_PLAN_RESEARCH_EVIDENCE_INCOMPLETE",
            "$plan.调研门禁",
            f"online research 缺少证据元数据：{', '.join(missing)}。",
            "为来源记录观察日期、authority、适用限制和方案影响。",
        )


def dependency_mode(section_text: str) -> str:
    for label in ("Selection mode", "本任务模式"):
        value = controlled_value(section_text, label)
        if value:
            return value
    return ""


def dependency_result(section_text: str) -> str:
    return controlled_value(section_text, "Dependency selection result")


def decision_values(decision: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in (
        "package",
        "selected_version",
        "version_policy",
        "evidence_artifact_id",
    ):
        value = decision.get(field)
        if isinstance(value, str):
            values.append(value)
    for field in ("manifest_paths", "validation_ids"):
        field_values = decision.get(field)
        if isinstance(field_values, list):
            values.extend(str(value) for value in field_values if isinstance(value, str))
    return values


def validate_dependency_plan(
    plan: str,
    contract: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    gate_text = plan_section(plan, "依赖选型门禁")
    selection = contract.get("dependency_selection")
    if not gate_text:
        if selection is not None:
            add_issue(
                issues,
                "TASK_PLAN_MISSING_SECTION",
                "$plan.依赖选型门禁",
                "contract 声明 dependency_selection，但计划缺少对应门禁。",
                "按 execution-plan 模板补齐 Dependency Selection Gate。",
            )
        return

    actual_mode = dependency_mode(gate_text)
    if not isinstance(selection, dict):
        if actual_mode != "none":
            add_issue(
                issues,
                "TASK_DEPENDENCY_PLAN_DRIFT",
                "$plan.依赖选型门禁",
                "计划声明非 none 依赖模式，但 contract 没有 dependency_selection。",
                "补齐 closed contract 或修正为 none。",
            )
        return

    expected_mode = selection.get("mode")
    if actual_mode != expected_mode:
        add_issue(
            issues,
            "TASK_DEPENDENCY_PLAN_DRIFT",
            "$plan.依赖选型门禁",
            f"计划 mode={actual_mode or 'missing'}，contract mode={expected_mode}。",
            "同步 plan 与 dependency_selection.mode。",
        )
    decisions = selection.get("decisions", [])
    expected_ids = {
        str(item.get("id"))
        for item in decisions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(decisions, list) else set()
    actual_ids = set(DEP_ID_PATTERN.findall(gate_text))
    if actual_ids != expected_ids:
        add_issue(
            issues,
            "TASK_DEPENDENCY_PLAN_DRIFT",
            "$plan.依赖选型门禁",
            "计划与 contract 的 DEP ID 集合不一致。",
            "每个 decision 在门禁摘要中出现一次。",
        )
    if isinstance(decisions, list):
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            for value in decision_values(decision):
                if value not in gate_text:
                    add_issue(
                        issues,
                        "TASK_DEPENDENCY_PLAN_DRIFT",
                        "$plan.依赖选型门禁",
                        f"计划未解释批准 dependency 值：{value}",
                        "同步 identity、version policy、manifest、artifact 和 validation。",
                    )
    result = dependency_result(gate_text)
    expected_result = "not-applicable" if expected_mode == "none" else "passed"
    if result != expected_result:
        add_issue(
            issues,
            "TASK_PLAN_GATE_RESULT_INVALID",
            "$plan.依赖选型门禁",
            f"dependency result 应为 {expected_result}。",
            "填写受控 result，blocked 计划不得请求 approval。",
        )
