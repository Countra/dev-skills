"""Windows runtime 文件 ACL 的语义验证与受保护 DACL 修复。"""

from __future__ import annotations

import ctypes
import stat
from ctypes import wintypes
from pathlib import Path

from ..errors import (
    EnvironmentUnverifiableError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
)
from ..models import (
    WINDOWS_BROAD_RESTRICTED_SIDS as BROAD_RESTRICTED_SIDS,
    WINDOWS_DENY_ACCESS as DENY_ACCESS,
    WINDOWS_FILE_ALL_ACCESS as FILE_ALL_ACCESS,
    WINDOWS_GRANT_ACCESS as GRANT_ACCESS,
    WindowsAclEntry as AclEntry,
    WindowsAclSnapshot as AclSnapshot,
    validate_windows_acl_snapshot as validate_acl_snapshot,
)


OWNER_SECURITY_INFORMATION = 0x00000001
GROUP_SECURITY_INFORMATION = 0x00000002
DACL_SECURITY_INFORMATION = 0x00000004
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
SECURITY_DESCRIPTOR_REVISION = 1
SE_FILE_OBJECT = 1
ERROR_ACCESS_DENIED = 5
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_ALREADY_EXISTS = 183
TOKEN_QUERY = 0x0008
TOKEN_DUPLICATE = 0x0002
TOKEN_USER_CLASS = 1
TOKEN_RESTRICTED_SIDS_CLASS = 11
SECURITY_IMPERSONATION = 2
MAX_TOKEN_INFORMATION_BYTES = 64 * 1024
MAX_RESTRICTED_SIDS = 64
FILE_GENERIC_READ = 0x00120089
FILE_GENERIC_WRITE = 0x00120116
FILE_GENERIC_EXECUTE = 0x001200A0
ACCESS_ALLOWED_ACE_TYPE = 0
ACCESS_DENIED_ACE_TYPE = 1
ACL_SIZE_INFORMATION_CLASS = 2


class ACL_SIZE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]


class ACE_HEADER(ctypes.Structure):
    _fields_ = [
        ("AceType", wintypes.BYTE),
        ("AceFlags", wintypes.BYTE),
        ("AceSize", wintypes.WORD),
    ]


class ACCESS_ALLOWED_ACE(ctypes.Structure):
    _fields_ = [
        ("Header", ACE_HEADER),
        ("Mask", wintypes.DWORD),
        ("SidStart", wintypes.DWORD),
    ]


