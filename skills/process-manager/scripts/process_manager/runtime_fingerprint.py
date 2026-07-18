"""计算 manager 受控 Python runtime 的稳定内容指纹。"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import EnvironmentUnverifiableError


DOMAIN = b"dev-skills/process-manager/runtime-fingerprint/v1\0"
MAX_FILES = 128
MAX_DISCOVERED_ENTRIES = 512
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    size: int
    identity: tuple[int, int, int, int]
    content: bytes


def _is_reparse(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _safe_lstat(path: Path) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError as exc:
        raise EnvironmentUnverifiableError(
            "manager runtime manifest 无法读取",
            diagnostics={"path": str(path), "failure": type(exc).__name__},
            recommended_action="doctor",
        ) from exc
    if stat.S_ISLNK(value.st_mode) or _is_reparse(value):
        raise EnvironmentUnverifiableError(
            "manager runtime manifest 包含 symlink 或 reparse point",
            diagnostics={"path": str(path)},
            recommended_action="doctor",
        )
    return value


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
    )


def _contained(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _discover_files(scripts_root: Path) -> list[tuple[str, Path]]:
    lexical_root = Path(os.path.abspath(scripts_root))
    root_stat = _safe_lstat(lexical_root)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise EnvironmentUnverifiableError("manager runtime manifest root 不是目录")
    scripts_root = lexical_root.resolve(strict=True)
    package_root = scripts_root / "process_manager"
    manager_script = scripts_root / "manager_server.py"
    package_stat = _safe_lstat(package_root)
    manager_stat = _safe_lstat(manager_script)
    if not stat.S_ISDIR(package_stat.st_mode):
        raise EnvironmentUnverifiableError("manager runtime manifest root 不是目录")
    if not stat.S_ISREG(manager_stat.st_mode):
        raise EnvironmentUnverifiableError("manager_server.py 不是 regular file")
    if not _contained(package_root, scripts_root) or not _contained(manager_script, scripts_root):
        raise EnvironmentUnverifiableError("manager runtime manifest root 越界")

    discovered: list[tuple[str, Path]] = [("manager_server.py", manager_script)]
    pending = [package_root]
    scanned_entries = 0
    while pending:
        directory = pending.pop()
        directory_stat = _safe_lstat(directory)
        if not stat.S_ISDIR(directory_stat.st_mode) or not _contained(directory, scripts_root):
            raise EnvironmentUnverifiableError("manager runtime package 路径无效")
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise EnvironmentUnverifiableError(
                "manager runtime package 无法枚举",
                diagnostics={"path": str(directory), "failure": type(exc).__name__},
            ) from exc
        for child in children:
            scanned_entries += 1
            if scanned_entries > MAX_DISCOVERED_ENTRIES:
                raise EnvironmentUnverifiableError(
                    "manager runtime manifest 扫描条目数超过上限",
                    diagnostics={"limit": MAX_DISCOVERED_ENTRIES},
                )
            child_stat = _safe_lstat(child)
            if stat.S_ISDIR(child_stat.st_mode):
                pending.append(child)
                continue
            if child.suffix != ".py":
                continue
            if not stat.S_ISREG(child_stat.st_mode) or not _contained(child, scripts_root):
                raise EnvironmentUnverifiableError(
                    "manager runtime Python manifest entry 无效",
                    diagnostics={"path": str(child)},
                )
            discovered.append((child.relative_to(scripts_root).as_posix(), child))
            if len(discovered) > MAX_FILES:
                raise EnvironmentUnverifiableError(
                    "manager runtime manifest 文件数超过上限",
                    diagnostics={"limit": MAX_FILES},
                )
    return sorted(discovered, key=lambda item: item[0])


def _read_pass(
    scripts_root: Path,
    *,
    reader: Callable[[Path], bytes],
) -> tuple[tuple[ManifestEntry, ...], str]:
    total = 0
    entries: list[ManifestEntry] = []
    for relative_path, path in _discover_files(scripts_root):
        before = _safe_lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise EnvironmentUnverifiableError("manager runtime entry 不是 regular file")
        if before.st_size > MAX_FILE_BYTES:
            raise EnvironmentUnverifiableError(
                "manager runtime entry 超过单文件上限",
                diagnostics={"path": relative_path, "limit": MAX_FILE_BYTES},
            )
        try:
            content = reader(path)
        except OSError as exc:
            raise EnvironmentUnverifiableError(
                "manager runtime entry 读取失败",
                diagnostics={"path": relative_path, "failure": type(exc).__name__},
            ) from exc
        after = _safe_lstat(path)
        if _identity(before) != _identity(after) or len(content) != after.st_size:
            raise EnvironmentUnverifiableError(
                "manager runtime entry 在读取期间发生变化",
                diagnostics={"path": relative_path},
            )
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise EnvironmentUnverifiableError(
                "manager runtime manifest 总内容超过上限",
                diagnostics={"limit": MAX_TOTAL_BYTES},
            )
        entries.append(ManifestEntry(relative_path, len(content), _identity(after), content))

    digest = hashlib.sha256()
    digest.update(DOMAIN)
    digest.update(len(entries).to_bytes(4, "big"))
    for entry in entries:
        encoded_path = entry.relative_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(4, "big"))
        digest.update(encoded_path)
        digest.update(entry.size.to_bytes(8, "big"))
        digest.update(entry.content)
    return tuple(entries), digest.hexdigest()


def compute_runtime_fingerprint(
    scripts_root: Path | None = None,
    *,
    reader: Callable[[Path], bytes] = Path.read_bytes,
) -> str:
    """执行两个独立 bounded pass；任一不稳定证据都 fail closed。"""

    root = scripts_root or Path(__file__).resolve().parents[1]
    try:
        first_entries, first_digest = _read_pass(root, reader=reader)
        second_entries, second_digest = _read_pass(root, reader=reader)
    except EnvironmentUnverifiableError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise EnvironmentUnverifiableError(
            "manager runtime fingerprint 无法验证",
            diagnostics={"failure": type(exc).__name__},
            recommended_action="doctor",
        ) from exc
    first_manifest = tuple((entry.relative_path, entry.size, entry.identity) for entry in first_entries)
    second_manifest = tuple((entry.relative_path, entry.size, entry.identity) for entry in second_entries)
    if first_digest != second_digest or first_manifest != second_manifest:
        raise EnvironmentUnverifiableError(
            "manager runtime manifest 连续读取不一致",
            recommended_action="doctor",
        )
    return first_digest
