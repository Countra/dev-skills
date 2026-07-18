"""macOS process-group guardian 与 kqueue 补充监控。"""

from __future__ import annotations

import ctypes
import os
import select
import subprocess
from pathlib import Path
from typing import Any

from ..errors import IdentityError
from .base import PlatformSelection, RunOwner
from .posix import PosixAdapter, PosixRunOwner


# 字段布局来自 XNU proc_bsdinfo，微秒级启动时间用于阻断 PID 复用。
class _ProcBsdInfo(ctypes.Structure):
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


PROC_PIDTBSDINFO = 3
PROC_PIDPATHINFO_MAXSIZE = 4096


class MacRunOwner(PosixRunOwner):
    def __init__(self, selection: PlatformSelection, host: subprocess.Popen[str], capability_hash: str) -> None:
        super().__init__(selection, host, capability_hash)
        self._kqueue: Any | None = None
        self._target_exit_observed = False

    def bind_target(self, target: dict[str, Any]) -> None:
        super().bind_target(target)
        pid = target.get("pid")
        if hasattr(select, "kqueue") and isinstance(pid, int):
            queue = select.kqueue()
            event = select.kevent(
                pid,
                filter=select.KQ_FILTER_PROC,
                flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                fflags=select.KQ_NOTE_EXIT,
            )
            queue.control([event], 0, 0)
            self._kqueue = queue

    def _poll_target_exit(self) -> None:
        if self._kqueue is None or self._target_exit_observed:
            return
        try:
            self._target_exit_observed = bool(self._kqueue.control(None, 1, 0))
        except OSError:
            return

    def is_empty(self) -> bool:
        self._poll_target_exit()
        return super().is_empty()

    def internal_identity(self) -> dict[str, Any]:
        return {
            **super().internal_identity(),
            "targetExitMonitor": "kqueue" if self._kqueue is not None else "process-group",
        }

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._kqueue is not None:
                self._kqueue.close()
                self._kqueue = None


class MacOSAdapter(PosixAdapter):
    @staticmethod
    def _identity_evidence_valid(expected: dict[str, Any]) -> bool:
        return (
            set(expected) == {"pid", "startTimeMicros", "executable"}
            and isinstance(expected.get("pid"), int)
            and expected["pid"] > 0
            and isinstance(expected.get("startTimeMicros"), str)
            and expected["startTimeMicros"].isdigit()
            and isinstance(expected.get("executable"), str)
            and bool(expected["executable"])
        )

    def create_run_owner(
        self,
        run_id: str,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> RunOwner:
        if host.poll() is not None:
            from ..errors import SupervisorError

            raise SupervisorError("service-host 在 owner 建立前退出")
        return MacRunOwner(self.selection, host, capability_hash)

    def process_identity(self, pid: int) -> dict[str, Any]:
        if pid <= 0:
            raise IdentityError("macOS 进程身份不可读取")
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
            library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            library.proc_pidpath.restype = ctypes.c_int
            info = _ProcBsdInfo()
            read = library.proc_pidinfo(
                pid,
                PROC_PIDTBSDINFO,
                0,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            path_buffer = ctypes.create_string_buffer(PROC_PIDPATHINFO_MAXSIZE)
            path_length = library.proc_pidpath(pid, path_buffer, len(path_buffer))
        except (AttributeError, OSError) as exc:
            raise IdentityError("macOS 进程身份不可读取") from exc
        if (
            read != ctypes.sizeof(info)
            or info.pbi_pid != pid
            or info.pbi_start_tvsec <= 0
            or info.pbi_start_tvusec >= 1_000_000
            or path_length <= 0
            or not path_buffer.value
        ):
            raise IdentityError("macOS 进程身份不可读取")
        return {
            "pid": pid,
            "startTimeMicros": str(info.pbi_start_tvsec * 1_000_000 + info.pbi_start_tvusec),
            "executable": os.fsdecode(path_buffer.value),
        }

    def identity_matches(self, expected: dict[str, Any]) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int):
            return False
        try:
            return self.process_identity(pid) == expected
        except IdentityError:
            return False
