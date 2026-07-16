#!/usr/bin/env python3
"""把 managed review target 绑定到批准范围和当前 Git 状态。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from harness_review_errors import ReviewGateError
from harness_task_bundle import TaskBundle


GIT_TIMEOUT_SECONDS = 30
NARRATIVE_ALLOWED_CHANGES = (
    "all files approved by ",
    "task-local execution evidence",
    "minimal fixes discovered by ",
)


def _allowed_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("\\", "/")
    if normalized.lower().startswith(NARRATIVE_ALLOWED_CHANGES):
        return None
    if normalized.endswith("/**"):
        normalized = normalized[:-3].rstrip("/")
    if not normalized or "*" in normalized or "?" in normalized:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE",
            f"allowed_changes 无法转换为 canonical review path：{value}",
        )
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts or ":" in normalized:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE",
            f"allowed_changes 包含不安全路径：{value}",
        )
    return path.as_posix()


def _minimal_paths(paths: set[str]) -> list[str]:
    selected: list[str] = []
    for path in sorted(paths, key=lambda item: (len(Path(item).parts), item)):
        if any(
            path == parent or path.startswith(parent.rstrip("/") + "/")
            for parent in selected
        ):
            continue
        selected.append(path)
    return sorted(selected)


def _stage_map(bundle: TaskBundle) -> dict[str, dict[str, Any]]:
    stages = bundle.contract.get("stages")
    if not isinstance(stages, list):
        return {}
    return {
        str(stage["id"]): stage
        for stage in stages
        if isinstance(stage, dict) and isinstance(stage.get("id"), str)
    }


def _collect_stage_paths(
    stages: dict[str, dict[str, Any]],
    stage_id: str,
    visiting: set[str],
) -> set[str]:
    if stage_id in visiting:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE",
            f"stage dependency cycle 无法转换 review paths：{stage_id}",
        )
    stage = stages.get(stage_id)
    if stage is None:
        return set()
    allowed = stage.get("allowed_changes")
    paths = (
        {
            normalized
            for item in allowed
            if (normalized := _allowed_path(item)) is not None
        }
        if isinstance(allowed, list)
        else set()
    )
    if paths:
        return paths
    dependencies = stage.get("depends_on")
    if not isinstance(dependencies, list):
        return set()
    inherited: set[str] = set()
    for dependency in dependencies:
        if isinstance(dependency, str):
            inherited.update(
                _collect_stage_paths(stages, dependency, visiting | {stage_id})
            )
    return inherited


def _stage_paths(bundle: TaskBundle, stage_id: str) -> list[str]:
    paths = _collect_stage_paths(_stage_map(bundle), stage_id, set())
    if paths:
        return _minimal_paths(paths)
    raise ReviewGateError(
        "RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE",
        f"stage 缺少可转换的 allowed_changes：{stage_id}",
    )


def _final_paths(bundle: TaskBundle) -> list[str]:
    paths: set[str] = set()
    stages = bundle.contract.get("stages")
    if not isinstance(stages, list):
        stages = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        allowed = stage.get("allowed_changes")
        if not isinstance(allowed, list):
            continue
        for item in allowed:
            normalized = _allowed_path(item)
            if normalized is not None:
                paths.add(normalized)
    if not paths:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE",
            "contract 缺少可转换的 final review paths。",
        )
    return _minimal_paths(paths)


def _current_head(workspace: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--verify", "HEAD^{commit}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_GIT_FAILED",
            f"无法读取 managed review 的当前 HEAD：{exc}",
        ) from exc
    head = completed.stdout.strip()
    if completed.returncode != 0 or len(head) not in {40, 64}:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_GIT_FAILED",
            "无法解析 managed review 的当前 HEAD。",
        )
    return head


def _git_changed_paths(workspace: Path, baseline: str) -> set[str]:
    commands = (
        ["diff", "--name-only", "-z", "--no-renames", baseline],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    )
    paths: set[str] = set()
    for arguments in commands:
        try:
            completed = subprocess.run(
                ["git", "-C", str(workspace), *arguments],
                check=False,
                capture_output=True,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_GIT_FAILED",
                f"无法读取 managed review scope：{exc}",
            ) from exc
        if completed.returncode != 0:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_GIT_FAILED",
                "无法读取 managed review scope 的 Git 变更。",
            )
        decoded = completed.stdout.decode("utf-8", errors="surrogateescape")
        for raw in decoded.split("\0"):
            if raw:
                paths.add(raw.replace("\\", "/"))
    return paths


def _task_bundle_paths(bundle: TaskBundle) -> list[str]:
    result: set[str] = set()
    for path in (bundle.task_dir, bundle.pointer_path):
        try:
            result.add(path.resolve().relative_to(bundle.workspace.resolve()).as_posix())
        except ValueError as exc:
            raise ReviewGateError(
                "RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE",
                f"task bundle 越出 workspace：{path}",
            ) from exc
    return sorted(result)


def _inside_paths(path: str, prefixes: list[str]) -> bool:
    return any(
        path == prefix or path.startswith(prefix.rstrip("/") + "/")
        for prefix in prefixes
    )


def validate_managed_target(
    bundle: TaskBundle,
    receipt: dict[str, Any],
    *,
    scope_kind: str,
    stage_id: str | None,
    attempt: int | None,
    final_commit_recorded: bool,
    expected_baseline: str | None = None,
) -> None:
    """确认 receipt 覆盖完整批准 scope，并绑定当前 HEAD。"""

    target = receipt.get("target")
    identity = target.get("identity") if isinstance(target, dict) else None
    if not isinstance(target, dict) or not isinstance(identity, dict):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_TARGET_INVALID",
            "managed review receipt 缺少 canonical Git target。",
        )
    expected_paths = (
        _stage_paths(bundle, stage_id)
        if scope_kind == "stage-delta" and stage_id is not None
        else _final_paths(bundle)
    )
    if identity.get("paths") != expected_paths or identity.get("excludes") != []:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_MISMATCH",
            "review target paths 必须精确覆盖 contract 的 canonical allowed_changes。",
        )
    expected_kind = (
        "commit-range"
        if scope_kind == "final-integration" and final_commit_recorded
        else "git-diff"
    )
    expected_mode = "commit-range" if expected_kind == "commit-range" else "working-tree"
    if target.get("kind") != expected_kind or identity.get("mode") != expected_mode:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_MISMATCH",
            f"{scope_kind} 当前必须使用 {expected_kind} target。",
        )
    current_head = _current_head(bundle.workspace)
    if identity.get("repository") != "." or identity.get("head") != current_head:
        raise ReviewGateError(
            "REVIEW_TARGET_STALE",
            "managed review target 未绑定当前 repository HEAD。",
        )
    baseline = identity.get("baseline")
    if not isinstance(baseline, str):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_TARGET_INVALID",
            "managed review target 缺少 Git baseline。",
        )
    if expected_baseline is not None and baseline != expected_baseline:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_BASELINE_MISMATCH",
            "final-integration target baseline 与当前 revision execution baseline 不一致。",
        )
    changed_paths = _git_changed_paths(bundle.workspace, baseline)
    task_paths = _task_bundle_paths(bundle)
    out_of_scope = sorted(
        path
        for path in changed_paths
        if not _inside_paths(path, task_paths)
        and not _inside_paths(path, expected_paths)
    )
    if out_of_scope:
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_DRIFT",
            "working tree/commit range 包含 target paths 外的变更："
            + ", ".join(out_of_scope[:20]),
        )
    if expected_kind == "commit-range":
        post_commit_changes = _git_changed_paths(bundle.workspace, current_head)
        source_changes = sorted(
            path for path in post_commit_changes if not _inside_paths(path, task_paths)
        )
        if source_changes:
            raise ReviewGateError(
                "REVIEW_TARGET_STALE",
                "post-commit final review 之后仍有未提交 source 变更："
                + ", ".join(source_changes[:20]),
            )
    if scope_kind == "stage-delta" and (
        identity.get("stage_id") != stage_id or identity.get("attempt") != attempt
    ):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_MISMATCH",
            "stage-delta target identity 与当前 stage attempt 不一致。",
        )
    if scope_kind == "final-integration" and (
        identity.get("stage_id") is not None or identity.get("attempt") is not None
    ):
        raise ReviewGateError(
            "RUN_STATE_REVIEW_SCOPE_MISMATCH",
            "final-integration target 不得绑定 stage attempt。",
        )
