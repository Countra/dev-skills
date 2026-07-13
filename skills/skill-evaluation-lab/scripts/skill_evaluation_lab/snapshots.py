"""Skill 树的确定性清单、快照和完整性校验。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from .errors import ExecutionError, SuiteError


EXCLUDED_DIRS = {".git", ".harness", ".mypy_cache", ".pytest_cache", "__pycache__"}
EXCLUDED_FILES = {".DS_Store", "Thumbs.db"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_readonly(function: Any, path: str, _error: Any) -> None:
    Path(path).chmod(stat.S_IWRITE)
    function(path)


def _remove_snapshot(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=False, onerror=_remove_readonly)


def build_tree_manifest(root: Path) -> dict[str, Any]:
    """生成与平台无关的有序文件清单，并拒绝链接造成的边界模糊。"""
    if _is_link_or_junction(root):
        raise SuiteError(f"快照来源不能是链接或 junction：{root}", path="$.skill_path")
    root = root.resolve()
    if not root.is_dir():
        raise SuiteError(f"快照来源不是目录：{root}", path="$.skill_path")
    files: list[dict[str, Any]] = []
    for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_dirs: list[str] = []
        for name in sorted(dir_names):
            child = current_path / name
            if name in EXCLUDED_DIRS:
                continue
            if _is_link_or_junction(child):
                raise SuiteError(f"快照树包含链接或 junction：{child.relative_to(root)}", path="$.skill_path")
            safe_dirs.append(name)
        dir_names[:] = safe_dirs
        for name in sorted(file_names):
            path = current_path / name
            if name in EXCLUDED_FILES or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            if _is_link_or_junction(path):
                raise SuiteError(f"快照树包含文件链接：{path.relative_to(root)}", path="$.skill_path")
            relative = path.relative_to(root).as_posix()
            files.append({"path": relative, "size": path.stat().st_size, "sha256": _hash_file(path)})
    canonical = json.dumps(files, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"algorithm": "sha256", "tree_sha256": hashlib.sha256(canonical).hexdigest(), "files": files}


def create_snapshot(source: Path, destination: Path) -> dict[str, Any]:
    """复制确定性文件集并将快照文件标记为只读。"""
    if destination.exists():
        raise ExecutionError(f"快照目标已存在：{destination}")
    manifest = build_tree_manifest(source)
    destination.mkdir(parents=True)
    try:
        for item in manifest["files"]:
            source_file = source.resolve() / item["path"]
            target_file = destination / item["path"]
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
            mode = target_file.stat().st_mode
            target_file.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    except (OSError, shutil.Error) as exc:
        if destination.exists():
            try:
                _remove_snapshot(destination)
            except (OSError, shutil.Error) as cleanup_exc:
                raise ExecutionError(f"创建快照失败：{exc}；清理失败：{cleanup_exc}") from exc
        raise ExecutionError(f"创建快照失败：{exc}") from exc
    copied = build_tree_manifest(destination)
    if copied["tree_sha256"] != manifest["tree_sha256"]:
        try:
            _remove_snapshot(destination)
        except OSError as exc:
            raise ExecutionError(f"快照哈希不一致且清理失败：{exc}") from exc
        raise ExecutionError("快照复制后的内容哈希不一致")
    return manifest


def verify_tree(root: Path, expected: dict[str, Any]) -> None:
    """确认源树或快照自基线后未发生任何物质变化。"""
    actual = build_tree_manifest(root)
    if actual != expected:
        raise ExecutionError(
            f"目录完整性校验失败：期望 {expected.get('tree_sha256')}，实际 {actual.get('tree_sha256')}",
            outcome="failed",
        )
