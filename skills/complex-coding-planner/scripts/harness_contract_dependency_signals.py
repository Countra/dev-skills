#!/usr/bin/env python3
"""dependency hard gates 与 trust signals 的 receipt 校验。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from harness_contract import (
    ValidationIssue,
    check_closed_object,
    check_string,
    check_string_list,
)
from harness_contract_dependencies import safe_evidence_url
from harness_contract_dependency_common import dependency_issue


HARD_GATE_NAMES = {
    "authenticity",
    "compatibility",
    "stable_support",
    "lifecycle",
    "security",
    "license",
    "reproducibility",
}
TRUST_SIGNAL_NAMES = {
    "stable_version",
    "adoption_scale",
    "update_recency",
    "maintenance_activity",
    "adoption_trend",
    "api_and_project_fit",
    "ecosystem_and_docs",
    "transitive_and_provenance",
    "operational_cost",
}
CORE_SIGNAL_NAMES = {
    "stable_version",
    "adoption_scale",
    "update_recency",
    "maintenance_activity",
    "adoption_trend",
}
HARD_GATE_FIELDS = {"result", "source"}
SIGNAL_FIELDS = {
    "result",
    "value",
    "source_type",
    "url",
    "as_of",
    "window",
    "caveat",
    "proxy_sources",
}
SIGNAL_REQUIRED_FIELDS = SIGNAL_FIELDS - {"proxy_sources"}

HARD_GATE_RESULTS = {"pass", "fail", "exception", "unavailable"}
SIGNAL_RESULTS = {"pass", "concern", "fail", "insufficient-data"}
SOURCE_TYPES = {"project", "official", "registry", "primary", "mixed", "external"}
WINDOWS = {"snapshot", "6m", "12m", "24m"}


def parse_iso_date(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "必须是严格 YYYY-MM-DD 日期。",
            "记录真实 observation date。",
        )
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "日期无效。",
            "使用真实日历日期。",
        )
        return None
    if parsed > date.today():
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "观察日期不能位于未来。",
            "修正时钟或 observation date。",
        )
        return None
    return parsed


def check_bounded_string(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
    *,
    maximum: int = 4000,
) -> str:
    if not check_string(value, path, issues):
        return ""
    result = str(value)
    if len(result) > maximum:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "evidence 字符串超过允许长度。",
            "保存摘要并把大内容留在来源中。",
        )
        return ""
    return result


def validate_hard_gates(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
) -> dict[str, str]:
    results: dict[str, str] = {}
    if not check_closed_object(value, path, HARD_GATE_NAMES, issues):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_HARD_GATE_FAILED",
            path,
            "candidate 缺少必需 hard gates。",
            "补齐七项 hard-gate receipt。",
        )
        return results
    assert isinstance(value, dict)
    for name in sorted(HARD_GATE_NAMES):
        gate_path = f"{path}.{name}"
        receipt = value.get(name)
        if not check_closed_object(receipt, gate_path, HARD_GATE_FIELDS, issues):
            continue
        assert isinstance(receipt, dict)
        result = receipt.get("result")
        if result not in HARD_GATE_RESULTS:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_INVALID",
                f"{gate_path}.result",
                "未知 hard-gate result。",
                "使用 pass、fail、exception 或 unavailable。",
            )
        else:
            results[name] = str(result)
        safe_evidence_url(receipt.get("source"), f"{gate_path}.source", issues)
    return results


def validate_signal(
    name: str,
    value: Any,
    path: str,
    maximum_age: int,
    approval_mode: bool,
    issues: list[ValidationIssue],
) -> tuple[str, str, date | None]:
    if not check_closed_object(
        value,
        path,
        SIGNAL_FIELDS,
        issues,
        required=SIGNAL_REQUIRED_FIELDS,
    ):
        return "", "", None
    assert isinstance(value, dict)
    result = value.get("result")
    if result not in SIGNAL_RESULTS:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.result",
            "未知 trust-signal result。",
            "使用 pass、concern、fail 或 insufficient-data。",
        )
        result = ""
    if value.get("source_type") not in SOURCE_TYPES:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.source_type",
            "未知 evidence source type。",
            "使用 project、official、registry、primary、mixed 或 external。",
        )
    signal_value = check_bounded_string(value.get("value"), f"{path}.value", issues)
    safe_evidence_url(value.get("url"), f"{path}.url", issues)
    observed = parse_iso_date(value.get("as_of"), f"{path}.as_of", issues)
    window = value.get("window")
    if window not in WINDOWS:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.window",
            "未知 evidence window。",
            "使用 snapshot、6m、12m 或 24m。",
        )
    if name == "adoption_trend" and window == "snapshot":
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.window",
            "adoption trend 需要 6/12/24 月窗口。",
            "提供历史序列或代理窗口。",
        )
    if name == "maintenance_activity" and window not in {"12m", "24m"}:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.window",
            "maintenance 至少需要 12 个月观察窗口。",
            "使用 12m 或 24m。",
        )
    check_bounded_string(value.get("caveat"), f"{path}.caveat", issues)
    proxies = check_string_list(
        value.get("proxy_sources", []),
        f"{path}.proxy_sources",
        issues,
    )
    if len(proxies) > 4:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.proxy_sources",
            "trend proxies 最多允许 4 项。",
            "保留最有区分力的独立代理。",
        )
    if name == "adoption_trend" and result == "insufficient-data":
        if len(set(proxies)) < 2:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
                f"{path}.proxy_sources",
                "趋势缺少历史序列时至少需要两个独立代理。",
                "补充不同来源或不同指标的两个 proxy URLs。",
            )
        for index, proxy in enumerate(proxies):
            safe_evidence_url(proxy, f"{path}.proxy_sources[{index}]", issues)
    elif proxies:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_SIGNAL_INCOMPLETE",
            f"{path}.proxy_sources",
            "proxy_sources 只用于 insufficient-data adoption trend。",
            "移除无关代理字段。",
        )
    if approval_mode and observed and (date.today() - observed).days > maximum_age:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_STALE",
            f"{path}.as_of",
            f"evidence 超过批准 freshness 上限 {maximum_age} 天。",
            "在线刷新 receipt 后再请求批准。",
        )
    return str(result), signal_value, observed
