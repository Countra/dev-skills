#!/usr/bin/env python3
"""任务契约校验的通用模型、ID 和路径 helpers。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


ID_PATTERNS = {
    "goal": re.compile(r"^GOAL-\d{2,}$"),
    "requirement": re.compile(r"^REQ-\d{2,}$"),
    "acceptance": re.compile(r"^AC-\d{2,}$"),
    "nonfunctional": re.compile(r"^NFR-\d{2,}$"),
    "artifact": re.compile(r"^ART-\d{2,}$"),
    "dependency": re.compile(r"^DEP-\d{2,}$"),
    "stage": re.compile(r"^STG-\d{2,}$"),
    "validation": re.compile(r"^VAL-\d{2,}$"),
}

PLACEHOLDER_PATTERN = re.compile(
    r"<(?:"
    r"task-id|date|type|task-slug|RFC3339 timestamp|observable outcome|"
    r"required behavior|given / when / then outcome|stage title|"
    r"approved path or module|explicit boundary|entry condition|"
    r"observable exit condition|deterministic command or tool|evidence-file|"
    r"dependency-category|ecosystem|package-identity|source-repository-url|"
    r"selected-version|version-policy|manifest-path|evidence-url|evidence-value|"
    r"evidence-caveat|YYYY-MM-DD|necessity-evidence|decision-reason|"
    r"阶段名称|TODO[^>]*|TBD[^>]*|placeholder[^>]*"
    r")>",
    re.IGNORECASE,
)

ROOT_FIELDS = {
    "task_id",
    "plan_revision",
    "lifecycle_route",
    "plan_profile",
    "goal",
    "requirements",
    "acceptance_criteria",
    "nonfunctional_requirements",
    "artifacts",
    "stages",
    "validations",
    "research",
    "dependency_selection",
    "approval_policy",
    "reapproval_triggers",
    "stop_conditions",
}

ROOT_REQUIRED_FIELDS = ROOT_FIELDS - {"dependency_selection"}

STAGE_FIELDS = {
    "id",
    "title",
    "depends_on",
    "requirement_ids",
    "acceptance_ids",
    "nonfunctional_ids",
    "validation_ids",
    "allowed_changes",
    "forbidden_changes",
    "entry_conditions",
    "exit_conditions",
    "risk",
    "commit_expectation",
}

APPROVAL_POLICY_FIELDS = {
    "implementation_requires_user_approval",
    "commit_requires_explicit_authorization",
    "external_write_requires_explicit_authorization",
    "elevated_tool_requires_explicit_authorization",
}


@dataclass(frozen=True)
class ValidationIssue:
    """一个稳定、可机器消费的校验诊断。"""

    code: str
    path: str
    message: str
    hint: str
    level: str = "error"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def add_issue(
    issues: list[ValidationIssue],
    code: str,
    path: str,
    message: str,
    hint: str,
    *,
    level: str = "error",
) -> None:
    issues.append(ValidationIssue(code, path, message, hint, level))


def load_json_object(
    path: Path,
) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_issue(
            issues,
            "TASK_CONTRACT_MISSING",
            "$",
            f"缺少任务契约：{path}",
            "从 templates/plan-contract.json 创建 plan-contract.json。",
        )
        return None, issues
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_JSON",
            "$",
            f"无法解析任务契约：{exc}",
            "修复 UTF-8 JSON 语法后重试。",
        )
        return None, issues
    if not isinstance(value, dict):
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_TYPE",
            "$",
            "任务契约根节点必须是 object。",
            "使用 JSON object 保存契约字段。",
        )
        return None, issues
    return value, issues


def check_closed_object(
    value: Any,
    path: str,
    allowed: set[str],
    issues: list[ValidationIssue],
    *,
    required: set[str] | None = None,
) -> bool:
    if not isinstance(value, dict):
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_TYPE",
            path,
            "必须是 object。",
            "改为 JSON object。",
        )
        return False
    for key in sorted(set(value) - allowed):
        add_issue(
            issues,
            "TASK_CONTRACT_UNKNOWN_FIELD",
            f"{path}.{key}",
            "字段不属于当前任务契约。",
            "删除该字段或先更新唯一契约定义和联合 fixtures。",
        )
    for key in sorted((required or allowed) - set(value)):
        add_issue(
            issues,
            "TASK_CONTRACT_MISSING_FIELD",
            f"{path}.{key}",
            "缺少必需字段。",
            "按 task-contract.md 补齐字段。",
        )
    return True


def check_string(value: Any, path: str, issues: list[ValidationIssue]) -> bool:
    if not isinstance(value, str) or not value.strip():
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_VALUE",
            path,
            "必须是非空字符串。",
            "填写明确、可验证的值。",
        )
        return False
    if contains_placeholder(value):
        add_issue(
            issues,
            "TASK_CONTRACT_PLACEHOLDER",
            path,
            "仍包含模板占位符。",
            "用任务真实值替换占位符。",
        )
        return False
    return True


def contains_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(value))


def check_string_list(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
    *,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_TYPE",
            path,
            "必须是字符串数组。",
            "改为 JSON array。",
        )
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if check_string(item, f"{path}[{index}]", issues):
            result.append(item)
    if not allow_empty and not result:
        add_issue(
            issues,
            "TASK_CONTRACT_EMPTY_LIST",
            path,
            "至少需要一项。",
            "补充可执行内容。",
        )
    return result


def check_id(
    value: Any,
    kind: str,
    path: str,
    issues: list[ValidationIssue],
) -> str:
    if not check_string(value, path, issues):
        return ""
    assert isinstance(value, str)
    if not ID_PATTERNS[kind].fullmatch(value):
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_ID",
            path,
            f"{value} 不符合 {kind} ID 格式。",
            "使用对应稳定 ID 前缀和数字。",
        )
        return ""
    return value


def check_relative_path(
    value: Any,
    path: str,
    task_dir: Path,
    issues: list[ValidationIssue],
) -> str:
    if not check_string(value, path, issues):
        return ""
    raw = str(value)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        add_issue(
            issues,
            "TASK_CONTRACT_UNSAFE_PATH",
            path,
            "路径必须位于 task-dir 内。",
            "使用无 .. 的相对路径。",
        )
        return ""
    resolved = (task_dir / candidate).resolve()
    try:
        resolved.relative_to(task_dir.resolve())
    except ValueError:
        add_issue(
            issues,
            "TASK_CONTRACT_UNSAFE_PATH",
            path,
            "路径逃逸 task-dir。",
            "使用 task-dir 内相对路径。",
        )
        return ""
    return raw


def collect_ids(
    values: Any,
    kind: str,
    path: str,
    issues: list[ValidationIssue],
) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(values, list):
        add_issue(
            issues,
            "TASK_CONTRACT_INVALID_TYPE",
            path,
            "必须是 object 数组。",
            "改为 JSON array。",
        )
        return [], set()
    objects: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(values):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            add_issue(
                issues,
                "TASK_CONTRACT_INVALID_TYPE",
                item_path,
                "必须是 object。",
                "按模板填写对象。",
            )
            continue
        objects.append(item)
        item_id = check_id(item.get("id"), kind, f"{item_path}.id", issues)
        if item_id in ids:
            add_issue(
                issues,
                "TASK_CONTRACT_DUPLICATE_ID",
                f"{item_path}.id",
                f"重复 ID：{item_id}",
                "为同类对象使用唯一 ID。",
            )
        elif item_id:
            ids.add(item_id)
    return objects, ids


def check_references(
    values: Iterable[str],
    known: set[str],
    path: str,
    issues: list[ValidationIssue],
) -> None:
    for index, value in enumerate(values):
        if value not in known:
            add_issue(
                issues,
                "TASK_CONTRACT_BROKEN_REFERENCE",
                f"{path}[{index}]",
                f"引用不存在：{value}",
                "修正 ID 或补充被引用对象。",
            )


def graph_has_cycle(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(
            dependency in graph and visit(dependency)
            for dependency in graph.get(node, set())
        ):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
