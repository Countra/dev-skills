#!/usr/bin/env python3
"""在统一 deadline 内运行有限命令，并只回收本次进程树。"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness_state_errors import StateError
from harness_state_io import write_json_atomic


EXIT_TIMEOUT = 124
EXIT_CLEANUP_FAILED = 125
EXIT_LAUNCH_FAILED = 126
EXIT_CANCELLED = 130
FORCE_WAIT_SECONDS = 5.0


@dataclass
class WindowsJobState:
    """Job handle 与绑定竞态窗口内已生成的原始子进程。"""

    handle: Any | None
    preassignment_processes: dict[int, Any]


class BoundedCommandError(Exception):
    """命令保护参数或启动条件无效。"""

    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


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


def _posix_group_pids(process_group_id: int) -> list[int]:
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,pgid=,stat="],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return []
        except PermissionError:
            return [process_group_id]
        return [process_group_id]
    if completed.returncode != 0:
        return [process_group_id]
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
    for pid in dict.fromkeys(pids):
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if handle:
            tracked[pid] = handle
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

    for pid, handle in tracked.items():
        if not _windows_handle_running(handle):
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
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
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, ValueError):
            pass
        remaining = _wait_until_stopped(
            tracked,
            time.monotonic() + grace_seconds,
        )
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


def _terminate_posix_group(
    process: subprocess.Popen[Any],
    grace_seconds: float,
) -> tuple[bool, list[int]]:
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return True, []
    except PermissionError:
        return False, _posix_group_pids(process_group_id)
    deadline = time.monotonic() + grace_seconds
    process.poll()
    remaining = _posix_group_pids(process_group_id)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.05)
        process.poll()
        remaining = _posix_group_pids(process_group_id)
    if remaining:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            remaining = []
        except PermissionError:
            return False, remaining
        force_deadline = time.monotonic() + FORCE_WAIT_SECONDS
        while remaining and time.monotonic() < force_deadline:
            time.sleep(0.05)
            process.poll()
            remaining = _posix_group_pids(process_group_id)
    try:
        process.wait(timeout=0.1)
    except (OSError, subprocess.SubprocessError):
        pass
    return not remaining, remaining


def terminate_process_tree(
    process: subprocess.Popen[Any],
    grace_seconds: float,
    windows_job: Any | None = None,
) -> tuple[bool, list[int]]:
    """按平台回收本次命令树，并返回仍存活的精确 PID。"""

    if os.name == "nt":
        return _terminate_windows_tree(process, grace_seconds, windows_job)
    return _terminate_posix_group(process, grace_seconds)


def remaining_process_tree_pids(process: subprocess.Popen[Any]) -> list[int]:
    """检查根进程退出后仍留在本次树中的子进程。"""

    if os.name == "nt":
        return [
            pid
            for pid in _windows_descendant_pids(process.pid)
            if _windows_process_running(pid)
        ]
    return _posix_group_pids(process.pid)


def cleanup_completed_process_tree(
    process: subprocess.Popen[Any],
    grace_seconds: float,
    windows_job: Any | None,
) -> tuple[bool, list[int]]:
    """回收正常 root 退出后仍可能存活的子进程。"""

    if os.name == "nt":
        tracked = (
            dict(windows_job.preassignment_processes)
            if isinstance(windows_job, WindowsJobState)
            else _track_windows_processes(_windows_descendant_pids(process.pid))
        )
        closed = _close_windows_job(windows_job) if windows_job is not None else True
        try:
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
    remaining = remaining_process_tree_pids(process)
    if not remaining:
        return True, []
    return terminate_process_tree(process, grace_seconds, windows_job)


def run_bounded_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    grace_seconds: float,
) -> tuple[int, dict[str, Any]]:
    """运行一个无 shell 的有限命令并返回稳定结果。"""

    started_at = _timestamp()
    started_monotonic = time.monotonic()
    popen_options: dict[str, Any] = {"cwd": str(cwd)}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
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
    windows_job = _create_windows_job(process) if os.name == "nt" else None
    try:
        exit_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        cleanup_verified, failure_pids = terminate_process_tree(
            process,
            grace_seconds,
            windows_job,
        )
        if not cleanup_verified:
            payload = _result(
                started_at=started_at,
                started_monotonic=started_monotonic,
                result="failed",
                exit_code=EXIT_CLEANUP_FAILED,
                termination="cleanup-failed",
                cleanup_verified=False,
                pid=process.pid,
                cleanup_failure_pids=failure_pids,
                error_code="RUN_STATE_COMMAND_CLEANUP_FAILED",
                error="deadline 后仍有本次命令树进程存活。",
            )
            return EXIT_CLEANUP_FAILED, payload
        payload = _result(
            started_at=started_at,
            started_monotonic=started_monotonic,
            result="failed",
            exit_code=EXIT_TIMEOUT,
            termination="timeout",
            cleanup_verified=True,
            pid=process.pid,
            cleanup_failure_pids=[],
            error_code="RUN_STATE_COMMAND_TIMEOUT",
            error="命令超过 deadline，已完成有界清理。",
        )
        return EXIT_TIMEOUT, payload
    except KeyboardInterrupt:
        cleanup_verified, failure_pids = terminate_process_tree(
            process,
            grace_seconds,
            windows_job,
        )
        exit_code = EXIT_CANCELLED if cleanup_verified else EXIT_CLEANUP_FAILED
        payload = _result(
            started_at=started_at,
            started_monotonic=started_monotonic,
            result="failed",
            exit_code=exit_code,
            termination="cancelled" if cleanup_verified else "cleanup-failed",
            cleanup_verified=cleanup_verified,
            pid=process.pid,
            cleanup_failure_pids=failure_pids,
            error_code=(
                "RUN_STATE_COMMAND_CANCELLED"
                if cleanup_verified
                else "RUN_STATE_COMMAND_CLEANUP_FAILED"
            ),
            error=(
                "用户取消后已完成有界清理。"
                if cleanup_verified
                else "用户取消后仍有本次命令树进程存活。"
            ),
        )
        return exit_code, payload
    cleanup_verified, failure_pids = cleanup_completed_process_tree(
        process,
        grace_seconds,
        windows_job,
    )
    if not cleanup_verified:
        payload = _result(
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
        return EXIT_CLEANUP_FAILED, payload
    payload = _result(
        started_at=started_at,
        started_monotonic=started_monotonic,
        result="passed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        termination="completed",
        cleanup_verified=True,
        pid=process.pid,
        cleanup_failure_pids=[],
        error_code=None,
        error=None,
    )
    return exit_code, payload


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是正数秒数。") from exc
    if seconds <= 0:
        raise argparse.ArgumentTypeError("必须是正数秒数。")
    return seconds


def _resolve_result_path(cwd: Path, raw: str | None) -> Path | None:
    if raw is None:
        return None
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise BoundedCommandError(
            "RUN_STATE_COMMAND_LAUNCH_FAILED",
            "--result-json 必须是 --cwd 内的相对路径。",
            EXIT_LAUNCH_FAILED,
        )
    resolved = (cwd / relative).resolve(strict=False)
    try:
        resolved.relative_to(cwd)
    except ValueError as exc:
        raise BoundedCommandError(
            "RUN_STATE_COMMAND_LAUNCH_FAILED",
            "--result-json 解析后越出 --cwd。",
            EXIT_LAUNCH_FAILED,
        ) from exc
    return resolved


def _persist_result(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    write_json_atomic(
        path,
        payload,
        error_code="RUN_STATE_COMMAND_RESULT_WRITE_FAILED",
        label="bounded command result",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="在 deadline 内运行一个有限命令")
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=_positive_seconds, required=True)
    parser.add_argument("--grace-seconds", type=_positive_seconds, default=5.0)
    parser.add_argument("--result-json")
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
        result_path = _resolve_result_path(cwd, args.result_json)
        exit_code, payload = run_bounded_command(
            command,
            cwd=cwd,
            timeout_seconds=args.timeout_seconds,
            grace_seconds=args.grace_seconds,
        )
        _persist_result(result_path, payload)
    except BoundedCommandError as exc:
        print(f"FAIL [{exc.code}]: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except (OSError, StateError) as exc:
        code = getattr(exc, "code", "RUN_STATE_COMMAND_RESULT_WRITE_FAILED")
        message = getattr(exc, "message", str(exc))
        print(f"FAIL [{code}]: {message}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
