"""commit-equivalence artifact 的封闭结构与安全文件 helpers。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness_task_bundle import TaskBundle


MAX_ARTIFACT_BYTES = 1024 * 1024
PROOF_FIELDS = {
    "kind",
    "task_id",
    "plan_revision",
    "attempt",
    "review_id",
    "receipt_ref",
    "receipt_digest",
    "precommit_target_digest",
    "postcommit_target_ref",
    "postcommit_target_digest",
    "repository",
    "baseline",
    "precommit_head",
    "commit",
    "allowed_paths",
    "excludes",
    "runtime_excludes",
    "manifest_digest",
    "file_statuses",
    "worktree_status",
    "checks",
    "created_at",
}
CHECK_FIELDS = {
    "single_commit",
    "baseline_match",
    "scope_match",
    "manifest_match",
    "file_status_match",
    "worktree_clean",
}


class CommitEquivalenceError(Exception):
    """快速路径前置条件、Git 对比或 proof 契约失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise CommitEquivalenceError(
                "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
                f"{label} 超过 {MAX_ARTIFACT_BYTES} bytes：{path}",
            )
        value = json.loads(path.read_text(encoding="utf-8"))
    except CommitEquivalenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"无法读取 {label}：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"{label} 根节点必须是 object：{path}",
        )
    return value


def file_digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"无法计算 artifact 摘要：{path}: {exc}",
        ) from exc


def resolve_task_ref(
    bundle: TaskBundle,
    ref: str,
    *,
    prefix: tuple[str, ...] | None = None,
) -> Path:
    relative = Path(ref)
    if (
        not ref
        or relative.is_absolute()
        or "\\" in ref
        or ".." in relative.parts
        or prefix is not None
        and tuple(relative.parts[: len(prefix)]) != prefix
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"artifact ref 不安全或目录不正确：{ref}",
        )
    try:
        resolved = (bundle.task_dir / relative).resolve(strict=True)
        resolved.relative_to(bundle.task_dir)
    except (OSError, ValueError) as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"artifact ref 不存在或越出 task-dir：{ref}",
        ) from exc
    if not resolved.is_file():
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"artifact ref 不是普通文件：{ref}",
        )
    return resolved
