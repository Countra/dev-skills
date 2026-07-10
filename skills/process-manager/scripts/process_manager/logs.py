"""轮转日志的有界读取与增量扫描。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, BinaryIO

from .errors import RequestError, StateError


MAX_TAIL_LINES = 10000
MAX_TAIL_BYTES = 1024 * 1024


def rotated_paths(path: Path, backups: int) -> list[Path]:
    return [
        *(path.with_name(f"{path.name}.{index}") for index in range(backups, 0, -1)),
        path,
    ]


def _open_log(path: Path) -> BinaryIO | None:
    try:
        if path.is_symlink():
            raise StateError(f"日志路径不能是 symlink: {path.name}")
        return path.open("rb")
    except FileNotFoundError:
        return None
    except StateError:
        raise
    except OSError as exc:
        raise StateError(f"日志不可读: {path.name}") from exc


def read_log_tail(path: Path, backups: int, *, tail_lines: int, max_bytes: int) -> dict[str, Any]:
    if not 1 <= tail_lines <= MAX_TAIL_LINES:
        raise RequestError(f"tail 必须是 1-{MAX_TAIL_LINES}")
    if not 1024 <= max_bytes <= MAX_TAIL_BYTES:
        raise RequestError(f"maxBytes 必须是 1024-{MAX_TAIL_BYTES}")
    total_bytes = 0
    remaining = max_bytes
    selected: list[tuple[Path, bytes]] = []
    identities: set[tuple[int, int]] = set()
    for candidate in reversed(rotated_paths(path, backups)):
        handle = _open_log(candidate)
        if handle is None:
            continue
        try:
            with handle:
                stat = os.fstat(handle.fileno())
                identity = (int(stat.st_dev), int(stat.st_ino))
                if identity in identities:
                    continue
                identities.add(identity)
                size = int(stat.st_size)
                total_bytes += size
                if remaining <= 0:
                    continue
                take = min(size, remaining)
                handle.seek(size - take)
                data = handle.read(take)
                selected.append((candidate, data))
                remaining -= len(data)
        except OSError as exc:
            raise StateError(f"日志读取失败: {candidate.name}") from exc
    selected.reverse()
    payload = b"".join(data for _, data in selected)
    text = payload.decode("utf-8", errors="replace")
    lines = text.splitlines()
    truncated = total_bytes > len(payload) or len(lines) > tail_lines
    return {
        "lines": lines[-tail_lines:],
        "bytesRead": len(payload),
        "availableBytes": total_bytes,
        "truncated": truncated,
        "files": [{"name": candidate.name, "bytesRead": len(data)} for candidate, data in selected],
    }


class IncrementalLogScanner:
    """按文件身份跟踪轮转日志，整个 probe 只读取 scanBytes。"""

    def __init__(self, path: Path, backups: int, scan_bytes: int) -> None:
        self.path = path
        self.backups = backups
        self.scan_bytes = scan_bytes
        self.bytes_scanned = 0
        self._offsets: dict[tuple[int, int], int] = {}
        self._buffer = bytearray()
        self._initialized = False

    @property
    def exhausted(self) -> bool:
        return self.bytes_scanned >= self.scan_bytes

    @property
    def text(self) -> str:
        return bytes(self._buffer).decode("utf-8", errors="replace")

    def scan(self) -> bool:
        remaining = self.scan_bytes - self.bytes_scanned
        if remaining <= 0:
            return False
        appended = False
        if not self._initialized:
            chunks: list[bytes] = []
            identities: set[tuple[int, int]] = set()
            for candidate in reversed(rotated_paths(self.path, self.backups)):
                handle = _open_log(candidate)
                if handle is None:
                    continue
                try:
                    with handle:
                        stat = os.fstat(handle.fileno())
                        identity = (int(stat.st_dev), int(stat.st_ino))
                        if identity in identities:
                            continue
                        identities.add(identity)
                        size = int(stat.st_size)
                        self._offsets[identity] = size
                        if remaining <= 0:
                            continue
                        take = min(size, remaining)
                        handle.seek(size - take)
                        data = handle.read(take)
                        chunks.append(data)
                        self.bytes_scanned += len(data)
                        remaining -= len(data)
                except OSError as exc:
                    raise StateError("readiness 日志读取失败") from exc
            for data in reversed(chunks):
                self._buffer.extend(data)
                appended = appended or bool(data)
            self._initialized = True
            return appended
        current_identities: set[tuple[int, int]] = set()
        for candidate in rotated_paths(self.path, self.backups):
            if remaining <= 0:
                break
            handle = _open_log(candidate)
            if handle is None:
                continue
            try:
                with handle:
                    stat = os.fstat(handle.fileno())
                    identity = (int(stat.st_dev), int(stat.st_ino))
                    if identity in current_identities:
                        continue
                    current_identities.add(identity)
                    size = int(stat.st_size)
                    offset = min(self._offsets.get(identity, 0), size)
                    take = min(size - offset, remaining)
                    if take > 0:
                        handle.seek(offset)
                        data = handle.read(take)
                        self._buffer.extend(data)
                        self.bytes_scanned += len(data)
                        remaining -= len(data)
                        offset += len(data)
                        appended = appended or bool(data)
                    self._offsets[identity] = offset
            except OSError as exc:
                raise StateError("readiness 日志读取失败") from exc
        self._offsets = {
            identity: offset for identity, offset in self._offsets.items() if identity in current_identities
        }
        return appended
