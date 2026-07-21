"""commit-equivalence 的有界 Git 读取与 canonical target 对比。"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness_commit_equivalence_schema import (
    CommitEquivalenceError,
    canonical_digest,
)
from harness_task_bundle import TaskBundle


GIT_TIMEOUT_SECONDS = 30
REVIEWER_TIMEOUT_SECONDS = 30


def _run_git(
    workspace: Path,
    arguments: list[str],
    *,
    binary: bool = False,
) -> bytes | str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace), *arguments],
            check=False,
            capture_output=True,
            text=not binary,
            encoding=None if binary else "utf-8",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
            f"Git 操作失败：{exc}",
        ) from exc
    if completed.returncode != 0:
        stderr = (
            completed.stderr.decode("utf-8", errors="replace")
            if isinstance(completed.stderr, bytes)
            else completed.stderr
        )
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
            f"Git 操作返回 {completed.returncode}：{stderr.strip()}",
        )
    return completed.stdout


def resolve_commit(workspace: Path, revision: str) -> str:
    output = _run_git(workspace, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
    assert isinstance(output, str)
    commit = output.strip()
    if len(commit) not in {40, 64}:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
            f"无法解析 commit：{revision}",
        )
    return commit


def _commit_parents(workspace: Path, commit: str) -> list[str]:
    output = _run_git(workspace, ["rev-list", "--parents", "-n", "1", commit])
    assert isinstance(output, str)
    fields = output.strip().split()
    if not fields or fields[0] != commit:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
            "无法解析 final commit 的父提交。",
        )
    return fields[1:]


def _runtime_excludes(bundle: TaskBundle) -> list[str]:
    result: list[str] = []
    for path in (bundle.task_dir, bundle.pointer_path):
        try:
            result.append(path.resolve().relative_to(bundle.workspace.resolve()).as_posix())
        except ValueError as exc:
            raise CommitEquivalenceError(
                "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
                f"Harness runtime path 越出 workspace：{path}",
            ) from exc
    return sorted(set(result))


def _is_runtime_path(path: str, excludes: list[str]) -> bool:
    return any(path == item or path.startswith(item.rstrip("/") + "/") for item in excludes)


def _source_worktree_status(bundle: TaskBundle, excludes: list[str]) -> list[str]:
    output = _run_git(
        bundle.workspace,
        [
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
            "--no-renames",
        ],
        binary=True,
    )
    assert isinstance(output, bytes)
    entries: list[str] = []
    for raw in output.decode("utf-8", errors="surrogateescape").split("\0"):
        if not raw:
            continue
        path = raw[3:].replace("\\", "/") if len(raw) >= 4 else raw
        if not _is_runtime_path(path, excludes):
            entries.append(raw)
    return sorted(entries)


def _changed_statuses(
    bundle: TaskBundle,
    baseline: str,
    commit: str,
    excludes: list[str],
) -> list[dict[str, str]]:
    output = _run_git(
        bundle.workspace,
        ["diff", "--name-status", "-z", "--no-renames", baseline, commit],
        binary=True,
    )
    assert isinstance(output, bytes)
    fields = output.decode("utf-8", errors="surrogateescape").split("\0")
    result: list[dict[str, str]] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index]
        if index + 1 >= len(fields) or not fields[index + 1]:
            raise CommitEquivalenceError(
                "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
                "无法解析 final commit 的 name-status。",
            )
        path = fields[index + 1].replace("\\", "/")
        if not _is_runtime_path(path, excludes):
            result.append({"path": path, "status": status})
        index += 2
    return sorted(result, key=lambda item: item["path"])


def _baseline_path_exists(bundle: TaskBundle, baseline: str, path: str) -> bool:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(bundle.workspace),
                "cat-file",
                "-e",
                f"{baseline}:{path}",
            ],
            check=False,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
            f"无法检查 baseline path：{path}: {exc}",
        ) from exc
    if completed.returncode not in {0, 128}:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_GIT_FAILED",
            f"无法检查 baseline path：{path}",
        )
    return completed.returncode == 0


def _expected_statuses(
    bundle: TaskBundle,
    baseline: str,
    manifest: list[dict[str, Any]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for entry in manifest:
        path = entry.get("path")
        state = entry.get("state")
        if not isinstance(path, str) or state not in {"present", "deleted"}:
            raise CommitEquivalenceError(
                "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
                "precommit target manifest 包含无效 path/state。",
            )
        if state == "deleted":
            status = "D"
        else:
            status = "M" if _baseline_path_exists(bundle, baseline, path) else "A"
        result.append({"path": path, "status": status})
    return sorted(result, key=lambda item: item["path"])


def _reviewer_target_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "complex-coding-reviewer"
        / "scripts"
        / "review_target.py"
    )


def build_commit_target(
    bundle: TaskBundle,
    *,
    baseline: str,
    commit: str,
    paths: list[str],
    excludes: list[str],
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        "-B",
        str(_reviewer_target_path()),
        "commit-range",
        "--repository",
        str(bundle.workspace),
        "--baseline",
        baseline,
        "--head",
        commit,
    ]
    for path in paths:
        command.extend(["--path", path])
    for exclude in excludes:
        command.extend(["--exclude", exclude])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=REVIEWER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            f"无法生成 postcommit canonical target：{exc}",
        ) from exc
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "Reviewer target helper 未返回合法 JSON。",
        ) from exc
    result = envelope.get("result") if isinstance(envelope, dict) else None
    target = result.get("target") if isinstance(result, dict) else None
    if completed.returncode != 0 or envelope.get("ok") is not True or not isinstance(target, dict):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "Reviewer target helper 拒绝生成 postcommit target。",
        )
    return target


def _reviewed_bytes_match(
    bundle: TaskBundle,
    pre_manifest: list[dict[str, Any]],
    post_manifest: list[dict[str, Any]],
    commit: str,
) -> bool:
    if len(pre_manifest) != len(post_manifest):
        return False
    for pre_entry, post_entry in zip(pre_manifest, post_manifest, strict=True):
        stable_fields = ("path", "role", "state")
        if any(pre_entry.get(field) != post_entry.get(field) for field in stable_fields):
            return False
        if pre_entry.get("state") == "deleted":
            if post_entry.get("sha256") is not None or post_entry.get("size") is not None:
                return False
            continue
        path = pre_entry.get("path")
        if not isinstance(path, str):
            return False
        try:
            source = (bundle.workspace / path).resolve(strict=True)
            source.relative_to(bundle.workspace.resolve())
            data = source.read_bytes()
        except (OSError, ValueError):
            return False
        if (
            hashlib.sha256(data).hexdigest() != pre_entry.get("sha256")
            or len(data) != pre_entry.get("size")
        ):
            return False
        filtered = _run_git(
            bundle.workspace,
            ["hash-object", f"--path={path}", "--", path],
        )
        committed = _run_git(bundle.workspace, ["rev-parse", f"{commit}:{path}"])
        assert isinstance(filtered, str) and isinstance(committed, str)
        if filtered.strip() != committed.strip():
            return False
    return True


def compare_targets(
    bundle: TaskBundle,
    precommit: dict[str, Any],
    postcommit: dict[str, Any],
    commit: str,
) -> dict[str, Any]:
    pre_identity = precommit.get("identity")
    post_identity = postcommit.get("identity")
    pre_manifest = precommit.get("manifest")
    post_manifest = postcommit.get("manifest")
    if (
        precommit.get("kind") != "git-diff"
        or postcommit.get("kind") != "commit-range"
        or not isinstance(pre_identity, dict)
        or not isinstance(post_identity, dict)
        or not isinstance(pre_manifest, list)
        or not isinstance(post_manifest, list)
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "快速路径只接受 working-tree 到 commit-range 的 canonical target。",
        )
    baseline = pre_identity.get("baseline")
    pre_head = pre_identity.get("head")
    paths = pre_identity.get("paths")
    excludes = pre_identity.get("excludes")
    if (
        not isinstance(baseline, str)
        or not isinstance(pre_head, str)
        or not isinstance(paths, list)
        or not all(isinstance(item, str) for item in paths)
        or not isinstance(excludes, list)
        or not all(isinstance(item, str) for item in excludes)
        or pre_identity.get("mode") != "working-tree"
        or pre_identity.get("stage_id") is not None
        or pre_identity.get("attempt") is not None
    ):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
            "precommit final target identity 无效。",
        )
    if _commit_parents(bundle.workspace, commit) != [pre_head]:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
            "final commit 不是 review HEAD 之后的单一直接提交；回退 post-commit review。",
        )
    expected_identity = {**pre_identity, "mode": "commit-range", "head": commit}
    if post_identity != expected_identity:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
            "baseline、allowed paths 或 commit identity 与 precommit target 不一致。",
        )
    runtime_excludes = _runtime_excludes(bundle)
    worktree_status = _source_worktree_status(bundle, runtime_excludes)
    if worktree_status:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_DIRTY",
            "final commit 后仍有未提交或未跟踪 source 变更；回退 post-commit review。",
        )
    if not _reviewed_bytes_match(bundle, pre_manifest, post_manifest, commit):
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
            "提交后的路径、删除项或工作树字节与 precommit target 不一致。",
        )
    actual_statuses = _changed_statuses(bundle, baseline, commit, runtime_excludes)
    expected_statuses = _expected_statuses(bundle, baseline, pre_manifest)
    if actual_statuses != expected_statuses:
        raise CommitEquivalenceError(
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
            "提交后的 A/M/D 状态或范围与 precommit target 不一致。",
        )
    return {
        "baseline": baseline,
        "precommit_head": pre_head,
        "allowed_paths": paths,
        "excludes": excludes,
        "runtime_excludes": runtime_excludes,
        "manifest_digest": canonical_digest(pre_manifest),
        "file_statuses": actual_statuses,
        "worktree_status": worktree_status,
    }
