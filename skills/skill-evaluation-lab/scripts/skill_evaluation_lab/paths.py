"""受限路径解析、资源上限与内容身份计算。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import PathError, SkillError


IGNORED_DIRECTORY_NAMES = {".git", "__pycache__"}
IGNORED_FILE_NAMES = {".DS_Store"}


@dataclass(frozen=True)
class ResourceLimits:
    """限制静态读取规模，避免意外扫描无界目录。"""

    max_files: int = 512
    max_entries: int = 1_024
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 8_388_608
    max_text_bytes: int = 1_048_576


DEFAULT_LIMITS = ResourceLimits()


def is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _reject_parent_segments(value: Path, *, label: str) -> None:
    if ".." in value.parts:
        raise PathError(
            f"{label} 不允许包含父目录跳转",
            code="PATH_PARENT_SEGMENT",
            path=str(value),
        )


def _ensure_contained(workspace: Path, candidate: Path, *, label: str) -> None:
    if candidate != workspace and not candidate.is_relative_to(workspace):
        raise PathError(
            f"{label} 必须位于 workspace 内",
            code="PATH_OUTSIDE_WORKSPACE",
            path=str(candidate),
        )


def _ensure_no_links(workspace: Path, candidate: Path, *, label: str) -> None:
    current = workspace
    relative = candidate.relative_to(workspace)
    for part in relative.parts:
        current = current / part
        if is_link_like(current):
            raise PathError(
                f"{label} 路径包含符号链接或 junction",
                code="PATH_LINK_REJECTED",
                path=str(current),
            )
        if not current.exists():
            break


def resolve_workspace(value: Path) -> Path:
    raw = Path(os.path.abspath(value))
    if is_link_like(raw):
        raise PathError(
            "workspace 根目录不能是符号链接或 junction",
            code="PATH_WORKSPACE_LINK",
            path=str(raw),
        )
    if not raw.is_dir():
        raise PathError(
            "workspace 根目录不存在或不是目录",
            code="PATH_WORKSPACE_MISSING",
            path=str(raw),
        )
    return raw.resolve(strict=True)


def resolve_input(
    workspace: Path,
    value: Path,
    *,
    label: str,
    expect: str,
) -> Path:
    workspace = resolve_workspace(workspace)
    raw_value = Path(value)
    _reject_parent_segments(raw_value, label=label)
    raw = raw_value if raw_value.is_absolute() else workspace / raw_value
    absolute = Path(os.path.abspath(raw))
    _ensure_contained(workspace, absolute, label=label)
    _ensure_no_links(workspace, absolute, label=label)
    if not absolute.exists():
        raise PathError(
            f"{label} 不存在",
            code="PATH_INPUT_MISSING",
            path=str(absolute),
        )
    if expect == "file" and not absolute.is_file():
        raise PathError(
            f"{label} 必须是文件",
            code="PATH_EXPECTED_FILE",
            path=str(absolute),
        )
    if expect == "directory" and not absolute.is_dir():
        raise PathError(
            f"{label} 必须是目录",
            code="PATH_EXPECTED_DIRECTORY",
            path=str(absolute),
        )
    resolved = absolute.resolve(strict=True)
    _ensure_contained(workspace, resolved, label=label)
    return resolved


def resolve_output(
    workspace: Path,
    value: Path,
    *,
    label: str,
    source_roots: tuple[Path, ...] = (),
) -> Path:
    workspace = resolve_workspace(workspace)
    raw_value = Path(value)
    _reject_parent_segments(raw_value, label=label)
    raw = raw_value if raw_value.is_absolute() else workspace / raw_value
    absolute = Path(os.path.abspath(raw))
    _ensure_contained(workspace, absolute, label=label)
    _ensure_no_links(workspace, absolute, label=label)
    if absolute.exists():
        raise PathError(
            f"{label} 已存在，拒绝覆盖",
            code="PATH_OUTPUT_EXISTS",
            path=str(absolute),
        )
    for source in source_roots:
        resolved_source = source.resolve(strict=True)
        if absolute == resolved_source or absolute.is_relative_to(resolved_source):
            raise PathError(
                f"{label} 不能写入被评估 source",
                code="PATH_OUTPUT_IN_SOURCE",
                path=str(absolute),
            )
    return absolute


def relative_path(workspace: Path, path: Path) -> str:
    return path.resolve(strict=True).relative_to(workspace.resolve(strict=True)).as_posix()


def read_text(path: Path, *, limits: ResourceLimits = DEFAULT_LIMITS) -> str:
    size = path.stat().st_size
    if size > limits.max_text_bytes:
        raise SkillError(
            "文本资源超过读取上限",
            code="SKILL_TEXT_TOO_LARGE",
            path=str(path),
            guidance=f"单个文本资源不得超过 {limits.max_text_bytes} bytes。",
        )
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SkillError(
            "文本资源不是有效 UTF-8",
            code="SKILL_TEXT_NOT_UTF8",
            path=str(path),
        ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_document(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_identity(
    workspace: Path,
    source: Path,
    *,
    limits: ResourceLimits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    source = resolve_input(workspace, source, label="source", expect="directory")
    stack = [source]
    files: list[Path] = []
    entry_count = 0
    while stack:
        directory = stack.pop()
        for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold(), reverse=True):
            entry_count += 1
            if entry_count > limits.max_entries:
                raise SkillError(
                    "source tree 目录项数量超过上限",
                    code="SKILL_ENTRY_COUNT_LIMIT",
                    path=str(source),
                )
            if is_link_like(child):
                raise PathError(
                    "source tree 包含符号链接或 junction",
                    code="PATH_SOURCE_LINK",
                    path=str(child),
                )
            if child.name in IGNORED_DIRECTORY_NAMES and child.is_dir():
                continue
            if child.name in IGNORED_FILE_NAMES and child.is_file():
                continue
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                files.append(child)
            else:
                raise PathError(
                    "source tree 包含不受支持的特殊文件",
                    code="PATH_SPECIAL_FILE",
                    path=str(child),
                )
            if len(files) > limits.max_files:
                raise SkillError(
                    "source tree 文件数量超过上限",
                    code="SKILL_FILE_COUNT_LIMIT",
                    path=str(source),
                )

    manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(files, key=lambda item: item.relative_to(source).as_posix()):
        size = path.stat().st_size
        if size > limits.max_file_bytes:
            raise SkillError(
                "source tree 存在超过单文件上限的资源",
                code="SKILL_FILE_SIZE_LIMIT",
                path=str(path),
            )
        total_bytes += size
        if total_bytes > limits.max_total_bytes:
            raise SkillError(
                "source tree 总大小超过上限",
                code="SKILL_TOTAL_SIZE_LIMIT",
                path=str(source),
            )
        manifest.append(
            {
                "path": path.relative_to(source).as_posix(),
                "size": size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "path": source.relative_to(workspace).as_posix(),
        "tree_sha256": hash_document(manifest),
        "file_count": len(manifest),
        "total_bytes": total_bytes,
        "files": manifest,
    }
