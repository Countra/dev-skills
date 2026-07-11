"""同目录原子文件写入工具。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import StateError


def read_json_file(path: Path, *, max_bytes: int) -> Any:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise StateError(f"JSON 文件超过读取上限: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"JSON 文件不存在: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError(f"JSON 文件不可读或格式错误: {path}") from exc


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    failure: BaseException | None = None
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            os.chmod(temporary, mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        # Windows 不支持目录 fsync；其他平台尽力同步目录项。
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    except OSError as exc:
        failure = StateError(f"原子写入失败: {path}")
        failure.__cause__ = exc
    except BaseException as exc:  # noqa: BLE001
        failure = exc
    if fd >= 0:
        try:
            os.close(fd)
        except OSError as close_error:
            if failure is None:
                failure = StateError(f"原子写入文件描述符关闭失败: {temporary}")
                failure.__cause__ = close_error
            elif hasattr(failure, "add_note"):
                failure.add_note(f"文件描述符关闭失败: {type(close_error).__name__}")
    try:
        temporary.unlink(missing_ok=True)
    except OSError as cleanup_error:
        if temporary.exists():
            if failure is None:
                raise StateError(f"原子写入临时文件清理失败: {temporary}") from cleanup_error
            if hasattr(failure, "add_note"):
                failure.add_note(f"临时文件清理失败: {type(cleanup_error).__name__}")
    if failure is not None:
        raise failure


def atomic_write_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    try:
        data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StateError(f"JSON 值无法序列化: {path}") from exc
    atomic_write_bytes(path, data, mode=mode)
