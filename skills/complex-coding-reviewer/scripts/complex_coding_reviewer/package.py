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
from .io import load_json_object, read_bytes, resolve_relative_file, resolve_root
from .target import validate_target_shape, verify_target_freshness


MAX_PACKAGE_FILES = 128
MAX_PACKAGE_BYTES = 4 * 1024 * 1024
MAX_DISPATCH_PACKAGE_BYTES = 512 * 1024
GIT_TIMEOUT_SECONDS = 30
PACKAGE_FIELDS = {
    "target_digest",
    "context_digest",
    "generated_at",
    "limits",
    "path_count",
    "byte_count",
    "truncated",
    "entries",
    "git",
}
LIMIT_FIELDS = {"max_files", "max_bytes", "max_dispatch_bytes"}
ENTRY_FIELDS = {"source", "path", "role", "state", "encoding", "content"}
GIT_FIELDS = {"commits", "stat", "diff"}


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


def _closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_PACKAGE_INVALID", "值必须是 object。", path=path)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ReviewError(
            "REVIEW_PACKAGE_INVALID",
            f"package 封闭字段不匹配：unknown={unknown}, missing={missing}",
            path=path,
        )
    return value


def _package_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError("REVIEW_PACKAGE_INVALID", "generated_at 必须是非空 RFC3339。")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewError("REVIEW_PACKAGE_INVALID", "generated_at 必须是 RFC3339。") from exc
    if parsed.tzinfo is None:
        raise ReviewError("REVIEW_PACKAGE_INVALID", "generated_at 必须包含时区。")
    return value


