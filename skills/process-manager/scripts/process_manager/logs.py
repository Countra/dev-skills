"""轮转日志的有界读取与增量扫描。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import RequestError, StateError


MAX_TAIL_LINES = 10000
MAX_TAIL_BYTES = 1024 * 1024


def rotated_paths(path: Path, backups: int) -> list[Path]:
    return [
        *(path.with_name(f"{path.name}.{index}") for index in range(backups, 0, -1)),
        path,
    ]


def _read_slice(path: Path, offset: int, size: int) -> bytes:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(size)
    except OSError as exc:
        raise StateError(f"日志不可读: {path.name}") from exc


def read_log_tail(path: Path, backups: int, *, tail_lines: int, max_bytes: int) -> dict[str, Any]:
    if not 1 <= tail_lines <= MAX_TAIL_LINES:
        raise RequestError(f"tail 必须是 1-{MAX_TAIL_LINES}")
    if not 1024 <= max_bytes <= MAX_TAIL_BYTES:
        raise RequestError(f"maxBytes 必须是 1024-{MAX_TAIL_BYTES}")
    existing: list[tuple[Path, int]] = []
    for candidate in rotated_paths(path, backups):
        try:
            if candidate.is_symlink():
                raise StateError(f"日志路径不能是 symlink: {candidate.name}")
            if candidate.is_file():
                existing.append((candidate, candidate.stat().st_size))
        except OSError as exc:
            raise StateError(f"日志 metadata 不可读: {candidate.name}") from exc
    total_bytes = sum(size for _, size in existing)
    remaining = max_bytes
    selected: list[tuple[Path, bytes]] = []
    for candidate, size in reversed(existing):
        if remaining <= 0:
            break
        take = min(size, remaining)
        selected.append((candidate, _read_slice(candidate, size - take, take)))
        remaining -= take
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

    @staticmethod
    def _identity(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return (int(stat.st_dev), int(stat.st_ino))

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
        try:
            existing: list[Path] = []
            for candidate in rotated_paths(self.path, self.backups):
                if candidate.is_symlink():
                    raise StateError(f"日志路径不能是 symlink: {candidate.name}")
                if candidate.is_file():
                    existing.append(candidate)
        except OSError as exc:
            raise StateError("readiness 日志 metadata 不可读") from exc
        appended = False
        if not self._initialized:
            sizes = [(candidate, candidate.stat().st_size) for candidate in existing]
            total = sum(size for _, size in sizes)
            skip = max(0, total - remaining)
            for candidate, size in sizes:
                identity = self._identity(candidate)
                self._offsets[identity] = size
                if skip >= size:
                    skip -= size
                    continue
                data = _read_slice(candidate, skip, size - skip)
                skip = 0
                self._buffer.extend(data)
                self.bytes_scanned += len(data)
                appended = appended or bool(data)
            self._initialized = True
            return appended
        for candidate in existing:
            if remaining <= 0:
                break
            identity = self._identity(candidate)
            size = candidate.stat().st_size
            offset = min(self._offsets.get(identity, 0), size)
            take = min(size - offset, remaining)
            if take > 0:
                data = _read_slice(candidate, offset, take)
                self._buffer.extend(data)
                self.bytes_scanned += len(data)
                remaining -= len(data)
                offset += len(data)
                appended = appended or bool(data)
            self._offsets[identity] = offset
        current_identities = {self._identity(candidate) for candidate in existing}
        self._offsets = {
            identity: offset for identity, offset in self._offsets.items() if identity in current_identities
        }
        return appended
