#!/usr/bin/env python3
"""结构化 dependency evidence receipt 的封闭校验。"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from harness_contract import (
    ValidationIssue,
    check_closed_object,
    check_references,
    check_string_list,
)
from harness_contract_dependencies import (
    SELECTION_CLASSES,
    safe_evidence_url,
)
from harness_contract_dependency_common import dependency_issue
from harness_contract_dependency_signals import (
    CORE_SIGNAL_NAMES,
    TRUST_SIGNAL_NAMES,
    check_bounded_string,
    parse_iso_date,
    validate_hard_gates,
    validate_signal,
)


ROOT_FIELDS = {"observed_at", "decisions"}
DECISION_FIELDS = {
    "decision_id",
    "necessity",
    "candidates",
    "excluded_alternatives",
    "decision_reason",
    "exception",
}
NECESSITY_FIELDS = {"result", "existing_or_standard_option", "evidence"}
CANDIDATE_FIELDS = {
    "key",
    "package",
    "source_repository",
    "selected_version",
    "selection_class",
    "disposition",
    "hard_gates",
    "trust_signals",
    "fit_summary",
    "risks",
}
NECESSITY_RESULTS = {
    "dependency-required",
    "existing-sufficient",
    "standard-or-official-sufficient",
}


def validate_candidate(
    value: Any,
    path: str,
    *,
    expected: dict[str, Any] | None,
    observed_at: date | None,
    approval_mode: bool,
    issues: list[ValidationIssue],
) -> tuple[str, dict[str, Any] | None]:
    if not check_closed_object(value, path, CANDIDATE_FIELDS, issues):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "candidate receipt 结构不完整。",
            "补齐 identity、hard gates、trust signals、fit 和 risks。",
        )
        return "", None
    assert isinstance(value, dict)
    key = str(value.get("key", ""))
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", key):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.key",
            "candidate key 格式无效。",
            "使用稳定的小写 key。",
        )
    for field in ("package", "selected_version", "fit_summary"):
        check_bounded_string(value.get(field), f"{path}.{field}", issues)
    safe_evidence_url(value.get("source_repository"), f"{path}.source_repository", issues)
    selection_class = value.get("selection_class")
    if selection_class not in SELECTION_CLASSES:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.selection_class",
            "未知 candidate selection class。",
            "使用受控 selection class。",
        )
    disposition = value.get("disposition")
    if disposition not in {"selected", "rejected", "baseline"}:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.disposition",
            "未知 candidate disposition。",
            "使用 selected、rejected 或 baseline。",
        )
    risks = check_string_list(value.get("risks"), f"{path}.risks", issues)
    if len(risks) > 20:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.risks",
            "candidate risks 超过 20 项。",
            "合并重复风险并保留摘要。",
        )
    hard_results = validate_hard_gates(value.get("hard_gates"), f"{path}.hard_gates", issues)
    signals = value.get("trust_signals")
    signal_results: dict[str, str] = {}
    if check_closed_object(signals, f"{path}.trust_signals", TRUST_SIGNAL_NAMES, issues):
        assert isinstance(signals, dict)
        maximum_age = int(expected.get("freshness_max_age_days", 0)) if expected else 90
        for name in sorted(TRUST_SIGNAL_NAMES):
            result, _, signal_date = validate_signal(
                name,
                signals.get(name),
                f"{path}.trust_signals.{name}",
                maximum_age,
                approval_mode and disposition == "selected",
                issues,
            )
            signal_results[name] = result
            if observed_at and signal_date and signal_date > observed_at:
                dependency_issue(
                    issues,
                    "TASK_DEPENDENCY_EVIDENCE_INVALID",
                    f"{path}.trust_signals.{name}.as_of",
                    "signal 日期晚于 artifact observed_at。",
                    "同步 receipt observation date。",
                )
    else:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.trust_signals",
            "candidate 缺少必需 trust signals。",
            "补齐五项核心信号和四项适配/成本信号。",
        )
    if disposition == "selected":
        if expected is None:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_PLAN_DRIFT",
                path,
                "artifact 包含 contract 未声明的 selected candidate。",
                "同步 DEP decision。",
            )
        else:
            for candidate_field, contract_field in (
                ("package", "package"),
                ("source_repository", "source_repository"),
                ("selected_version", "selected_version"),
                ("selection_class", "selection_class"),
            ):
                if value.get(candidate_field) != expected.get(contract_field):
                    dependency_issue(
                        issues,
                        "TASK_DEPENDENCY_PLAN_DRIFT",
                        f"{path}.{candidate_field}",
                        "selected candidate 与 contract 不一致。",
                        "以批准 contract 的 identity/version/class 为准。",
                    )
        for gate_name, result in hard_results.items():
            allowed_exception = (
                result == "exception"
                and gate_name in {"stable_support", "lifecycle"}
                and selection_class == "specialized-exception"
            )
            if result != "pass" and not allowed_exception:
                dependency_issue(
                    issues,
                    "TASK_DEPENDENCY_HARD_GATE_FAILED",
                    f"{path}.hard_gates.{gate_name}",
                    "selected candidate 未通过 hard gate。",
                    "淘汰候选、修复风险或进入允许的专用例外。",
                )
        if any(signal_results.get(name) == "fail" for name in CORE_SIGNAL_NAMES):
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
                f"{path}.trust_signals",
                "selected candidate 的核心可信度信号包含 fail。",
                "重新选择或修复失败信号。",
            )
        if any(result == "concern" for result in signal_results.values()) and not risks:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
                f"{path}.risks",
                "selected candidate 的 concern 未映射风险。",
                "记录风险和缓解。",
            )
    return key, value


def validate_decision_receipt(
    value: Any,
    path: str,
    *,
    expected: dict[str, Any],
    observed_at: date | None,
    requirement_ids: set[str],
    approval_mode: bool,
    issues: list[ValidationIssue],
) -> str:
    if not check_closed_object(value, path, DECISION_FIELDS, issues):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "decision receipt 结构不完整。",
            "补齐 necessity、candidates、排除依据、reason 和 exception。",
        )
        return ""
    assert isinstance(value, dict)
    decision_id = str(value.get("decision_id", ""))
    if decision_id != expected.get("id"):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_PLAN_DRIFT",
            f"{path}.decision_id",
            "artifact decision ID 与 contract 不一致。",
            "同步 DEP ID。",
        )
    necessity = value.get("necessity")
    if check_closed_object(necessity, f"{path}.necessity", NECESSITY_FIELDS, issues):
        assert isinstance(necessity, dict)
        if necessity.get("result") not in NECESSITY_RESULTS:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_INVALID",
                f"{path}.necessity.result",
                "未知 necessity result。",
                "使用 Dependency Selection Gate 定义的必要性结果。",
            )
        check_bounded_string(
            necessity.get("existing_or_standard_option"),
            f"{path}.necessity.existing_or_standard_option",
            issues,
        )
        evidence = check_string_list(
            necessity.get("evidence"),
            f"{path}.necessity.evidence",
            issues,
            allow_empty=False,
        )
        if len(evidence) > 20:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_INVALID",
                f"{path}.necessity.evidence",
                "necessity evidence refs 超过 20 项。",
                "保留直接支撑必要性的 REQ。",
            )
        check_references(evidence, requirement_ids, f"{path}.necessity.evidence", issues)
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 5:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.candidates",
            "候选数量必须为 1-5。",
            "保留同类 baseline 与领先候选。",
        )
        candidates = []
    candidate_map: dict[str, dict[str, Any]] = {}
    selected: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        candidate_expected = (
            expected
            if isinstance(candidate, dict) and candidate.get("disposition") == "selected"
            else None
        )
        key, validated = validate_candidate(
            candidate,
            f"{path}.candidates[{index}]",
            expected=candidate_expected,
            observed_at=observed_at,
            approval_mode=approval_mode,
            issues=issues,
        )
        if key in candidate_map:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_INVALID",
                f"{path}.candidates[{index}].key",
                "candidate key 重复。",
                "使用唯一 key。",
            )
        elif key and validated:
            candidate_map[key] = validated
        if validated and validated.get("disposition") == "selected":
            selected.append(validated)
    if len(selected) != 1:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.candidates",
            "每个 DEP decision 必须恰好一个 selected candidate。",
            "修正 disposition。",
        )
    excluded = check_string_list(
        value.get("excluded_alternatives"),
        f"{path}.excluded_alternatives",
        issues,
    )
    if len(excluded) > 20:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.excluded_alternatives",
            "排除依据超过 20 项。",
            "合并同类排除理由。",
        )
    if len(candidates) == 1 and not excluded:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            f"{path}.excluded_alternatives",
            "单一候选必须解释其它方案为何不合理。",
            "记录排除依据。",
        )
    check_bounded_string(value.get("decision_reason"), f"{path}.decision_reason", issues)
    selected_class = str(selected[0].get("selection_class")) if selected else ""
    from harness_contract_dependency_exception import validate_specialized_exception

    validate_specialized_exception(
        value.get("exception"),
        f"{path}.exception",
        selected_class=selected_class,
        candidates=candidate_map,
        requirement_ids=requirement_ids,
        issues=issues,
    )
    return decision_id


def validate_dependency_artifact(
    artifact_path: Path,
    expected_decisions: list[dict[str, Any]],
    requirement_ids: set[str],
    mode: str,
    issues: list[ValidationIssue],
) -> None:
    try:
        if artifact_path.stat().st_size > 1_000_000:
            raise ValueError("artifact 超过 1 MB")
        value = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            str(artifact_path),
            f"无法解析 dependency artifact：{exc}",
            "使用 UTF-8 closed JSON receipt。",
        )
        return
    if not check_closed_object(value, "$dependency_artifact", ROOT_FIELDS, issues):
        return
    assert isinstance(value, dict)
    observed_at = parse_iso_date(
        value.get("observed_at"),
        "$dependency_artifact.observed_at",
        issues,
    )
    receipts = value.get("decisions")
    if not isinstance(receipts, list) or len(receipts) > 50:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            "$dependency_artifact.decisions",
            "decisions 必须是最多 50 项的数组。",
            "拆分无关选型任务。",
        )
        return
    expected_map = {str(item.get("id")): item for item in expected_decisions}
    actual_ids: list[str] = []
    for index, receipt in enumerate(receipts):
        receipt_id = receipt.get("decision_id") if isinstance(receipt, dict) else None
        expected = expected_map.get(str(receipt_id))
        if expected is None:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_PLAN_DRIFT",
                f"$dependency_artifact.decisions[{index}]",
                "artifact 包含 contract 未声明的 DEP decision。",
                "移除漂移 receipt 或同步 contract。",
            )
            continue
        actual_ids.append(
            validate_decision_receipt(
                receipt,
                f"$dependency_artifact.decisions[{index}]",
                expected=expected,
                observed_at=observed_at,
                requirement_ids=requirement_ids,
                approval_mode=mode == "approval",
                issues=issues,
            )
        )
    if set(actual_ids) != set(expected_map) or len(actual_ids) != len(set(actual_ids)):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_PLAN_DRIFT",
            "$dependency_artifact.decisions",
            "artifact 与 contract 的 DEP decisions 不完全一致。",
            "每个 decision 保留一个且仅一个 receipt。",
        )
