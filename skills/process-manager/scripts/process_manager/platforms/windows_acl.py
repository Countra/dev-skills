"""Windows runtime 文件 ACL 的受保护 DACL 实现。"""

from __future__ import annotations

import csv
import ctypes
import io
import os
import re
import subprocess
from ctypes import wintypes
from pathlib import Path

from ..errors import SupervisorError


DACL_SECURITY_INFORMATION = 0x00000004
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
SECURITY_DESCRIPTOR_REVISION = 1


class WindowsAcl:
    """仅允许当前用户、SYSTEM 和 Administrators 访问 runtime 文件。"""

    def __init__(self) -> None:
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._sid: str | None = None
        self._configure_api()

    def _configure_api(self) -> None:
        self.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel32.LocalFree.restype = ctypes.c_void_p
        self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
        self.advapi32.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        self.advapi32.SetFileSecurityW.restype = wintypes.BOOL
        self.advapi32.GetFileSecurityW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.advapi32.GetFileSecurityW.restype = wintypes.BOOL
        self.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL

    @staticmethod
    def _last_error(label: str) -> SupervisorError:
        return SupervisorError(f"{label} 失败，Win32 error={ctypes.get_last_error()}")

    @staticmethod
    def _system_tool(name: str) -> str:
        root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        return str(root / "System32" / name)

    def _current_sid(self) -> str:
        if self._sid:
            return self._sid
        try:
            result = subprocess.run(
                [self._system_tool("whoami.exe"), "/user", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            row = next(csv.reader(io.StringIO(result.stdout)), [])
        except (OSError, subprocess.SubprocessError, csv.Error) as exc:
            raise SupervisorError("无法读取当前 Windows 用户 SID") from exc
        if result.returncode != 0 or len(row) < 2 or not row[1].startswith("S-"):
            raise SupervisorError("无法读取当前 Windows 用户 SID")
        self._sid = row[1]
        return self._sid

    def _acl_sddl(self, *, directory: bool) -> str:
        flags = "OICI" if directory else ""
        return (
            f"D:P(A;{flags};FA;;;{self._current_sid()})"
            f"(A;{flags};FA;;;SY)"
            f"(A;{flags};FA;;;BA)"
        )

    def _apply_acl(self, path: Path, *, directory: bool) -> None:
        descriptor = ctypes.c_void_p()
        descriptor_size = wintypes.DWORD()
        if not self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            self._acl_sddl(directory=directory),
            SECURITY_DESCRIPTOR_REVISION,
            ctypes.byref(descriptor),
            ctypes.byref(descriptor_size),
        ):
            raise self._last_error("Windows runtime ACL 解析")
        try:
            information = DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
            if not self.advapi32.SetFileSecurityW(str(path), information, descriptor):
                raise self._last_error(f"Windows runtime ACL 设置: {path}")
        finally:
            self.kernel32.LocalFree(descriptor)
        self._verify_acl(path)

    def _read_acl_sddl(self, path: Path) -> str:
        needed = wintypes.DWORD()
        self.advapi32.GetFileSecurityW(str(path), DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(needed))
        if needed.value == 0:
            raise self._last_error(f"Windows runtime ACL 大小读取: {path}")
        descriptor = ctypes.create_string_buffer(needed.value)
        if not self.advapi32.GetFileSecurityW(
            str(path),
            DACL_SECURITY_INFORMATION,
            descriptor,
            needed.value,
            ctypes.byref(needed),
        ):
            raise self._last_error(f"Windows runtime ACL 读取: {path}")
        text_pointer = wintypes.LPWSTR()
        text_length = wintypes.DWORD()
        if not self.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor,
            SECURITY_DESCRIPTOR_REVISION,
            DACL_SECURITY_INFORMATION,
            ctypes.byref(text_pointer),
            ctypes.byref(text_length),
        ):
            raise self._last_error(f"Windows runtime ACL 序列化: {path}")
        try:
            return ctypes.wstring_at(text_pointer, text_length.value)
        finally:
            self.kernel32.LocalFree(text_pointer)

    def _verify_acl(self, path: Path) -> None:
        sddl = self._read_acl_sddl(path)
        allowed_sids = {self._current_sid(), "SY", "BA", "S-1-5-18", "S-1-5-32-544"}
        aces = [item.split(";") for item in re.findall(r"\(([^)]+)\)", sddl)]
        observed_sids = {item[-1] for item in aces if len(item) == 6}
        valid_aces = bool(aces) and all(
            len(item) == 6
            and item[0] == "A"
            and item[2].lower() in {"fa", "0x1f01ff"}
            and item[-1] in allowed_sids
            for item in aces
        )
        if "D:P" not in sddl or not valid_aces or self._current_sid() not in observed_sids:
            raise SupervisorError(f"Windows runtime ACL 不是受保护的当前用户 DACL: {path}")

    def secure_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._apply_acl(path, directory=True)

    def secure_file(self, path: Path) -> None:
        if not path.is_file():
            raise SupervisorError(f"runtime 文件不存在: {path}")
        self._apply_acl(path, directory=False)

    def verify_file(self, path: Path) -> None:
        if not path.is_file():
            raise SupervisorError(f"runtime 文件不存在: {path}")
        self._verify_acl(path)