def _validate_package_shape(
    package: Any,
    *,
    target: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    value = _closed(package, PACKAGE_FIELDS, "$.package")
    if (
        value["target_digest"] != target["digest"]
        or value["context_digest"] != context["digest"]
    ):
        raise ReviewError("REVIEW_PACKAGE_STALE", "package 未绑定当前 target/context。")
    _package_timestamp(value["generated_at"])
    limits = _closed(value["limits"], LIMIT_FIELDS, "$.package.limits")
    expected_limits = {
        "max_files": MAX_PACKAGE_FILES,
        "max_bytes": MAX_PACKAGE_BYTES,
        "max_dispatch_bytes": MAX_DISPATCH_PACKAGE_BYTES,
    }
    if limits != expected_limits:
        raise ReviewError("REVIEW_PACKAGE_INVALID", "package limits 与当前契约不一致。")
    path_count = value["path_count"]
    byte_count = value["byte_count"]
    if (
        isinstance(path_count, bool)
        or not isinstance(path_count, int)
        or path_count < 0
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
        or value["truncated"] is not False
    ):
        raise ReviewError(
            "REVIEW_PACKAGE_INVALID",
            "path_count/byte_count 必须是非负整数且 truncated=false。",
        )
    entries = value["entries"]
    if not isinstance(entries, list) or path_count != len(entries):
        raise ReviewError("REVIEW_PACKAGE_INVALID", "path_count 与 entries 数量不一致。")
    expected_entries = {
        (source, item["path"]): item
        for source, manifest in (
            ("target", target["manifest"]),
            ("context", context["manifest"]),
        )
        for item in manifest
    }
    actual_keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(entries):
        item = _closed(raw, ENTRY_FIELDS, f"$.package.entries[{index}]")
        source = item["source"]
        path = item["path"]
        if source not in {"target", "context"} or not isinstance(path, str):
            raise ReviewError("REVIEW_PACKAGE_INVALID", "package entry source/path 无效。")
        key = (source, path)
        if key in actual_keys or key not in expected_entries:
            raise ReviewError("REVIEW_PACKAGE_INVALID", "package entry 重复或不属于冻结 manifest。")
        actual_keys.add(key)
        expected = expected_entries[key]
        if item["role"] != expected["role"] or item["state"] != expected["state"]:
            raise ReviewError("REVIEW_PACKAGE_INVALID", "package entry role/state 与 manifest 不一致。")
        if item["state"] == "deleted":
            if item["encoding"] is not None or item["content"] is not None:
                raise ReviewError("REVIEW_PACKAGE_INVALID", "deleted package entry 不得包含内容。")
            continue
        if item["encoding"] == "utf-8-line-numbered":
            if not isinstance(item["content"], str):
                raise ReviewError("REVIEW_PACKAGE_INVALID", "UTF-8 package entry 必须包含文本。")
        elif item["encoding"] in {"binary", "redacted-sensitive-path"}:
            if item["content"] is not None:
                raise ReviewError("REVIEW_PACKAGE_INVALID", "binary/redacted entry 不得包含文本。")
        else:
            raise ReviewError("REVIEW_PACKAGE_INVALID", "package entry encoding 无效。")
    if actual_keys != set(expected_entries):
        raise ReviewError("REVIEW_PACKAGE_INVALID", "package entries 未完整覆盖冻结 manifest。")
    git = value["git"]
    if target["kind"] in {"git-diff", "commit-range"}:
        git_view = _closed(git, GIT_FIELDS, "$.package.git")
        if not all(isinstance(git_view[field], str) for field in GIT_FIELDS):
            raise ReviewError("REVIEW_PACKAGE_INVALID", "package git 视图必须是字符串。")
    elif git is not None:
        raise ReviewError("REVIEW_PACKAGE_INVALID", "非 Git target 不得包含 git 阅读视图。")
    source_bytes = sum(
        int(item["size"])
        for manifest in (target["manifest"], context["manifest"])
        for item in manifest
        if item["state"] == "present"
    )
    git_bytes = (
        sum(len(git[field].encode("utf-8")) for field in GIT_FIELDS)
        if isinstance(git, dict)
        else 0
    )
    if byte_count != source_bytes + git_bytes:
        raise ReviewError("REVIEW_PACKAGE_INVALID", "package byte_count 与冻结内容不一致。")
    return value


def load_dispatch_package(
    path: Path,
    *,
    target: dict[str, Any],
    context: dict[str, Any],
    workspace: Path | None,
    task_dir: Path | None,
    check_freshness: bool,
) -> dict[str, Any]:
    """读取 Agent package，并执行闭合结构、预算与内容重放校验。"""

    try:
        artifact_size = path.stat().st_size
    except OSError as exc:
        raise ReviewError(
            "REVIEW_PACKAGE_INVALID",
            f"无法读取 review package 元数据：{exc}",
            path=str(path),
        ) from exc
    if artifact_size > MAX_DISPATCH_PACKAGE_BYTES:
        raise ReviewError(
            "REVIEW_PACKAGE_LIMIT_EXCEEDED",
            "Agent 派发 package 超过 512 KiB；请省略 --package 或拆分审查目标。",
            path=str(path),
        )
    package = load_json_object(path, code="REVIEW_PACKAGE_INVALID")
    byte_count = package.get("byte_count")
    if (
        isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 0
        or package.get("truncated") is not False
    ):
        raise ReviewError(
            "REVIEW_PACKAGE_INVALID",
            "Agent 派发 package 必须声明非负 byte_count 且 truncated=false。",
            path=str(path),
        )
    if byte_count > MAX_DISPATCH_PACKAGE_BYTES:
        raise ReviewError(
            "REVIEW_PACKAGE_LIMIT_EXCEEDED",
            "Agent 派发 package 的声明内容超过 512 KiB；请省略 --package 或拆分审查目标。",
            path=str(path),
        )
    checked = _validate_package_shape(package, target=target, context=context)
    if check_freshness:
        expected = build_review_package(
            target,
            context,
            workspace=workspace,
            task_dir=task_dir,
            generated_at=checked["generated_at"],
        )
        if checked != expected:
            raise ReviewError(
                "REVIEW_PACKAGE_INVALID",
                "package 内容不是由当前冻结 target/context 确定性生成。",
                path=str(path),
            )
    return checked


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
            "max_dispatch_bytes": MAX_DISPATCH_PACKAGE_BYTES,
        },
        "path_count": len(entries),
        "byte_count": total_bytes + git_bytes,
        "truncated": False,
        "entries": entries,
        "git": git_view,
    }
