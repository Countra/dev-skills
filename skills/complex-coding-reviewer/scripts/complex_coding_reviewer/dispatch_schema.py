"""Reviewer dispatch 的封闭字段与基础值校验。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .errors import ReviewError


POLICIES = {"strict", "conditional", "disabled"}
CAPABILITY_STATUSES = {"available", "unavailable", "policy-disabled"}
LIFECYCLE_STATUSES = {"completed", "fallback", "failed", "blocked"}
TIMEOUT_CLASSES = {"standard", "high-risk"}
REQUIRED_TOOLS = ("close_agent", "spawn_agent", "wait_agent")
SCHEMA_REPAIR_TOOL = "send_input"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
AGENT_ID = re.compile(r"^[^\s]+$")

PREPARATION_FIELDS = {
    "kind",
    "dispatch_id",
    "review_id",
    "profile",
    "scope",
    "policy",
    "capability",
    "inputs",
    "attempt",
    "max_attempts",
    "timeout_class",
    "timeout_seconds",
    "prepared_at",
    "decision",
    "prompt",
    "prompt_digest",
    "reviewer_skill_digest",
    "previous_dispatch_ref",
    "previous_dispatch_digest",
    "recursive_delegation_allowed",
    "parent_judgment_included",
}
CAPABILITY_FIELDS = {
    "status",
    "tool_family",
    "required_tools",
    "available_tools",
    "missing_tools",
}
INPUT_FIELDS = {
    "target_ref",
    "target_digest",
    "context_ref",
    "context_digest",
    "brief_ref",
    "brief_digest",
    "package_ref",
    "package_digest",
    "semantic_result_ref",
}
FINAL_FIELDS = {
    "kind",
    "dispatch_id",
    "review_id",
    "profile",
    "scope",
    "policy",
    "capability",
    "inputs",
    "preparation_ref",
    "preparation_digest",
    "prompt_digest",
    "reviewer_skill_digest",
    "previous_dispatch_ref",
    "previous_dispatch_digest",
    "attempt",
    "max_attempts",
    "timeout_class",
    "timeout_seconds",
    "decision",
    "lifecycle",
    "reviewer",
    "prepared_at",
    "finalized_at",
}
OUTCOME_FIELDS = {
    "status",
    "agent_id",
    "fork_context",
    "started_at",
    "completed_at",
    "schema_repair_count",
    "context_expansion_requested",
    "parent_judgment_included",
    "recursive_delegation_allowed",
    "failure",
    "close",
    "fallback",
}
FAILURE_FIELDS = {"code", "reason", "retryable"}
CLOSE_FIELDS = {"required", "attempted", "status", "closed_at", "error"}
FALLBACK_FIELDS = {"mode", "reason_code", "reason"}
REVIEWER_FIELDS = {"mode", "identity", "independence_claim", "capability_limits"}

MANDATORY_EXTERNAL_LIMITS = [
    "同模型相关性（same-model-correlation）可能导致相关性偏差。",
    "继承权限与沙箱不构成独立安全边界（inherited-permissions-not-security-boundary）。",
    "Reviewer 未运行测试（tests-not-run-by-reviewer），仅消费冻结证据。",
    "本结果不是人类审计（not-human-audit）。",
    "静态 validator 无法独立证明宿主真实调用过工具（host-tool-call-not-statically-provable）。",
]


def closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "值必须是 object。", path=path)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            f"封闭字段不匹配：unknown={unknown}, missing={missing}",
            path=path,
        )
    return value


def nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "值必须是非空字符串。",
            path=path,
        )
    return value


def nullable_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return nonempty(value, path)


def positive_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "值必须是正整数。",
            path=path,
        )
    return value


def timestamp(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    text = nonempty(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "时间戳必须是 RFC3339。",
            path=path,
        ) from exc
    if parsed.tzinfo is None:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "时间戳必须包含时区。",
            path=path,
        )
    return text


def digest(value: Any, path: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "摘要必须是小写 SHA-256。",
            path=path,
        )
    return value


def string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "值必须是非空字符串数组。",
            path=path,
        )
    if value != sorted(set(value)):
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "工具列表必须排序且去重。",
            path=path,
        )
    return value
