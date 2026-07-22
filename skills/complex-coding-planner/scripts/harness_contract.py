#!/usr/bin/env python3
"""定义 compact managed task contract 的最小校验规则。"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RISKS = {"low", "medium", "high"}
RISK_RANK = {"low": 0, "medium": 1, "high": 2}
REVIEWS = {"none", "same-context", "independent"}
TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STAGE_ID = re.compile(r"^STG-[A-Z0-9][A-Z0-9-]*$")
VALIDATION_ID = re.compile(r"^VAL-[A-Z0-9][A-Z0-9-]*$")

CONTRACT_FIELDS = {
    "task_id",
    "plan_revision",
    "risk",
    "scope",
    "stages",
    "validations",
    "final_review",
    "permissions_requested",
}
STAGE_FIELDS = {
    "id",
    "title",
    "depends_on",
    "scope",
    "risk",
    "validation_ids",
    "review",
}
VALIDATION_FIELDS = {
    "id",
    "stage_id",
    "command",
    "required",
    "timeout_seconds",
}
PERMISSION_FIELDS = {"commit", "external_write", "elevated_tool"}
MAX_VALIDATION_TIMEOUT_SECONDS = 86_400


@dataclass(frozen=True)
class ContractIssue:
    severity: str
    code: str
    message: str


def _issue(
    issues: list[ContractIssue],
    severity: str,
    code: str,
    message: str,
) -> None:
    issues.append(ContractIssue(severity, code, message))


def _text(value: Any, path: str, issues: list[ContractIssue]) -> str:
    if not isinstance(value, str) or not value.strip():
        _issue(issues, "error", "PLAN_CONTRACT_TYPE", f"{path} 必须是非空字符串。")
        return ""
    return value.strip()


def _strings(
    value: Any,
    path: str,
    issues: list[ContractIssue],
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        _issue(issues, "error", "PLAN_CONTRACT_TYPE", f"{path} 必须是 array。")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            _issue(
                issues,
                "error",
                "PLAN_CONTRACT_TYPE",
                f"{path}[{index}] 必须是非空字符串。",
            )
            continue
        result.append(item.strip())
    if not allow_empty and not result:
        _issue(issues, "error", "PLAN_CONTRACT_EMPTY", f"{path} 不能为空。")
    if len(result) != len(set(result)):
        _issue(issues, "error", "PLAN_CONTRACT_DUPLICATE", f"{path} 包含重复值。")
    return result


def _exact_fields(
    value: dict[str, Any],
    expected: set[str],
    path: str,
    issues: list[ContractIssue],
) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        _issue(
            issues,
            "error",
            "PLAN_CONTRACT_FIELDS",
            f"{path} 缺少字段：{', '.join(missing)}。",
        )
    if extra:
        _issue(
            issues,
            "error",
            "PLAN_CONTRACT_UNSUPPORTED",
            f"{path} 包含旧版或非核心字段：{', '.join(extra)}；请重新规划。",
        )


def _scope_is_safe(item: str) -> bool:
    normalized = item.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", normalized):
        return False
    parts = normalized.rstrip("/").split("/")
    return normalized == "." or all(part not in {"", ".", ".."} for part in parts)


def _scope_allowed(item: str, approved: set[str]) -> bool:
    if not _scope_is_safe(item):
        return False
    normalized = item.replace("\\", "/").rstrip("/")
    for root in approved:
        if not _scope_is_safe(root):
            continue
        approved_root = root.replace("\\", "/").rstrip("/")
        if approved_root == ".":
            return True
        if normalized == approved_root or normalized.startswith(approved_root + "/"):
            return True
    return False


def _validate_dag(
    stages: dict[str, dict[str, Any]],
    issues: list[ContractIssue],
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visited:
            return
        if stage_id in visiting:
            _issue(
                issues,
                "error",
                "PLAN_STAGE_CYCLE",
                f"阶段依赖存在环：{stage_id}。",
            )
            return
        visiting.add(stage_id)
        for dependency in stages[stage_id]["depends_on"]:
            if dependency in stages:
                visit(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)

    for stage_id in stages:
        visit(stage_id)


def validate_contract(value: Any) -> list[ContractIssue]:
    """返回 contract 的全部核心问题，不评价计划文风。"""

    issues: list[ContractIssue] = []
    if not isinstance(value, dict):
        return [
            ContractIssue(
                "error",
                "PLAN_CONTRACT_INVALID",
                "plan-contract.json 根节点必须是 object。",
            )
        ]
    _exact_fields(value, CONTRACT_FIELDS, "contract", issues)

    task_id = _text(value.get("task_id"), "task_id", issues)
    if task_id and not TASK_ID.fullmatch(task_id):
        _issue(
            issues,
            "error",
            "PLAN_TASK_ID_INVALID",
            "task_id 只能包含字母、数字、点、下划线和连字符。",
        )
    revision = value.get("plan_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        _issue(
            issues,
            "error",
            "PLAN_REVISION_INVALID",
            "plan_revision 必须是正整数。",
        )
    risk = value.get("risk")
    if risk not in RISKS:
        _issue(
            issues,
            "error",
            "PLAN_RISK_INVALID",
            "risk 必须是 low、medium 或 high。",
        )
    approved_scope = set(_strings(value.get("scope"), "scope", issues))
    unsafe_scope = sorted(item for item in approved_scope if not _scope_is_safe(item))
    if unsafe_scope:
        _issue(
            issues,
            "error",
            "PLAN_SCOPE_INVALID",
            f"scope 必须是安全的 workspace 相对范围：{', '.join(unsafe_scope)}。",
        )

    permissions = value.get("permissions_requested")
    if not isinstance(permissions, dict):
        _issue(
            issues,
            "error",
            "PLAN_PERMISSION_INVALID",
            "permissions_requested 必须是 object。",
        )
    else:
        _exact_fields(
            permissions,
            PERMISSION_FIELDS,
            "permissions_requested",
            issues,
        )
        for name in PERMISSION_FIELDS:
            if not isinstance(permissions.get(name), bool):
                _issue(
                    issues,
                    "error",
                    "PLAN_PERMISSION_INVALID",
                    f"permissions_requested.{name} 必须是 boolean。",
                )

    raw_stages = value.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        _issue(
            issues,
            "error",
            "PLAN_STAGE_INVALID",
            "stages 必须是非空 array。",
        )
        raw_stages = []
    stages: dict[str, dict[str, Any]] = {}
    for index, raw_stage in enumerate(raw_stages):
        path = f"stages[{index}]"
        if not isinstance(raw_stage, dict):
            _issue(issues, "error", "PLAN_STAGE_INVALID", f"{path} 必须是 object。")
            continue
        _exact_fields(raw_stage, STAGE_FIELDS, path, issues)
        stage_id = _text(raw_stage.get("id"), f"{path}.id", issues)
        if stage_id and not STAGE_ID.fullmatch(stage_id):
            _issue(
                issues,
                "error",
                "PLAN_STAGE_ID_INVALID",
                f"{stage_id} 不是合法 STG ID。",
            )
        if stage_id in stages:
            _issue(
                issues,
                "error",
                "PLAN_STAGE_DUPLICATE",
                f"阶段 {stage_id} 重复。",
            )
            continue
        _text(raw_stage.get("title"), f"{path}.title", issues)
        dependencies = _strings(
            raw_stage.get("depends_on"),
            f"{path}.depends_on",
            issues,
            allow_empty=True,
        )
        stage_scope = _strings(raw_stage.get("scope"), f"{path}.scope", issues)
        unsafe_stage_scope = sorted(
            item for item in stage_scope if not _scope_is_safe(item)
        )
        if unsafe_stage_scope:
            _issue(
                issues,
                "error",
                "PLAN_SCOPE_INVALID",
                f"{stage_id} 包含不安全范围：{', '.join(unsafe_stage_scope)}。",
            )
        outside = sorted(
            item for item in stage_scope if not _scope_allowed(item, approved_scope)
        )
        if outside:
            _issue(
                issues,
                "error",
                "PLAN_STAGE_SCOPE_OUTSIDE",
                f"{stage_id} 超出批准范围：{', '.join(outside)}。",
            )
        stage_risk = raw_stage.get("risk")
        if stage_risk not in RISKS:
            _issue(
                issues,
                "error",
                "PLAN_RISK_INVALID",
                f"{path}.risk 无效。",
            )
        validation_ids = _strings(
            raw_stage.get("validation_ids"),
            f"{path}.validation_ids",
            issues,
        )
        review = raw_stage.get("review")
        if review not in REVIEWS:
            _issue(
                issues,
                "error",
                "PLAN_REVIEW_INVALID",
                f"{path}.review 无效。",
            )
        if stage_risk == "high" and review != "independent":
            _issue(
                issues,
                "error",
                "PLAN_REVIEW_REQUIRED",
                f"高风险阶段 {stage_id} 必须 independent review。",
            )
        if stage_id:
            stages[stage_id] = {
                **raw_stage,
                "depends_on": dependencies,
                "validation_ids": validation_ids,
            }

    for stage_id, stage in stages.items():
        for dependency in stage["depends_on"]:
            if dependency not in stages:
                _issue(
                    issues,
                    "error",
                    "PLAN_STAGE_DEPENDENCY_UNKNOWN",
                    f"{stage_id} 引用了未知阶段 {dependency}。",
                )
            if dependency == stage_id:
                _issue(
                    issues,
                    "error",
                    "PLAN_STAGE_CYCLE",
                    f"{stage_id} 不能依赖自身。",
                )
    _validate_dag(stages, issues)
    stage_risks = [stage.get("risk") for stage in stages.values()]
    if risk in RISK_RANK and any(
        item in RISK_RANK and RISK_RANK[item] > RISK_RANK[risk]
        for item in stage_risks
    ):
        _issue(
            issues,
            "error",
            "PLAN_RISK_UNDERSCOPED",
            "任务 risk 不能低于其最高风险阶段。",
        )

    raw_validations = value.get("validations")
    if not isinstance(raw_validations, list) or not raw_validations:
        _issue(
            issues,
            "error",
            "PLAN_VALIDATION_INVALID",
            "validations 必须是非空 array。",
        )
        raw_validations = []
    validations: dict[str, dict[str, Any]] = {}
    for index, raw_validation in enumerate(raw_validations):
        path = f"validations[{index}]"
        if not isinstance(raw_validation, dict):
            _issue(
                issues,
                "error",
                "PLAN_VALIDATION_INVALID",
                f"{path} 必须是 object。",
            )
            continue
        _exact_fields(raw_validation, VALIDATION_FIELDS, path, issues)
        validation_id = _text(raw_validation.get("id"), f"{path}.id", issues)
        if validation_id and not VALIDATION_ID.fullmatch(validation_id):
            _issue(
                issues,
                "error",
                "PLAN_VALIDATION_ID_INVALID",
                f"{validation_id} 不是合法 VAL ID。",
            )
        if validation_id in validations:
            _issue(
                issues,
                "error",
                "PLAN_VALIDATION_DUPLICATE",
                f"验证 {validation_id} 重复。",
            )
            continue
        stage_id = _text(raw_validation.get("stage_id"), f"{path}.stage_id", issues)
        if stage_id and stage_id not in stages:
            _issue(
                issues,
                "error",
                "PLAN_VALIDATION_STAGE_UNKNOWN",
                f"{validation_id} 引用了未知阶段 {stage_id}。",
            )
        _text(raw_validation.get("command"), f"{path}.command", issues)
        if not isinstance(raw_validation.get("required"), bool):
            _issue(
                issues,
                "error",
                "PLAN_VALIDATION_REQUIRED_INVALID",
                f"{path}.required 必须是 boolean。",
            )
        timeout = raw_validation.get("timeout_seconds")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or timeout > MAX_VALIDATION_TIMEOUT_SECONDS
        ):
            _issue(
                issues,
                "error",
                "PLAN_VALIDATION_TIMEOUT_INVALID",
                f"{path}.timeout_seconds 必须大于 0 且不超过 {MAX_VALIDATION_TIMEOUT_SECONDS} 秒。",
            )
        if validation_id:
            validations[validation_id] = raw_validation

    for stage_id, stage in stages.items():
        for validation_id in stage["validation_ids"]:
            validation = validations.get(validation_id)
            if validation is None:
                _issue(
                    issues,
                    "error",
                    "PLAN_VALIDATION_UNKNOWN",
                    f"{stage_id} 引用了未知验证 {validation_id}。",
                )
            elif validation.get("stage_id") != stage_id:
                _issue(
                    issues,
                    "error",
                    "PLAN_VALIDATION_STAGE_MISMATCH",
                    f"{validation_id} 的 stage_id 与 {stage_id} 不一致。",
                )
    for validation_id, validation in validations.items():
        stage = stages.get(str(validation.get("stage_id")))
        if stage and validation_id not in stage["validation_ids"]:
            _issue(
                issues,
                "error" if validation.get("required") is True else "warning",
                "PLAN_VALIDATION_UNREFERENCED",
                f"{validation_id} 未被所属阶段引用。",
            )

    final_review = value.get("final_review")
    if final_review not in {"same-context", "independent"}:
        _issue(
            issues,
            "error",
            "PLAN_FINAL_REVIEW_INVALID",
            "final_review 必须是 same-context 或 independent。",
        )
    if risk == "high" and final_review != "independent":
        _issue(
            issues,
            "error",
            "PLAN_REVIEW_REQUIRED",
            "高风险任务的 final_review 必须 independent。",
        )
    return issues


def load_contract(path: Path) -> tuple[dict[str, Any], list[ContractIssue]]:
    """读取 contract；解析失败也通过统一 issue 返回。"""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, [
            ContractIssue("error", "PLAN_CONTRACT_MISSING", "缺少 plan-contract.json。")
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [
            ContractIssue(
                "error",
                "PLAN_CONTRACT_INVALID",
                f"无法解析 plan-contract.json：{exc}",
            )
        ]
    return value if isinstance(value, dict) else {}, validate_contract(value)


def contract_maps(
    contract: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """为状态机返回按 ID 索引的阶段和验证定义。"""

    raw_stages = contract.get("stages", [])
    raw_validations = contract.get("validations", [])
    if not isinstance(raw_stages, list):
        raw_stages = []
    if not isinstance(raw_validations, list):
        raw_validations = []
    stages = {
        str(item["id"]): item
        for item in raw_stages
        if isinstance(item, dict) and "id" in item
    }
    validations = {
        str(item["id"]): item
        for item in raw_validations
        if isinstance(item, dict) and "id" in item
    }
    return stages, validations
