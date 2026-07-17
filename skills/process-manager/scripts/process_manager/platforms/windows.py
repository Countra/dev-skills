"""Windows named mutex、Job Object 与进程身份实现。"""

from __future__ import annotations

import ctypes
import hashlib
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any

from ..errors import ConflictError, IdentityError, SupervisorError
from .base import (
    ManagerLock,
    OwnerInspection,
    PersistedOwnerEvidence,
    PlatformAdapter,
    PlatformSelection,
    RunOwner,
)
from .windows_acl import WindowsAcl


ERROR_ALREADY_EXISTS = 183
PROCESS_TERMINATE = 0x0001
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1


class LARGE_INTEGER(ctypes.Structure):
    _fields_ = [("QuadPart", ctypes.c_longlong)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", LARGE_INTEGER),
        ("PerJobUserTimeLimit", LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", LARGE_INTEGER),
        ("TotalKernelTime", LARGE_INTEGER),
        ("ThisPeriodTotalUserTime", LARGE_INTEGER),
        ("ThisPeriodTotalKernelTime", LARGE_INTEGER),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class WindowsApi:
    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32 = kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        kernel32.IsProcessInJob.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

    def close(self, handle: Any) -> None:
        if handle and not self.kernel32.CloseHandle(handle):
            raise SupervisorError("Win32 handle 关闭失败")

    @staticmethod
    def last_error(label: str) -> SupervisorError:
        code = ctypes.get_last_error()
        return SupervisorError(f"{label} 失败，Win32 error={code}")


class WindowsManagerLock(ManagerLock):
    def __init__(self, api: WindowsApi, name: str) -> None:
        self.api = api
        self.handle = api.kernel32.CreateMutexW(None, True, name)
        if not self.handle:
            raise api.last_error("CreateMutexW")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            api.close(self.handle)
            self.handle = None
            raise ConflictError("当前 workspace 已有 process-manager 实例")

    def close(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, None
            self.api.close(handle)


class WindowsJobOwner(RunOwner):
    def __init__(
        self,
        api: WindowsApi,
        selection: PlatformSelection,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> None:
        super().__init__(selection, host, capability_hash)
        self.api = api
        self.handle = api.kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise api.last_error("CreateJobObjectW")
        try:
            limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not api.kernel32.SetInformationJobObject(
                self.handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ):
                raise api.last_error("SetInformationJobObject")
            self._assign_pid(host.pid)
        except Exception:
            self._close_job()
            raise

    @property
    def control_data(self) -> dict[str, Any]:
        return {"mode": "windows-job"}

    def _open_process(self, pid: int, access: int) -> Any:
        handle = self.api.kernel32.OpenProcess(access, False, pid)
        if not handle:
            raise self.api.last_error("OpenProcess")
        return handle

    def _assign_pid(self, pid: int) -> None:
        process = self._open_process(pid, PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION)
        try:
            if not self.api.kernel32.AssignProcessToJobObject(self.handle, process):
                raise self.api.last_error("AssignProcessToJobObject")
        finally:
            self.api.close(process)

    def _contains_pid(self, pid: int) -> bool:
        try:
            process = self._open_process(pid, PROCESS_QUERY_LIMITED_INFORMATION)
        except SupervisorError:
            return False
        try:
            result = wintypes.BOOL()
            if not self.api.kernel32.IsProcessInJob(process, self.handle, ctypes.byref(result)):
                raise self.api.last_error("IsProcessInJob")
            return bool(result.value)
        finally:
            self.api.close(process)

    def bind_target(self, target: dict[str, Any]) -> None:
        pid = target.get("pid")
        if not isinstance(pid, int) or pid <= 0 or not self._contains_pid(pid):
            raise IdentityError("target 未继承 Windows Job Object ownership")

    def graceful_stop(self) -> bool:
        self.send_host_command("graceful_stop")
        return self.host.poll() is None

    def force_stop(self) -> bool:
        self.send_host_command("force_stop")
        if self.handle is None:
            return self.is_empty()
        return bool(self.api.kernel32.TerminateJobObject(self.handle, 1))

    def is_empty(self) -> bool:
        if self.handle is None:
            return self.host.poll() is not None
        accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        if not self.api.kernel32.QueryInformationJobObject(
            self.handle,
            JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            return False
        return accounting.ActiveProcesses == 0

    def _close_job(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, None
            self.api.close(handle)

    def close(self) -> None:
        if self.host.stdin is not None:
            try:
                self.host.stdin.close()
            except OSError:
                pass
        self._close_job()
        try:
            self.host.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if self.host.poll() is None:
                self.host.kill()
        for stream in (self.host.stdout, self.host.stderr):
            if stream is not None:
                stream.close()


class WindowsAdapter(PlatformAdapter):
    def __init__(self, selection: PlatformSelection, workspace_root: Path, state_root: Path) -> None:
        super().__init__(selection, workspace_root, state_root)
        self.api = WindowsApi()
        self.acl = WindowsAcl()

    def secure_directory(self, path: Path) -> None:
        self.validate_runtime_path(path)
        self.acl.secure_directory(path)

    def secure_file(self, path: Path) -> None:
        self.validate_runtime_path(path)
        self.acl.secure_file(path)

    def verify_directory(self, path: Path) -> None:
        self.validate_runtime_path(path)
        self.acl.verify_directory(path)

    def verify_file(self, path: Path) -> None:
        self.validate_runtime_path(path)
        self.acl.verify_file(path)

    def acquire_manager_lock(self) -> ManagerLock:
        digest = hashlib.sha256(str(self.workspace_root).lower().encode("utf-8")).hexdigest()[:24]
        return WindowsManagerLock(self.api, f"Local\\dev-skills-process-manager-{digest}")

    def spawn_manager(
        self,
        command: list[str],
        *,
        stdout: Any,
        stderr: Any,
    ) -> subprocess.Popen[Any]:
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=flags,
        )

    def spawn_service_host(
        self,
        command: list[str],
        *,
        cwd: Path,
        environment: dict[str, str],
    ) -> subprocess.Popen[str]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            close_fds=True,
            creationflags=flags,
        )

    def create_run_owner(
        self,
        run_id: str,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> RunOwner:
        if host.poll() is not None:
            raise SupervisorError("service-host 在 owner 建立前退出")
        return WindowsJobOwner(self.api, self.selection, host, capability_hash)

    def process_identity(self, pid: int) -> dict[str, Any]:
        handle = self.api.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            raise IdentityError("Windows 进程身份不可读取")
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not self.api.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                raise IdentityError("Windows 进程 creation time 不可读取")
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self.api.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                raise IdentityError("Windows 进程 image path 不可读取")
            creation_value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return {"pid": pid, "creationFileTime": str(creation_value), "executable": buffer.value}
        finally:
            self.api.close(handle)

    def identity_matches(self, expected: dict[str, Any]) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int):
            return False
        try:
            return self.process_identity(pid) == expected
        except (IdentityError, SupervisorError):
            return False

    @staticmethod
    def _identity_evidence_valid(expected: dict[str, Any]) -> bool:
        return (
            set(expected) == {"pid", "creationFileTime", "executable"}
            and isinstance(expected.get("pid"), int)
            and expected["pid"] > 0
            and isinstance(expected.get("creationFileTime"), str)
            and bool(expected["creationFileTime"])
            and isinstance(expected.get("executable"), str)
            and bool(expected["executable"])
        )

    def inspect_persisted_owner(self, evidence: PersistedOwnerEvidence) -> OwnerInspection:
        owner = evidence.owner
        host_pid = evidence.host_identity.get("pid")
        target_identity = evidence.target_identity
        target_pid = target_identity.get("pid") if isinstance(target_identity, dict) else None
        if (
            owner.get("platform") != self.selection.platform
            or owner.get("backend") != self.selection.backend
            or owner.get("capabilityHash") != evidence.capability_hash
            or owner.get("hostPid") != host_pid
            or not self._identity_evidence_valid(evidence.host_identity)
            or target_identity is not None
            and (
                not isinstance(target_identity, dict)
                or not self._identity_evidence_valid(target_identity)
                or not isinstance(target_pid, int)
            )
        ):
            return OwnerInspection("unverifiable", False, {}, "owner_identity_invalid")
        host_alive = self.identity_matches(evidence.host_identity)
        target_alive = self.identity_matches(target_identity) if isinstance(target_identity, dict) else None
        accounting = {
            "hostAlive": host_alive,
            "targetAlive": target_alive,
            "knownProcessesActive": int(host_alive) + int(target_alive is True),
        }
        if not host_alive and target_alive is not True:
            return OwnerInspection("empty", False, accounting)
        if target_alive is None:
            return OwnerInspection("unverifiable", False, accounting, "owner_target_identity_missing")
        return OwnerInspection("active", False, accounting, "owner_job_handle_unavailable")

    def signal_persisted_owner(self, evidence: PersistedOwnerEvidence, *, force: bool) -> bool:
        del force
        return self.inspect_persisted_owner(evidence).empty

    def terminate_manager(self, expected: dict[str, Any], *, timeout: float) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int) or not self.identity_matches(expected):
            return False
        handle = self.api.kernel32.OpenProcess(
            PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
            False,
            pid,
        )
        if not handle:
            return not self.identity_matches(expected)
        terminated = False
        try:
            if not self.identity_matches(expected):
                return True
            if not self.api.kernel32.TerminateProcess(handle, 1):
                return False
            wait_ms = max(0, min(int(timeout * 1000), 3_600_000))
            terminated = self.api.kernel32.WaitForSingleObject(handle, wait_ms) == WAIT_OBJECT_0
        finally:
            self.api.close(handle)
        return terminated and not self.identity_matches(expected)