class GENERIC_MAPPING(ctypes.Structure):
    _fields_ = [
        ("GenericRead", wintypes.DWORD),
        ("GenericWrite", wintypes.DWORD),
        ("GenericExecute", wintypes.DWORD),
        ("GenericAll", wintypes.DWORD),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", SID_AND_ATTRIBUTES)]


class TOKEN_GROUPS(ctypes.Structure):
    _fields_ = [
        ("GroupCount", wintypes.DWORD),
        ("Groups", SID_AND_ATTRIBUTES * 1),
    ]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class WindowsAcl:
    """只信任当前用户、SYSTEM、Administrators 与 owner 语义 SID。"""

    def __init__(self) -> None:
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._sid: str | None = None
        self._restricted: tuple[str, ...] | None = None
        self._configure_api()

    @staticmethod
    def _api(library: object, name: str, argtypes: list[object], restype: object) -> None:
        function = getattr(library, name)
        function.argtypes = argtypes
        function.restype = restype

    def _configure_api(self) -> None:
        pointer, void_pointer = ctypes.POINTER, ctypes.c_void_p
        handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
        kernel32, advapi32 = self.kernel32, self.advapi32
        definitions = (
            (kernel32, "GetCurrentProcess", [], handle),
            (kernel32, "LocalFree", [void_pointer], void_pointer),
            (kernel32, "CloseHandle", [handle], boolean),
            (kernel32, "CreateDirectoryW", [wintypes.LPCWSTR, pointer(SECURITY_ATTRIBUTES)], boolean),
            (advapi32, "OpenProcessToken", [handle, dword, pointer(handle)], boolean),
            (advapi32, "GetTokenInformation", [handle, ctypes.c_int, void_pointer, dword, pointer(dword)], boolean),
            (advapi32, "ConvertSidToStringSidW", [void_pointer, pointer(wintypes.LPWSTR)], boolean),
            (
                advapi32,
                "ConvertStringSecurityDescriptorToSecurityDescriptorW",
                [wintypes.LPCWSTR, dword, pointer(void_pointer), pointer(dword)],
                boolean,
            ),
            (advapi32, "GetSecurityDescriptorDacl", [void_pointer, pointer(boolean), pointer(void_pointer), pointer(boolean)], boolean),
            (advapi32, "SetNamedSecurityInfoW", [wintypes.LPWSTR, dword, dword] + [void_pointer] * 4, dword),
            (advapi32, "GetNamedSecurityInfoW", [wintypes.LPWSTR, dword, dword] + [pointer(void_pointer)] * 5, dword),
            (advapi32, "GetAclInformation", [void_pointer, void_pointer, dword, ctypes.c_int], boolean),
            (advapi32, "GetAce", [void_pointer, dword, pointer(void_pointer)], boolean),
            (advapi32, "DuplicateToken", [handle, ctypes.c_int, pointer(handle)], boolean),
            (advapi32, "AccessCheck", [void_pointer, handle, dword, pointer(GENERIC_MAPPING), void_pointer, pointer(dword), pointer(dword), pointer(boolean)], boolean),
        )
        for library, name, argtypes, restype in definitions:
            self._api(library, name, argtypes, restype)

    @staticmethod
    def _raise_win_error(label: str, error: int) -> None:
        if error == ERROR_ACCESS_DENIED:
            raise RuntimePermissionDeniedError(
                f"{label} 被 Windows 拒绝",
                diagnostics={"win32Error": error},
            )
        raise EnvironmentUnverifiableError(
            f"{label} 无法验证",
            diagnostics={"win32Error": error},
        )

    @staticmethod
    def _raise_filesystem_error(label: str, exc: OSError) -> None:
        if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) == ERROR_ACCESS_DENIED:
            raise RuntimePermissionDeniedError(f"{label} 被 Windows 拒绝") from exc
        raise EnvironmentUnverifiableError(f"{label} 无法验证") from exc

    def _sid_to_string(self, sid: ctypes.c_void_p) -> str:
        text = wintypes.LPWSTR()
        if not self.advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            self._raise_win_error("Windows SID 转换", ctypes.get_last_error())
        try:
            return ctypes.wstring_at(text)
        finally:
            self.kernel32.LocalFree(text)

    def _open_process_token(self, access: int) -> wintypes.HANDLE:
        token = wintypes.HANDLE()
        if not self.advapi32.OpenProcessToken(
            self.kernel32.GetCurrentProcess(),
            access,
            ctypes.byref(token),
        ):
            self._raise_win_error("当前 Windows token 读取", ctypes.get_last_error())
        return token

    def _token_information(self, information_class: int, label: str) -> ctypes.Array:
        token = self._open_process_token(TOKEN_QUERY)
        try:
            needed = wintypes.DWORD()
            ctypes.set_last_error(0)
            self.advapi32.GetTokenInformation(
                token,
                information_class,
                None,
                0,
                ctypes.byref(needed),
            )
            error = ctypes.get_last_error()
            if (
                error != ERROR_INSUFFICIENT_BUFFER
                or needed.value == 0
                or needed.value > MAX_TOKEN_INFORMATION_BYTES
            ):
                self._raise_win_error(f"{label}大小读取", error)
            buffer = ctypes.create_string_buffer(needed.value)
            if not self.advapi32.GetTokenInformation(
                token,
                information_class,
                buffer,
                needed.value,
                ctypes.byref(needed),
            ):
                self._raise_win_error(label, ctypes.get_last_error())
            return buffer
        finally:
            self.kernel32.CloseHandle(token)

    def _current_sid(self) -> str:
        if self._sid is not None:
            return self._sid
        buffer = self._token_information(TOKEN_USER_CLASS, "当前 Windows SID 读取")
        token_user = ctypes.cast(buffer, ctypes.POINTER(TOKEN_USER)).contents
        self._sid = self._sid_to_string(token_user.User.Sid)
        return self._sid

    def _restricted_sids(self) -> tuple[str, ...]:
        if self._restricted is not None:
            return self._restricted
        buffer = self._token_information(
            TOKEN_RESTRICTED_SIDS_CLASS,
            "当前 Windows restricting SID 读取",
        )
        token_groups = ctypes.cast(buffer, ctypes.POINTER(TOKEN_GROUPS)).contents
        count = int(token_groups.GroupCount)
        if count > MAX_RESTRICTED_SIDS:
            raise EnvironmentUnverifiableError(
                "当前 Windows restricting SID 数量超过上限",
                diagnostics={"count": count, "limit": MAX_RESTRICTED_SIDS},
            )
        group_type = SID_AND_ATTRIBUTES * count
        group_pointer = ctypes.addressof(buffer) + TOKEN_GROUPS.Groups.offset
        groups = ctypes.cast(group_pointer, ctypes.POINTER(group_type)).contents
        observed = {self._sid_to_string(item.Sid) for item in groups}
        values = tuple(sorted(observed - BROAD_RESTRICTED_SIDS))
        if observed and not values:
            raise EnvironmentUnverifiableError(
                "当前 Windows token 只有宽泛 restricting SID，无法构造私有 runtime",
                diagnostics={"restrictingSids": sorted(observed)},
            )
        self._restricted = values
        return values

    def _acl_sddl(self, *, directory: bool) -> str:
        flags = "OICI" if directory else ""
        fixed = (
            f"D:P(A;{flags};FA;;;{self._current_sid()})"
            f"(A;{flags};FA;;;SY)"
            f"(A;{flags};FA;;;BA)"
        )
        restricted = "".join(
            f"(A;{flags};FA;;;{sid})"
            for sid in self._restricted_sids()
        )
        return fixed + restricted

    def _build_descriptor(self, *, directory: bool) -> ctypes.c_void_p:
        descriptor = ctypes.c_void_p()
        descriptor_size = wintypes.DWORD()
        if not self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            self._acl_sddl(directory=directory),
            SECURITY_DESCRIPTOR_REVISION,
            ctypes.byref(descriptor),
            ctypes.byref(descriptor_size),
        ):
            self._raise_win_error("Windows runtime ACL 构造", ctypes.get_last_error())
        return descriptor

    def _create_directory(self, path: Path) -> None:
        descriptor = self._build_descriptor(directory=True)
        attributes = SECURITY_ATTRIBUTES(
            ctypes.sizeof(SECURITY_ATTRIBUTES),
            descriptor,
            False,
        )
        try:
            ctypes.set_last_error(0)
            if not self.kernel32.CreateDirectoryW(str(path), ctypes.byref(attributes)):
                error = ctypes.get_last_error()
                if error != ERROR_ALREADY_EXISTS:
                    self._raise_win_error("Windows runtime 目录创建", error)
        finally:
            self.kernel32.LocalFree(descriptor)

    def _apply_acl(self, path: Path, *, directory: bool) -> None:
        descriptor = self._build_descriptor(directory=directory)
        try:
            present = wintypes.BOOL()
            dacl = ctypes.c_void_p()
            defaulted = wintypes.BOOL()
            if not self.advapi32.GetSecurityDescriptorDacl(
                descriptor,
                ctypes.byref(present),
                ctypes.byref(dacl),
                ctypes.byref(defaulted),
            ):
                self._raise_win_error("Windows runtime DACL 提取", ctypes.get_last_error())
            if not present.value or not dacl.value:
                raise EnvironmentUnverifiableError("构造的 Windows runtime DACL 无效")
            error = self.advapi32.SetNamedSecurityInfoW(
                str(path),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                dacl,
                None,
            )
            if error:
                self._raise_win_error("Windows runtime ACL 设置", error)
        finally:
            self.kernel32.LocalFree(descriptor)
        self._verify_acl(path)

    def _entries(self, dacl: ctypes.c_void_p) -> tuple[AclEntry, ...]:
        information = ACL_SIZE_INFORMATION()
        if not self.advapi32.GetAclInformation(
            dacl,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ACL_SIZE_INFORMATION_CLASS,
        ):
            self._raise_win_error("Windows runtime ACL 大小读取", ctypes.get_last_error())
        values: list[AclEntry] = []
        for index in range(information.AceCount):
            raw_ace = ctypes.c_void_p()
            if not self.advapi32.GetAce(dacl, index, ctypes.byref(raw_ace)):
                self._raise_win_error("Windows runtime ACE 读取", ctypes.get_last_error())
            header = ctypes.cast(raw_ace, ctypes.POINTER(ACE_HEADER)).contents
            if header.AceType not in {ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE}:
                raise EnvironmentUnverifiableError(
                    "Windows runtime ACL 包含无法验证的 ACE 类型",
                    diagnostics={"aceType": int(header.AceType)},
                )
            sid_offset = ACCESS_ALLOWED_ACE.SidStart.offset
            if header.AceSize < sid_offset + 8 or raw_ace.value is None:
                raise EnvironmentUnverifiableError("Windows runtime ACE 长度无效")
            entry = ctypes.cast(raw_ace, ctypes.POINTER(ACCESS_ALLOWED_ACE)).contents
            sid = ctypes.c_void_p(raw_ace.value + sid_offset)
            values.append(
                AclEntry(
                    self._sid_to_string(sid),
                    int(entry.Mask),
                    GRANT_ACCESS if header.AceType == ACCESS_ALLOWED_ACE_TYPE else DENY_ACCESS,
                    int(header.AceFlags),
                )
            )
        return tuple(values)

    def _access_mask(self, descriptor: ctypes.c_void_p) -> int:
        primary = self._open_process_token(TOKEN_QUERY | TOKEN_DUPLICATE)
        impersonation = wintypes.HANDLE()
        try:
            if not self.advapi32.DuplicateToken(
                primary,
                SECURITY_IMPERSONATION,
                ctypes.byref(impersonation),
            ):
                self._raise_win_error("Windows impersonation token 构造", ctypes.get_last_error())
            mapping = GENERIC_MAPPING(
                FILE_GENERIC_READ,
                FILE_GENERIC_WRITE,
                FILE_GENERIC_EXECUTE,
                FILE_ALL_ACCESS,
            )
            privilege_size = wintypes.DWORD(1024)
            privileges = ctypes.create_string_buffer(privilege_size.value)
            granted = wintypes.DWORD()
            access_status = wintypes.BOOL()
            if not self.advapi32.AccessCheck(
                descriptor,
                impersonation,
                FILE_ALL_ACCESS,
                ctypes.byref(mapping),
                privileges,
                ctypes.byref(privilege_size),
                ctypes.byref(granted),
                ctypes.byref(access_status),
            ):
                self._raise_win_error("Windows runtime AccessCheck", ctypes.get_last_error())
            return int(granted.value) if access_status.value else 0
        finally:
            if impersonation:
                self.kernel32.CloseHandle(impersonation)
            self.kernel32.CloseHandle(primary)

    def _read_snapshot(self, path: Path) -> AclSnapshot:
        owner = ctypes.c_void_p()
        group = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        error = self.advapi32.GetNamedSecurityInfoW(
            str(path),
            SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
            ctypes.byref(owner),
            ctypes.byref(group),
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if error:
            self._raise_win_error("Windows runtime security descriptor 读取", error)
        try:
            if not owner.value or not group.value or not dacl.value:
                raise RuntimeInsecureError("Windows runtime 缺少 owner、group 或受限 DACL")
            return AclSnapshot(
                self._sid_to_string(owner),
                self._entries(dacl),
                self._access_mask(descriptor),
            )
        finally:
            self.kernel32.LocalFree(descriptor)

    @staticmethod
    def _validate_path(path: Path, *, directory: bool) -> None:
        try:
            value = path.lstat()
        except OSError as exc:
            WindowsAcl._raise_filesystem_error("Windows runtime 路径读取", exc)
        expected = stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)
        attributes = getattr(value, "st_file_attributes", 0)
        if not expected or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeInsecureError(f"Windows runtime 路径类型不安全: {path}")

    def _verify_acl(self, path: Path) -> None:
        validate_acl_snapshot(
            self._read_snapshot(path),
            self._current_sid(),
            self._restricted_sids(),
        )

    def _ensure_acl(self, path: Path, *, directory: bool) -> None:
        self._validate_path(path, directory=directory)
        try:
            self._verify_acl(path)
        except RuntimeInsecureError:
            self._apply_acl(path, directory=directory)

    def secure_directory(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._raise_filesystem_error("Windows runtime 父目录创建", exc)
        if not path.exists():
            self._create_directory(path)
        self._ensure_acl(path, directory=True)

    def secure_file(self, path: Path) -> None:
        self._ensure_acl(path, directory=False)

    def verify_directory(self, path: Path) -> None:
        self._validate_path(path, directory=True)
        self._verify_acl(path)

    def verify_file(self, path: Path) -> None:
        self._validate_path(path, directory=False)
        self._verify_acl(path)
