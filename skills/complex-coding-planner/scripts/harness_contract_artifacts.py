#!/usr/bin/env python3
"""Planning artifact 的路径、批准集合与 critique 门禁。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness_contract import (
    ValidationIssue,
    add_issue,
    check_closed_object,
    check_relative_path,
    collect_ids,
)


ARTIFACT_KINDS = {
    "research",
    "standards",
    "architecture",
    "validation",
    "review",
    "other",
}


def validate_review_artifact(
    artifact_path: Path,
    issue_path: str,
    issues: list[ValidationIssue],
) -> None:
    try:
        review_text = artifact_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        add_issue(
            issues,
            "TASK_ARTIFACT_UNREADABLE",
            issue_path,
            f"无法读取 review artifact：{exc}",
            "使用 UTF-8 文本记录 critique 结论。",
        )
        return
    blocking_closed = re.search(
        r"Open blocking findings\s*[:：]\s*(?:none|无|0)",
        review_text,
        re.IGNORECASE,
    )
    ready = re.search(
        r"Ready for approval\s*[:：]\s*(?:yes|true|是|ready)",
        review_text,
        re.IGNORECASE,
    )
    if not blocking_closed or not ready:
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_INCOMPLETE",
            issue_path,
            "critique 未明确关闭 blocking finding 或确认可审批。",
            "填写 Gate Result；独立 evaluator 不可用时声明 fallback。",
        )


def validate_artifacts(
    contract: dict[str, Any],
    task_dir: Path,
    mode: str,
    issues: list[ValidationIssue],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    artifacts, artifact_ids = collect_ids(
        contract.get("artifacts"),
        "artifact",
        "$.artifacts",
        issues,
    )
    artifact_kinds: set[str] = set()
    artifact_paths: set[Path] = set()
    for index, item in enumerate(artifacts):
        path = f"$.artifacts[{index}]"
        fields = {"id", "kind", "path", "required", "approval_included"}
        if not check_closed_object(item, path, fields, issues):
            continue
        kind = item.get("kind")
        if kind not in ARTIFACT_KINDS:
            add_issue(
                issues,
                "TASK_CONTRACT_INVALID_VALUE",
                f"{path}.kind",
                "未知 artifact kind。",
                "使用 task-contract.md 中的 kind。",
            )
        else:
            artifact_kinds.add(kind)
        relative = check_relative_path(item.get("path"), f"{path}.path", task_dir, issues)
        canonical_path = (task_dir / relative).resolve() if relative else None
        if canonical_path in artifact_paths:
            add_issue(
                issues,
                "TASK_CONTRACT_DUPLICATE_PATH",
                f"{path}.path",
                f"重复 artifact 路径：{relative}",
                "每个文件只索引一次。",
            )
        elif canonical_path:
            artifact_paths.add(canonical_path)
        for field in ("required", "approval_included"):
            if not isinstance(item.get(field), bool):
                add_issue(
                    issues,
                    "TASK_CONTRACT_INVALID_TYPE",
                    f"{path}.{field}",
                    "必须是 boolean。",
                    "按 task-contract.md 使用正确 JSON 类型。",
                )
        if item.get("required") is True and item.get("approval_included") is not True:
            add_issue(
                issues,
                "TASK_CONTRACT_ARTIFACT_NOT_ATTESTED",
                f"{path}.approval_included",
                "required planning artifact 必须进入批准哈希集合。",
                "将 approval_included 设为 true。",
            )
        artifact_path = task_dir / relative if relative else None
        missing = artifact_path is not None and not artifact_path.is_file()
        approval_requires_file = (
            item.get("required") is True or item.get("approval_included") is True
        )
        if mode != "approval" or not approval_requires_file:
            continue
        if missing:
            add_issue(
                issues,
                "TASK_ARTIFACT_MISSING",
                f"{path}.path",
                f"批准 artifact 不存在：{relative}",
                "创建文件或修正 artifact index。",
            )
            continue
        if artifact_path is None:
            continue
        try:
            empty = artifact_path.stat().st_size == 0
        except OSError as exc:
            add_issue(
                issues,
                "TASK_ARTIFACT_UNREADABLE",
                f"{path}.path",
                f"无法读取 artifact：{exc}",
                "修复文件权限后重试。",
            )
            continue
        if empty:
            add_issue(
                issues,
                "TASK_ARTIFACT_EMPTY",
                f"{path}.path",
                f"批准 artifact 为空：{relative}",
                "写入实际证据或从 contract 移除该 artifact。",
            )
        elif kind == "review":
            validate_review_artifact(artifact_path, f"{path}.path", issues)
    return artifacts, artifact_ids, artifact_kinds
