#!/usr/bin/env python3
"""Planning artifact 的路径、批准集合与正式审查门禁。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
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
    "dependency",
    "validation",
    "review",
    "other",
}
PLAN_REVIEW_PATH = re.compile(
    r"^artifacts/reviews/plan-review-attempt-([1-9][0-9]*)\.json$"
)
REVIEWER_VALIDATOR = (
    Path(__file__).resolve().parents[2]
    / "complex-coding-reviewer"
    / "scripts"
    / "review_validate.py"
)


def validate_review_artifact(
    artifact_path: Path,
    task_dir: Path,
    attempt: int,
    approval_context_paths: set[str],
    issue_path: str,
    issues: list[ValidationIssue],
) -> None:
    if not REVIEWER_VALIDATOR.is_file():
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_TOOL_UNAVAILABLE",
            issue_path,
            f"缺少 Reviewer 公共 validator：{REVIEWER_VALIDATOR}",
            "安装 complex-coding-reviewer，并保持两个 skill 位于同一 skills 目录。",
        )
        return

    review_root = task_dir / "artifacts" / "reviews"
    command = [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        "-B",
        str(REVIEWER_VALIDATOR),
        "--receipt",
        str(artifact_path),
        "--review-root",
        str(review_root),
        "--task-dir",
        str(task_dir),
        "--expected-profile",
        "plan-review",
        "--expected-scope",
        "managed-plan",
    ]
    if attempt > 1:
        predecessor = review_root / f"plan-review-attempt-{attempt - 1}.json"
        if not predecessor.is_file():
            add_issue(
                issues,
                "TASK_ARTIFACT_REVIEW_HISTORY_MISSING",
                issue_path,
                f"缺少前序 plan-review receipt：{predecessor.name}",
                "保留不可变前序 attempt，并让当前 receipt 通过 supersedes 连接它。",
            )
            return
        command.extend(("--supersedes", str(predecessor)))

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_VALIDATION_FAILED",
            issue_path,
            f"无法执行 Reviewer validator：{exc}",
            "修复 Python/skill 安装或超时问题后重试。",
        )
        return
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        detail = completed.stderr.strip() or completed.stdout.strip()
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_VALIDATION_FAILED",
            issue_path,
            f"Reviewer validator 未返回 JSON envelope：{detail[:500]}",
            "直接运行 review_validate.py 并修复其稳定诊断。",
        )
        return
    if completed.returncode != 0 or payload.get("ok") is not True:
        error = payload.get("error")
        error_code = error.get("code") if isinstance(error, dict) else "REVIEW_UNKNOWN"
        message = error.get("message") if isinstance(error, dict) else "validator rejected receipt"
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_INVALID",
            issue_path,
            f"plan-review receipt 被拒绝 [{error_code}]：{message}",
            "由 Planner 修复目标后生成新 attempt，或修复 receipt 再重新校验。",
        )
        return
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("verdict") != "passed":
        verdict = result.get("verdict") if isinstance(result, dict) else "missing"
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_NOT_PASSED",
            issue_path,
            f"plan-review verdict 必须为 passed，当前为 {verdict}。",
            "处理所有 blocking/major finding 和 blocked lens，再生成新 attempt。",
        )
        return
    try:
        receipt = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_VALIDATION_FAILED",
            issue_path,
            f"无法读取已通过校验的 plan-review receipt：{exc}",
            "修复 receipt 文件后重新运行 approval checker。",
        )
        return
    context = receipt.get("context") if isinstance(receipt, dict) else None
    manifest = context.get("manifest") if isinstance(context, dict) else None
    context_paths = {
        item.get("path")
        for item in manifest or []
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    unapproved = sorted(context_paths - approval_context_paths)
    if unapproved:
        add_issue(
            issues,
            "TASK_ARTIFACT_REVIEW_CONTEXT_UNATTESTED",
            issue_path,
            "plan-review context 包含未进入批准哈希集合的文件："
            + ", ".join(unapproved),
            "只引用 execution-plan.md、plan-contract.json 和 approval_included planning artifacts。",
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
    review_artifact_count = 0
    approval_context_paths = {"execution-plan.md", "plan-contract.json"}
    review_validations: list[tuple[Path, int, str]] = []
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
            if kind == "review":
                review_artifact_count += 1
        relative = check_relative_path(item.get("path"), f"{path}.path", task_dir, issues)
        review_attempt = None
        if kind == "review" and relative:
            normalized_path = relative.replace("\\", "/")
            match = PLAN_REVIEW_PATH.fullmatch(normalized_path)
            if relative != normalized_path or match is None:
                add_issue(
                    issues,
                    "TASK_CONTRACT_REVIEW_PATH_INVALID",
                    f"{path}.path",
                    "plan-review receipt 路径必须包含不可变 attempt 编号。",
                    "使用 artifacts/reviews/plan-review-attempt-N.json。",
                )
            else:
                review_attempt = int(match.group(1))
        canonical_path = (task_dir / relative).resolve() if relative else None
        if (
            relative
            and kind != "review"
            and item.get("approval_included") is True
        ):
            approval_context_paths.add(relative.replace("\\", "/"))
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
        if kind == "review" and (
            item.get("required") is not True
            or item.get("approval_included") is not True
        ):
            add_issue(
                issues,
                "TASK_CONTRACT_REVIEW_NOT_ATTESTED",
                path,
                "当前 plan-review receipt 必须 required 且进入批准哈希集合。",
                "将 required 与 approval_included 同时设为 true。",
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
                "TASK_ARTIFACT_REVIEW_MISSING"
                if kind == "review"
                else "TASK_ARTIFACT_MISSING",
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
        elif kind == "review" and review_attempt is not None:
            review_validations.append((artifact_path, review_attempt, f"{path}.path"))
    for artifact_path, review_attempt, issue_path in review_validations:
        validate_review_artifact(
            artifact_path,
            task_dir,
            review_attempt,
            approval_context_paths,
            issue_path,
            issues,
        )
    if review_artifact_count != 1:
        add_issue(
            issues,
            "TASK_CONTRACT_REVIEW_ARTIFACT_COUNT",
            "$.artifacts",
            f"managed plan 必须索引一个当前 plan-review receipt，实际为 {review_artifact_count}。",
            "只索引当前 attempt；历史 attempts 保留在 review 目录但不进入 artifact index。",
        )
    return artifacts, artifact_ids, artifact_kinds
