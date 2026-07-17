"""生成只读、有界且非 canonical 的审查阅读包。"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import (
    _sensitive_path,
    validate_context_target_shape,
    verify_context_freshness,
)
from .errors import ReviewError
from .io import read_bytes, resolve_relative_file, resolve_root
from .target import validate_target_shape, verify_target_freshness


MAX_PACKAGE_FILES = 128
MAX_PACKAGE_BYTES = 4 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 30


def _root(
    kind: str,
    *,
    workspace: Path | None,
    task_dir: Path | None,
) -> Path:
    value = workspace if kind == "workspace" else task_dir
    if value is None:
        raise ReviewError("REVIEW_PACKAGE_ROOT_MISSING", f"package 需要 {kind} root。")
    return resolve_root(value, label=f"package {kind}")


def _line_numbered(data: bytes, path: str) -> tuple[str | None, str]:
    if _sensitive_path(path):
        return None, "redacted-sensitive-path"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "binary"
    numbered = "\n".join(
        f"{index:6d}  {line}" for index, line in enumerate(text.splitlines(), start=1)
    )
    return numbered, "utf-8-line-numbered"


def _manifest_entries(
    manifest: list[dict[str, Any]],
    root: Path,
    *,
    source: str,
    git_revision: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    records = []
    total = 0
    for item in manifest:
        if item["state"] == "deleted":
            if git_revision is None:
                path = resolve_relative_file(root, item["path"], must_exist=False)
                if path.exists() or path.is_symlink():
                    raise ReviewError(
                        "REVIEW_PACKAGE_STALE",
                        "package 读取时 deleted entry 已重新出现。",
                        path=item["path"],
                    )
            records.append(
                {
                    "source": source,
                    "path": item["path"],
                    "role": item["role"],
                    "state": "deleted",
                    "encoding": None,
                    "content": None,
                }
            )
            continue
        if git_revision is None:
            path = resolve_relative_file(root, item["path"])
            data = read_bytes(path, display_path=item["path"])
        else:
            data = _git_bytes(root, ["show", f"{git_revision}:{item['path']}"])
        if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ReviewError(
                "REVIEW_PACKAGE_STALE",
                "package 读取字节与 target/context manifest 不一致。",
                path=item["path"],
            )
        total += len(data)
        content, encoding = _line_numbered(data, item["path"])
        records.append(
            {
                "source": source,
                "path": item["path"],
                "role": item["role"],
                "state": "present",
                "encoding": encoding,
                "content": content,
            }
        )
    return records, total


def _git(repository: Path, arguments: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReviewError("REVIEW_PACKAGE_GIT_FAILED", f"无法运行 git：{exc}") from exc
    if completed.returncode != 0:
        raise ReviewError("REVIEW_PACKAGE_GIT_FAILED", completed.stderr.strip() or "git 读取失败。")
    return completed.stdout


def _git_bytes(repository: Path, arguments: list[str]) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReviewError("REVIEW_PACKAGE_GIT_FAILED", f"无法运行 git：{exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReviewError("REVIEW_PACKAGE_GIT_FAILED", detail or "git 读取失败。")
    return completed.stdout


def _git_view(target: dict[str, Any], repository: Path) -> dict[str, str] | None:
    if target["kind"] not in {"git-diff", "commit-range"}:
        return None
    identity = target["identity"]
    baseline = identity["baseline"]
    head = identity["head"]
    paths = identity["paths"]
    end = [] if target["kind"] == "git-diff" else [head]
    diff_args = ["diff", "--no-ext-diff", "--unified=10", baseline, *end, "--", *paths]
    stat_args = ["diff", "--stat", baseline, *end, "--", *paths]
    log_args = ["log", "--oneline", "--no-decorate", f"{baseline}..{head}"]
    return {
        "commits": _git(repository, log_args),
        "stat": _git(repository, stat_args),
        "diff": _git(repository, diff_args),
    }


def build_review_package(
    target: dict[str, Any],
    context: dict[str, Any],
    *,
    workspace: Path | None = None,
    task_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    primary = validate_target_shape(target)
    supporting = validate_context_target_shape(context)
    verify_target_freshness(primary, workspace=workspace, task_dir=task_dir)
    verify_context_freshness(supporting, workspace=workspace, task_dir=task_dir)
    primary_root_kind = "task-dir" if primary["kind"] == "plan-bundle" else "workspace"
    primary_root = _root(primary_root_kind, workspace=workspace, task_dir=task_dir)
    context_root = _root(
        supporting["identity"]["root"],
        workspace=workspace,
        task_dir=task_dir,
    )
    entries, primary_bytes = _manifest_entries(
        primary["manifest"],
        primary_root,
        source="target",
        git_revision=(
            str(primary["identity"]["head"])
            if primary["kind"] == "commit-range"
            else None
        ),
    )
    context_entries, context_bytes = _manifest_entries(
        supporting["manifest"],
        context_root,
        source="context",
    )
    entries.extend(context_entries)
    total_bytes = primary_bytes + context_bytes
    if len(entries) > MAX_PACKAGE_FILES or total_bytes > MAX_PACKAGE_BYTES:
        raise ReviewError(
            "REVIEW_PACKAGE_LIMIT_EXCEEDED",
            "review package 超过文件数或字节预算，必须拆分目标。",
        )
    git_view = (
        _git_view(primary, primary_root)
        if primary["kind"] in {"git-diff", "commit-range"}
        else None
    )
    git_bytes = (
        sum(len(value.encode("utf-8")) for value in git_view.values())
        if git_view is not None
        else 0
    )
    if total_bytes + git_bytes > MAX_PACKAGE_BYTES:
        raise ReviewError("REVIEW_PACKAGE_LIMIT_EXCEEDED", "Git 阅读视图超过 package 字节预算。")
    return {
        "target_digest": primary["digest"],
        "context_digest": supporting["digest"],
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "limits": {
            "max_files": MAX_PACKAGE_FILES,
            "max_bytes": MAX_PACKAGE_BYTES,
        },
        "path_count": len(entries),
        "byte_count": total_bytes + git_bytes,
        "truncated": False,
        "entries": entries,
        "git": git_view,
    }
