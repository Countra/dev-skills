"""同目录原子文件写入工具。"""

from __future__ import annotations

import errno
import json
import math
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .errors import OperationConflictError, StateError


WINDOWS_FILE_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.32)
WINDOWS_RETRYABLE_FILE_ERRORS = {5, 32, 33}
WINDOWS_LOCK_CONTENTION_ERRORS = {32, 33}


def _windows_file_retry_enabled() -> bool:
    return os.name == "nt"


def _is_lock_contention_error(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in WINDOWS_LOCK_CONTENTION_ERRORS
    return exc.errno in {errno.EACCES, errno.EAGAIN}


def retry_windows_file_operation(operation: Callable[[], object]) -> None:
    for attempt in range(len(WINDOWS_FILE_RETRY_DELAYS) + 1):
        try:
            operation()
            return
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            retryable = _windows_file_retry_enabled() and (
                isinstance(exc, PermissionError) or winerror in WINDOWS_RETRYABLE_FILE_ERRORS
            )
            if not retryable or attempt >= len(WINDOWS_FILE_RETRY_DELAYS):
                raise
            time.sleep(WINDOWS_FILE_RETRY_DELAYS[attempt])


def open_private_binary_append(path: Path) -> BinaryIO:
    """以私有权限打开普通文件，并拒绝 POSIX 链接与跨用户 owner。"""

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_APPEND
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        value = os.fstat(descriptor)
        if not stat.S_ISREG(value.st_mode):
            raise StateError(f"私有 append 目标不是普通文件: {path.name}")
        getuid = getattr(os, "getuid", None)
        if getuid is not None and value.st_uid != getuid():
            raise StateError(f"私有 append 目标 owner 不属于当前用户: {path.name}")
        fchmod = getattr(os, "fchmod", None)
        if fchmod is not None:
            fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "ab", buffering=0)
        descriptor = -1
        return handle
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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
        retry_windows_file_operation(lambda: os.replace(temporary, path))
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


class InterProcessFileLock:
    """使用 OS 文件锁串行化 workspace 内的短生命周期控制操作。"""

    def __init__(self, path: Path, *, timeout: float, poll_interval: float = 0.05) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout < 0
        ):
            raise ValueError("lock timeout 必须是有限非负数")
        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or not math.isfinite(float(poll_interval))
            or poll_interval <= 0
        ):
            raise ValueError("lock poll interval 必须是有限正数")
        timeout = float(timeout)
        poll_interval = float(poll_interval)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._handle = path.open("a+b")
        self._locked = False
        try:
            if path.stat().st_size == 0:
                self._handle.write(b"\0")
                self._handle.flush()
                os.fsync(self._handle.fileno())
            os.chmod(path, 0o600)
            self._acquire(timeout, poll_interval)
        except BaseException:
            self._handle.close()
            raise

    def _try_lock(self) -> bool:
        self._handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if _is_lock_contention_error(exc):
                return False
            raise
        self._locked = True
        return True

    def _acquire(self, timeout: float, poll_interval: float) -> None:
        deadline = time.monotonic() + timeout
        while not self._try_lock():
            if time.monotonic() >= deadline:
                raise OperationConflictError(
                    "manager operation 正在由另一个调用者执行",
                    recommended_action="status",
                )
            time.sleep(max(0.001, poll_interval))

    def close(self) -> None:
        if self._handle.closed:
            return
        try:
            if self._locked:
                self._handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False
            self._handle.close()

    def __enter__(self) -> "InterProcessFileLock":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.close()
