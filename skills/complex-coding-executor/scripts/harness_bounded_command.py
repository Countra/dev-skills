#!/usr/bin/env python3
"""在统一 deadline 内运行有限命令，并只回收本次进程树。"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
import signal
import subprocess
import sys
import time
from ctypes import wintypes
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

EXIT_TIMEOUT = 124
EXIT_CLEANUP_FAILED = 125
EXIT_LAUNCH_FAILED = 126
EXIT_CANCELLED = 130
FORCE_WAIT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 86_400.0
MAX_GRACE_SECONDS = 300.0
DEFAULT_HEARTBEAT_SECONDS = 15.0
MAX_HEARTBEAT_SECONDS = 300.0
WAIT_POLL_SECONDS = 0.1


@dataclass
class WindowsJobState:
    """Job handle 与绑定竞态窗口内已生成的原始子进程。"""

    handle: Any | None
    preassignment_processes: dict[int, Any]


@dataclass(frozen=True)
class PosixProcessIdentity:
    """用于阻断 PID、PGID 与 session 数字复用。"""

    pid: int
    start_time: str
    process_group_id: int
    session_id: int


@dataclass
class PosixGroupTracker:
    """记录本次 POSIX session 内已验证的进程身份。"""

    process_group_id: int
    session_id: int
    members: dict[int, PosixProcessIdentity]
    observed_empty: bool = False

    def inspect(self, deadline: float) -> list[int]:
        while True:
            pids = _posix_group_pids(self.process_group_id, deadline)
            if not pids:
                self.observed_empty = True
                return []
            if self.observed_empty:
                raise PosixInspectionError("进程组已为空后出现数字复用")
            restart = False
            for pid in pids:
                try:
                    identity = _posix_process_identity(pid)
                except PosixInspectionError:
                    # 进程可能在 ps 与身份读取之间正常退出；只对仍存在的 PID 失败关闭。
                    refreshed = _posix_group_pids(
                        self.process_group_id,
                        deadline,
                    )
                    if pid not in refreshed:
                        restart = True
                        break
                    raise
                if (
                    identity.process_group_id != self.process_group_id
                    or identity.session_id != self.session_id
                ):
                    raise PosixInspectionError(
                        "进程组成员身份不属于本次 session"
                    )
                previous = self.members.get(pid)
                if previous is not None and previous != identity:
                    raise PosixInspectionError("进程身份发生复用")
                self.members[pid] = identity
            if not restart:
                return pids


@dataclass
class CancellationState:
    """记录第一次可捕获取消，避免与 deadline 竞态漂移。"""

    reason: str | None = None
    requested_at: float | None = None

    def request(self, reason: str) -> None:
        if self.reason is None:
            self.reason = reason
            self.requested_at = time.monotonic()


class StatusReporter:
    """尽力输出状态；输出端关闭不能影响进程清理。"""

    def __init__(self) -> None:
        self.enabled = True

    def emit(self, message: str) -> None:
        if not self.enabled:
            return
        try:
            print(message, file=sys.stderr, flush=True)
        except (BrokenPipeError, OSError, ValueError):
            self.enabled = False


class BoundedCommandError(Exception):
    """命令保护参数或启动条件无效。"""

    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


class PosixInspectionError(Exception):
    """POSIX 进程身份无法在 cleanup budget 内安全验证。"""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(
    *,
    started_at: str,
    started_monotonic: float,
    result: str,
    exit_code: int,
    termination: str,
    cleanup_verified: bool,
    pid: int | None,
    cleanup_failure_pids: list[int],
    error_code: str | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "kind": "bounded-command-result",
        "started_at": started_at,
        "finished_at": _timestamp(),
        "duration_ms": max(0, round((time.monotonic() - started_monotonic) * 1000)),
        "result": result,
        "exit_code": exit_code,
        "termination": termination,
        "cleanup_verified": cleanup_verified,
        "pid": pid,
        "cleanup_failure_pids": sorted(set(cleanup_failure_pids)),
        "error_code": error_code,
        "error": error,
    }


class _MacProcBsdInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


def _posix_process_identity(pid: int) -> PosixProcessIdentity:
    if sys.platform.startswith("linux"):
        try:
            text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            closing = text.rfind(")")
            fields = text[closing + 2 :].split()
            return PosixProcessIdentity(
                pid=pid,
                start_time=fields[19],
                process_group_id=int(fields[2]),
                session_id=int(fields[3]),
            )
        except (OSError, IndexError, ValueError) as exc:
            raise PosixInspectionError("Linux 进程身份不可读取") from exc
    if sys.platform == "darwin":
        try:
            library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            library.proc_pidinfo.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            library.proc_pidinfo.restype = ctypes.c_int
            info = _MacProcBsdInfo()
            read = library.proc_pidinfo(
                pid,
                3,
                0,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            session_id = os.getsid(pid)
        except (AttributeError, OSError) as exc:
            raise PosixInspectionError("macOS 进程身份不可读取") from exc
        if (
            read != ctypes.sizeof(info)
            or info.pbi_pid != pid
            or info.pbi_start_tvsec <= 0
            or info.pbi_start_tvusec >= 1_000_000
        ):
            raise PosixInspectionError("macOS 进程身份不可读取")
        return PosixProcessIdentity(
            pid=pid,
            start_time=str(
                info.pbi_start_tvsec * 1_000_000 + info.pbi_start_tvusec
            ),
            process_group_id=int(info.pbi_pgid),
            session_id=session_id,
        )
    raise PosixInspectionError(f"不支持的 POSIX 平台：{sys.platform}")


def _create_posix_tracker(process: subprocess.Popen[Any]) -> PosixGroupTracker:
    identity = _posix_process_identity(process.pid)
    if (
        identity.process_group_id != process.pid
        or identity.session_id != process.pid
    ):
        raise PosixInspectionError("目标未建立独立 POSIX session")
    return PosixGroupTracker(
        process_group_id=identity.process_group_id,
        session_id=identity.session_id,
        members={identity.pid: identity},
    )


def _posix_group_pids(process_group_id: int, deadline: float) -> list[int]:
    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds <= 0:
        raise PosixInspectionError("POSIX 成员查询超过 cleanup deadline")
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,pgid=,stat="],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=min(1.0, remaining_seconds),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PosixInspectionError("POSIX 成员查询失败") from exc
    if completed.returncode != 0:
        raise PosixInspectionError("POSIX 成员查询返回失败")
    matches: list[int] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        try:
            pid = int(fields[0])
            group_id = int(fields[1])
        except ValueError:
            continue
        if group_id == process_group_id and not fields[2].startswith("Z"):
            matches.append(pid)
    return sorted(set(matches))


def _windows_descendant_pids(root_pid: int) -> list[int]:
    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not snapshot or snapshot == invalid_handle:
        return []
    children: dict[int, list[int]] = {}
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        available = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
        while available:
            parent = int(entry.th32ParentProcessID)
            children.setdefault(parent, []).append(int(entry.th32ProcessID))
            available = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    descendants: list[int] = []
    pending = list(children.get(root_pid, []))
    while pending:
        pid = pending.pop()
        if pid in descendants:
            continue
        descendants.append(pid)
        pending.extend(children.get(pid, []))
    return sorted(descendants)


def _windows_process_running(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == 0x00000102
    finally:
        kernel32.CloseHandle(handle)


def _create_windows_job(process: subprocess.Popen[Any]) -> WindowsJobState | None:
    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    try:
        information = ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x00002000
        configured = kernel32.SetInformationJobObject(
            job,
            9,
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        process_handle = getattr(process, "_handle", None)
        try:
            process_handle_value = int(process_handle)
        except (TypeError, ValueError):
            process_handle_value = 0
        assigned = bool(
            configured
            and process_handle_value
            and kernel32.AssignProcessToJobObject(job, process_handle_value)
        )
        preassignment = _track_windows_processes(
            _windows_descendant_pids(process.pid)
        )
        if not assigned:
            kernel32.CloseHandle(job)
            return WindowsJobState(None, preassignment) if preassignment else None
        return WindowsJobState(job, preassignment)
    except BaseException:
        try:
            kernel32.CloseHandle(job)
        except Exception:
            pass
        raise


def _close_windows_job(job: Any) -> bool:
    handle = job.handle if isinstance(job, WindowsJobState) else job
    if handle is None:
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return bool(kernel32.CloseHandle(handle))


def _track_windows_processes(pids: Sequence[int]) -> dict[int, Any]:
    """持有原始进程 handle，避免退出后的 PID 复用造成误判或误杀。"""

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    tracked: dict[int, Any] = {}
    try:
        for pid in dict.fromkeys(pids):
            handle = kernel32.OpenProcess(0x00100000, False, pid)
            if handle:
                tracked[pid] = handle
    except BaseException:
        for handle in tracked.values():
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
        raise
    return tracked


def _windows_handle_running(handle: Any) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    return kernel32.WaitForSingleObject(handle, 0) == 0x00000102


def _close_windows_process_handles(tracked: Mapping[int, Any]) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    for handle in tracked.values():
        kernel32.CloseHandle(handle)


def _wait_until_stopped(
    tracked: Mapping[int, Any],
    deadline: float,
) -> list[int]:
    remaining = list(tracked)
    while remaining and time.monotonic() < deadline:
        remaining = [
            pid for pid in remaining if _windows_handle_running(tracked[pid])
        ]
        if remaining:
            time.sleep(0.05)
    return [pid for pid in remaining if _windows_handle_running(tracked[pid])]


def _force_kill_windows_pids(
    tracked: Mapping[int, Any],
    timeout_seconds: float,
) -> None:
    """只强制回收本次命令树中已追踪且仍存活的 PID。"""

    deadline = time.monotonic() + timeout_seconds
    for pid, handle in tracked.items():
        if not _windows_handle_running(handle):
            continue
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=remaining_seconds,
            )
        except (OSError, subprocess.SubprocessError):
            continue


def _terminate_windows_tree(
    process: subprocess.Popen[Any],
    grace_seconds: float,
    windows_job: Any | None,
) -> tuple[bool, list[int]]:
    tracked = (
        dict(windows_job.preassignment_processes)
        if isinstance(windows_job, WindowsJobState)
        else {}
    )
    current_pids = [process.pid, *_windows_descendant_pids(process.pid)]
    tracked.update(
        _track_windows_processes(
            [pid for pid in current_pids if pid not in tracked]
        )
    )
    remaining: list[int] = []
    try:
        break_sent = True
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            break_sent = False
        if break_sent:
            remaining = _wait_until_stopped(
                tracked,
                time.monotonic() + grace_seconds,
            )
        else:
            remaining = [
                pid
                for pid, handle in tracked.items()
                if _windows_handle_running(handle)
            ]
        if windows_job is not None:
            closed = _close_windows_job(windows_job)
            remaining = _wait_until_stopped(
                tracked,
                time.monotonic() + FORCE_WAIT_SECONDS,
            )
            if remaining:
                # Popen 与 Job 绑定之间存在极短竞态，已提前生成的子进程不会自动入 Job。
                _force_kill_windows_pids(
                    {pid: tracked[pid] for pid in remaining},
                    max(FORCE_WAIT_SECONDS, grace_seconds),
                )
                remaining = _wait_until_stopped(
                    tracked,
                    time.monotonic() + FORCE_WAIT_SECONDS,
                )
            return closed and not remaining, remaining
        if remaining:
            _force_kill_windows_pids(
                {pid: tracked[pid] for pid in remaining},
                max(FORCE_WAIT_SECONDS, grace_seconds),
            )
            remaining = _wait_until_stopped(
                tracked,
                time.monotonic() + FORCE_WAIT_SECONDS,
            )
        return not remaining, remaining
    finally:
        try:
            process.wait(timeout=0.1)
        except (OSError, subprocess.SubprocessError):
            pass
        _close_windows_process_handles(tracked)


def _stop_direct_process(
    process: subprocess.Popen[Any],
    graceful_deadline: float,
) -> bool:
    """身份不足时仍精确回收直接子进程，但不据此声称整棵树已清空。"""

    try:
        if process.poll() is not None:
            return True
        process.terminate()
        remaining_seconds = max(0.0, graceful_deadline - time.monotonic())
        if remaining_seconds > 0:
            try:
                process.wait(timeout=remaining_seconds)
                return True
            except subprocess.TimeoutExpired:
                pass
        process.kill()
        process.wait(timeout=FORCE_WAIT_SECONDS)
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            return process.poll() is not None
        except Exception:
            return False


def _terminate_posix_group(
    process: subprocess.Popen[Any],
    grace_seconds: float,
    tracker: PosixGroupTracker | None = None,
) -> tuple[bool, list[int]]:
    grace_deadline = time.monotonic() + grace_seconds
    try:
        tracker = tracker or _create_posix_tracker(process)
        remaining = tracker.inspect(grace_deadline)
    except PosixInspectionError:
        known = sorted(tracker.members) if tracker is not None else [process.pid]
        if _stop_direct_process(process, grace_deadline):
            known = [pid for pid in known if pid != process.pid]
        return False, known
    if not remaining:
        return True, []
    process_group_id = tracker.process_group_id
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        tracker.observed_empty = True
        return True, []
    except PermissionError:
        _stop_direct_process(process, grace_deadline)
        return False, remaining
    process.poll()
    while remaining and time.monotonic() < grace_deadline:
        time.sleep(
            min(0.05, max(0.0, grace_deadline - time.monotonic()))
        )
        process.poll()
        try:
            remaining = tracker.inspect(grace_deadline)
        except PosixInspectionError:
            _stop_direct_process(process, grace_deadline)
            return False, remaining
    if remaining:
        force_deadline = time.monotonic() + FORCE_WAIT_SECONDS
        try:
            remaining = tracker.inspect(force_deadline)
            if not remaining:
                return True, []
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            tracker.observed_empty = True
            remaining = []
        except (PermissionError, PosixInspectionError):
            _stop_direct_process(process, force_deadline)
            return False, remaining
        while remaining and time.monotonic() < force_deadline:
            time.sleep(
                min(0.05, max(0.0, force_deadline - time.monotonic()))
            )
            process.poll()
            try:
                remaining = tracker.inspect(force_deadline)
            except PosixInspectionError:
                _stop_direct_process(process, force_deadline)
                return False, remaining
    try:
        process.wait(timeout=0.1)
    except (OSError, subprocess.SubprocessError):
        pass
    return not remaining, remaining


def terminate_process_tree(
    process: subprocess.Popen[Any],
    grace_seconds: float,
    windows_job: Any | None = None,
    posix_tracker: PosixGroupTracker | None = None,
) -> tuple[bool, list[int]]:
    """按平台回收本次命令树，并返回仍存活的精确 PID。"""

    if os.name == "nt":
        return _terminate_windows_tree(process, grace_seconds, windows_job)
    return _terminate_posix_group(process, grace_seconds, posix_tracker)


def remaining_process_tree_pids(
    process: subprocess.Popen[Any],
    posix_tracker: PosixGroupTracker | None = None,
) -> list[int]:
    """检查根进程退出后仍留在本次树中的子进程。"""

    if os.name == "nt":
        return [
            pid
            for pid in _windows_descendant_pids(process.pid)
            if _windows_process_running(pid)
        ]
    tracker = posix_tracker or _create_posix_tracker(process)
    return tracker.inspect(time.monotonic() + 1.0)


def cleanup_completed_process_tree(
    process: subprocess.Popen[Any],
    grace_seconds: float,
    windows_job: Any | None,
    posix_tracker: PosixGroupTracker | None = None,
) -> tuple[bool, list[int]]:
    """回收正常 root 退出后仍可能存活的子进程。"""

    if os.name == "nt":
        tracked = (
            dict(windows_job.preassignment_processes)
            if isinstance(windows_job, WindowsJobState)
            else _track_windows_processes(_windows_descendant_pids(process.pid))
        )
        try:
            closed = _close_windows_job(windows_job) if windows_job is not None else True
            remaining = _wait_until_stopped(
                tracked,
                time.monotonic() + FORCE_WAIT_SECONDS,
            )
            if remaining:
                _force_kill_windows_pids(
                    {pid: tracked[pid] for pid in remaining},
                    max(FORCE_WAIT_SECONDS, grace_seconds),
                )
                remaining = _wait_until_stopped(
                    tracked,
                    time.monotonic() + FORCE_WAIT_SECONDS,
                )
            return closed and not remaining, remaining
        finally:
            _close_windows_process_handles(tracked)
    try:
        remaining = remaining_process_tree_pids(process, posix_tracker)
    except PosixInspectionError:
        known = (
            sorted(posix_tracker.members)
            if posix_tracker is not None
            else [process.pid]
        )
        return False, known
    if not remaining:
        return True, []
    return terminate_process_tree(
        process,
        grace_seconds,
        windows_job,
        posix_tracker,
    )


@contextmanager
def _temporary_cancellation_handlers(
    cancellation: CancellationState,
) -> Iterator[None]:
    previous: list[tuple[Any, Any]] = []

    def request_cancel(signum: int, _frame: Any) -> None:
        cancellation.request(signal.Signals(signum).name.lower())

    candidates = [
        getattr(signal, name, None)
        for name in ("SIGINT", "SIGTERM", "SIGHUP", "SIGBREAK")
    ]
    try:
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                previous.append((candidate, signal.getsignal(candidate)))
                signal.signal(candidate, request_cancel)
            except (OSError, ValueError):
                if previous and previous[-1][0] == candidate:
                    previous.pop()
        yield
    finally:
        for candidate, handler in reversed(previous):
            try:
                signal.signal(candidate, handler)
            except (OSError, ValueError):
                pass


def _wait_for_terminal(
    process: subprocess.Popen[Any],
    *,
    started_monotonic: float,
    timeout_seconds: float,
    heartbeat_seconds: float,
    reporter: StatusReporter | None,
    cancellation: CancellationState,
) -> tuple[str, int | None]:
    deadline = started_monotonic + timeout_seconds
    next_heartbeat = started_monotonic + heartbeat_seconds
    while True:
        now = time.monotonic()
        if (
            cancellation.requested_at is not None
            and cancellation.requested_at <= deadline
        ):
            return "cancelled", None
        if now >= deadline:
            return "timeout", None
        exit_code = process.poll()
        if exit_code is not None:
            return "completed", exit_code
        if reporter is not None and now >= next_heartbeat:
            elapsed = max(0.0, now - started_monotonic)
            remaining = max(0.0, deadline - now)
            reporter.emit(
                "bounded-command: heartbeat, "
                f"pid={process.pid}, elapsed={elapsed:.1f}s, "
                f"remaining={remaining:.1f}s"
            )
            while next_heartbeat <= now:
                next_heartbeat += heartbeat_seconds
        wake_at = min(deadline, next_heartbeat)
        try:
            time.sleep(
                min(
                    WAIT_POLL_SECONDS,
                    max(0.001, wake_at - time.monotonic()),
                )
            )
        except KeyboardInterrupt:
            cancellation.request("sigint")


def _cleanup_tree_safely(
    process: subprocess.Popen[Any],
    *,
    grace_seconds: float,
    windows_job: Any | None,
    posix_tracker: PosixGroupTracker | None,
    completed: bool,
) -> tuple[bool, list[int]]:
    try:
        if completed:
            return cleanup_completed_process_tree(
                process,
                grace_seconds,
                windows_job,
                posix_tracker,
            )
        return terminate_process_tree(
            process,
            grace_seconds,
            windows_job,
            posix_tracker,
        )
    except (Exception, KeyboardInterrupt):
        if os.name == "nt" and windows_job is not None:
            try:
                _close_windows_job(windows_job)
            except Exception:
                pass
        stopped = _stop_direct_process(process, time.monotonic())
        running = not stopped
        return False, [process.pid] if running else []


def run_bounded_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    grace_seconds: float,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    inherit_stdin: bool = False,
    reporter: StatusReporter | None = None,
) -> tuple[int, dict[str, Any]]:
    """运行一个无 shell 的有限命令并返回稳定结果。"""

    started_at = _timestamp()
    started_monotonic = time.monotonic()
    if reporter is not None:
        reporter.emit(
            "bounded-command: starting, "
            f"timeout={timeout_seconds:g}s"
        )
    popen_options: dict[str, Any] = {
        "cwd": str(cwd),
        "stdin": None if inherit_stdin else subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    cancellation = CancellationState()
    windows_job = None
    posix_tracker = None
    with _temporary_cancellation_handlers(cancellation):
        try:
            process = subprocess.Popen(list(command), **popen_options)
        except OSError as exc:
            payload = _result(
                started_at=started_at,
                started_monotonic=started_monotonic,
                result="failed",
                exit_code=EXIT_LAUNCH_FAILED,
                termination="launch-failed",
                cleanup_verified=True,
                pid=None,
                cleanup_failure_pids=[],
                error_code="RUN_STATE_COMMAND_LAUNCH_FAILED",
                error=f"{type(exc).__name__}: 命令未启动。",
            )
            return EXIT_LAUNCH_FAILED, payload
        if reporter is not None:
            reporter.emit(
                "bounded-command: started, "
                f"pid={process.pid}, timeout={timeout_seconds:g}s"
            )
        setup_error: Exception | None = None
        try:
            if os.name == "nt":
                windows_job = _create_windows_job(process)
            else:
                posix_tracker = _create_posix_tracker(process)
        except KeyboardInterrupt:
            cancellation.request("sigint")
        except Exception as exc:
            setup_error = exc
        if setup_error is not None:
            cleanup_verified, failure_pids = _cleanup_tree_safely(
                process,
                grace_seconds=grace_seconds,
                windows_job=windows_job,
                posix_tracker=posix_tracker,
                completed=False,
            )
            result_exit_code = (
                EXIT_LAUNCH_FAILED
                if cleanup_verified
                else EXIT_CLEANUP_FAILED
            )
            return result_exit_code, _result(
                started_at=started_at,
                started_monotonic=started_monotonic,
                result="failed",
                exit_code=result_exit_code,
                termination=(
                    "launch-failed"
                    if cleanup_verified
                    else "cleanup-failed"
                ),
                cleanup_verified=cleanup_verified,
                pid=process.pid,
                cleanup_failure_pids=failure_pids,
                error_code=(
                    "RUN_STATE_COMMAND_LAUNCH_FAILED"
                    if cleanup_verified
                    else "RUN_STATE_COMMAND_CLEANUP_FAILED"
                ),
                error=(
                    "进程隔离初始化失败，已回收本次命令树。"
                    if cleanup_verified
                    else "进程隔离初始化失败，且无法验证本次命令树已清空。"
                ),
            )
        terminal, child_exit_code = _wait_for_terminal(
            process,
            started_monotonic=started_monotonic,
            timeout_seconds=timeout_seconds,
            heartbeat_seconds=heartbeat_seconds,
            reporter=reporter,
            cancellation=cancellation,
        )
        if terminal == "completed":
            cleanup_verified, failure_pids = _cleanup_tree_safely(
                process,
                grace_seconds=grace_seconds,
                windows_job=windows_job,
                posix_tracker=posix_tracker,
                completed=True,
            )
            if not cleanup_verified:
                return EXIT_CLEANUP_FAILED, _result(
                    started_at=started_at,
                    started_monotonic=started_monotonic,
                    result="failed",
                    exit_code=EXIT_CLEANUP_FAILED,
                    termination="cleanup-failed",
                    cleanup_verified=False,
                    pid=process.pid,
                    cleanup_failure_pids=failure_pids,
                    error_code="RUN_STATE_COMMAND_CLEANUP_FAILED",
                    error="命令结束后仍有本次命令树进程存活。",
                )
            assert child_exit_code is not None
            return child_exit_code, _result(
                started_at=started_at,
                started_monotonic=started_monotonic,
                result="passed" if child_exit_code == 0 else "failed",
                exit_code=child_exit_code,
                termination="completed",
                cleanup_verified=True,
                pid=process.pid,
                cleanup_failure_pids=[],
                error_code=None,
                error=None,
            )
        cleanup_verified, failure_pids = _cleanup_tree_safely(
            process,
            grace_seconds=grace_seconds,
            windows_job=windows_job,
            posix_tracker=posix_tracker,
            completed=False,
        )
        if not cleanup_verified:
            return EXIT_CLEANUP_FAILED, _result(
                started_at=started_at,
                started_monotonic=started_monotonic,
                result="failed",
                exit_code=EXIT_CLEANUP_FAILED,
                termination="cleanup-failed",
                cleanup_verified=False,
                pid=process.pid,
                cleanup_failure_pids=failure_pids,
                error_code="RUN_STATE_COMMAND_CLEANUP_FAILED",
                error=(
                    "deadline 后仍有本次命令树进程存活。"
                    if terminal == "timeout"
                    else "用户取消后仍有本次命令树进程存活。"
                ),
            )
        result_exit_code = (
            EXIT_TIMEOUT if terminal == "timeout" else EXIT_CANCELLED
        )
        return result_exit_code, _result(
            started_at=started_at,
            started_monotonic=started_monotonic,
            result="failed",
            exit_code=result_exit_code,
            termination=terminal,
            cleanup_verified=True,
            pid=process.pid,
            cleanup_failure_pids=[],
            error_code=(
                "RUN_STATE_COMMAND_TIMEOUT"
                if terminal == "timeout"
                else "RUN_STATE_COMMAND_CANCELLED"
            ),
            error=(
                "命令超过 deadline，已完成有界清理。"
                if terminal == "timeout"
                else "用户取消后已完成有界清理。"
            ),
        )


def _bounded_seconds(value: str, *, maximum: float, option: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是正数秒数。") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("必须是正数秒数。")
    if seconds > maximum:
        raise argparse.ArgumentTypeError(
            f"{option} 不得超过 {maximum:g} 秒。"
        )
    return seconds


def _timeout_seconds(value: str) -> float:
    return _bounded_seconds(
        value,
        maximum=MAX_TIMEOUT_SECONDS,
        option="--timeout-seconds",
    )


def _grace_seconds(value: str) -> float:
    return _bounded_seconds(
        value,
        maximum=MAX_GRACE_SECONDS,
        option="--grace-seconds",
    )


def _heartbeat_seconds(value: str) -> float:
    return _bounded_seconds(
        value,
        maximum=MAX_HEARTBEAT_SECONDS,
        option="--heartbeat-seconds",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="在 deadline 内运行一个有限命令")
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=_timeout_seconds, required=True)
    parser.add_argument("--grace-seconds", type=_grace_seconds, default=5.0)
    parser.add_argument(
        "--heartbeat-seconds",
        type=_heartbeat_seconds,
        default=DEFAULT_HEARTBEAT_SECONDS,
    )
    parser.add_argument("--inherit-stdin", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    try:
        try:
            cwd = args.cwd.resolve(strict=True)
        except OSError as exc:
            raise BoundedCommandError(
                "RUN_STATE_COMMAND_LAUNCH_FAILED",
                "--cwd 不存在或不可访问。",
                EXIT_LAUNCH_FAILED,
            ) from exc
        if not cwd.is_absolute() or not cwd.is_dir():
            raise BoundedCommandError(
                "RUN_STATE_COMMAND_LAUNCH_FAILED",
                "--cwd 必须是绝对目录。",
                EXIT_LAUNCH_FAILED,
            )
        if not args.cwd.is_absolute():
            raise BoundedCommandError(
                "RUN_STATE_COMMAND_LAUNCH_FAILED",
                "--cwd 必须使用绝对路径。",
                EXIT_LAUNCH_FAILED,
            )
        if not command:
            raise BoundedCommandError(
                "RUN_STATE_COMMAND_LAUNCH_FAILED",
                "-- 后必须提供 program 和参数。",
                EXIT_LAUNCH_FAILED,
            )
        reporter = StatusReporter()
        exit_code, payload = run_bounded_command(
            command,
            cwd=cwd,
            timeout_seconds=args.timeout_seconds,
            grace_seconds=args.grace_seconds,
            heartbeat_seconds=args.heartbeat_seconds,
            inherit_stdin=args.inherit_stdin,
            reporter=reporter,
        )
    except BoundedCommandError as exc:
        print(f"FAIL [{exc.code}]: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except OSError as exc:
        print(f"FAIL [RUN_STATE_COMMAND_LAUNCH_FAILED]: {exc}", file=sys.stderr)
        return EXIT_LAUNCH_FAILED
    cleanup = "verified" if payload["cleanup_verified"] else "failed"
    remaining = payload["cleanup_failure_pids"]
    suffix = f", remaining-pids={','.join(map(str, remaining))}" if remaining else ""
    reporter.emit(
        "bounded-command: "
        f"{payload['termination']}, exit={payload['exit_code']}, "
        f"duration={payload['duration_ms']}ms, cleanup={cleanup}{suffix}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
