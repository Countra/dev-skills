"""Linux/macOS 共用的 process-group guardian 实现。"""

from __future__ import annotations

import fcntl
import os
import signal
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

from ..errors import (
    ConflictError,
    EnvironmentUnverifiableError,
    IdentityError,
    RuntimeInsecureError,
    RuntimePermissionDeniedError,
    SupervisorError,
)
from .base import (
    ManagerLock,
    OwnerInspection,
    PersistedOwnerEvidence,
    PlatformAdapter,
    PlatformSelection,
    RunOwner,
)


class PosixManagerLock(ManagerLock):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            self._handle = os.fdopen(descriptor, "a+", encoding="utf-8")
            descriptor = -1
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            raise ConflictError("当前 workspace 已有 process-manager 实例") from exc

    def close(self) -> None:
        if self._handle.closed:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()


class PosixRunOwner(RunOwner):
    def __init__(self, selection: PlatformSelection, host: subprocess.Popen[str], capability_hash: str) -> None:
        super().__init__(selection, host, capability_hash)
        self._pgid: int | None = None

    @property
    def control_data(self) -> dict[str, Any]:
        return {"mode": "process-group"}

    def bind_target(self, target: dict[str, Any]) -> None:
        pid = target.get("pid")
        pgid = target.get("pgid")
        if not isinstance(pid, int) or not isinstance(pgid, int) or pid <= 0 or pgid != pid:
            raise IdentityError("service-host 未建立独立 target process group")
        try:
            actual = os.getpgid(pid)
        except OSError as exc:
            raise IdentityError("target 在 owner 验证前已退出") from exc
        if actual != pgid:
            raise IdentityError("target process group 身份不匹配")
        self._pgid = pgid

    def graceful_stop(self) -> bool:
        self.send_host_command("graceful_stop")
        if self._pgid is None:
            return False
        try:
            os.killpg(self._pgid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return True
        except OSError:
            return False

    def force_stop(self) -> bool:
        self.send_host_command("force_stop")
        if self._pgid is None:
            return False
        try:
            os.killpg(self._pgid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return True
        except OSError:
            return False

    def _group_alive(self) -> bool:
        if self._pgid is None:
            return False
        try:
            os.killpg(self._pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def is_empty(self) -> bool:
        return not self._group_alive() and self.host.poll() is not None

    def close(self) -> None:
        if self.host.stdin is not None:
            try:
                self.host.stdin.close()
            except OSError:
                pass
        if self.host.poll() is None and not self._group_alive():
            try:
                self.host.terminate()
                self.host.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                if self.host.poll() is None:
                    self.host.kill()
        for handle in (self.host.stdout, self.host.stderr):
            if handle is not None:
                handle.close()

    def internal_identity(self) -> dict[str, Any]:
        return {**super().internal_identity(), "targetProcessGroup": self._pgid}


class PosixAdapter(PlatformAdapter):
    @staticmethod
    def _runtime_error(label: str, exc: OSError) -> None:
        if isinstance(exc, PermissionError):
            raise RuntimePermissionDeniedError(f"{label}访问被拒绝") from exc
        raise EnvironmentUnverifiableError(
            f"{label}无法验证",
            diagnostics={"errno": exc.errno},
        ) from exc

    def _runtime_stat(self, path: Path, *, directory: bool) -> os.stat_result:
        path = self.validate_runtime_path(path)
        try:
            value = path.lstat()
        except OSError as exc:
            self._runtime_error("runtime 路径", exc)
        expected = stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)
        if not expected or stat.S_ISLNK(value.st_mode):
            raise RuntimeInsecureError(f"runtime 路径类型不安全: {path}")
        return value

    @staticmethod
    def _validate_owner_mode(path: Path, value: os.stat_result) -> None:
        if value.st_uid != os.getuid() or value.st_mode & 0o077:
            raise RuntimeInsecureError(f"runtime owner 或 mode 不安全: {path}")

    def _chmod_runtime(self, path: Path, mode: int, *, directory: bool) -> None:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        if directory:
            flags |= getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            self._runtime_error("runtime 路径打开", exc)
        try:
            os.fchmod(descriptor, mode)
        except OSError as exc:
            self._runtime_error("runtime 权限修复", exc)
        finally:
            os.close(descriptor)

    def secure_directory(self, path: Path) -> None:
        path = self.validate_runtime_path(path)
        try:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            value = self._runtime_stat(path, directory=True)
            if value.st_uid != os.getuid():
                raise RuntimeInsecureError(f"runtime 目录 owner 不安全: {path}")
            self._chmod_runtime(path, 0o700, directory=True)
        except OSError as exc:
            self._runtime_error("runtime 目录修复", exc)
        self.verify_directory(path)

    def secure_file(self, path: Path) -> None:
        path = self.validate_runtime_path(path)
        value = self._runtime_stat(path, directory=False)
        if value.st_uid != os.getuid():
            raise RuntimeInsecureError(f"runtime 文件 owner 不安全: {path}")
        self._chmod_runtime(path, 0o600, directory=False)
        self.verify_file(path)

    def verify_directory(self, path: Path) -> None:
        path = self.validate_runtime_path(path)
        self._validate_owner_mode(path, self._runtime_stat(path, directory=True))

    def verify_file(self, path: Path) -> None:
        path = self.validate_runtime_path(path)
        self._validate_owner_mode(path, self._runtime_stat(path, directory=False))

    def acquire_manager_lock(self) -> ManagerLock:
        path = self.state_root / "control" / "manager.lock"
        self.validate_runtime_path(path)
        lock = PosixManagerLock(path)
        self.secure_file(path)
        return lock

    def spawn_manager(
        self,
        command: list[str],
        *,
        stdout: Any,
        stderr: Any,
    ) -> subprocess.Popen[Any]:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            start_new_session=True,
        )

    def spawn_service_host(
        self,
        command: list[str],
        *,
        cwd: Path,
        environment: dict[str, str],
    ) -> subprocess.Popen[str]:
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
        )

    def create_run_owner(
        self,
        run_id: str,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> RunOwner:
        if host.poll() is not None:
            raise SupervisorError("service-host 在 owner 建立前退出")
        return PosixRunOwner(self.selection, host, capability_hash)

    def process_identity(self, pid: int) -> dict[str, Any]:
        try:
            os.kill(pid, 0)
        except OSError as exc:
            raise IdentityError("进程身份不可读取") from exc
        return {"pid": pid}

    def identity_matches(self, expected: dict[str, Any]) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int):
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _identity_evidence_valid(expected: dict[str, Any]) -> bool:
        return set(expected) == {"pid"} and isinstance(expected.get("pid"), int) and expected["pid"] > 0

    def _persisted_group(self, evidence: PersistedOwnerEvidence) -> tuple[int, bool, bool | None] | None:
        owner = evidence.owner
        pgid = owner.get("targetProcessGroup")
        host_pid = evidence.host_identity.get("pid")
        target_identity = evidence.target_identity
        target_pid = target_identity.get("pid") if isinstance(target_identity, dict) else None
        if (
            owner.get("platform") != self.selection.platform
            or owner.get("backend") != self.selection.backend
            or owner.get("capabilityHash") != evidence.capability_hash
            or owner.get("hostPid") != host_pid
            or not self._identity_evidence_valid(evidence.host_identity)
            or not isinstance(pgid, int)
            or pgid <= 0
        ):
            return None
        if target_identity is None:
            target_alive = None
        elif not self._identity_evidence_valid(target_identity) or target_pid != pgid:
            return None
        else:
            target_alive = self.identity_matches(target_identity)
        return pgid, self.identity_matches(evidence.host_identity), target_alive

    @staticmethod
    def _persisted_group_alive(pgid: int) -> bool | None:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return None
        except OSError:
            return None

    def inspect_persisted_owner(self, evidence: PersistedOwnerEvidence) -> OwnerInspection:
        values = self._persisted_group(evidence)
        if values is None:
            return OwnerInspection("unverifiable", False, {}, "owner_identity_invalid")
        pgid, host_alive, target_alive = values
        group_alive = self._persisted_group_alive(pgid)
        accounting = {
            "hostAlive": host_alive,
            "targetAlive": target_alive,
            "groupAlive": group_alive,
        }
        if group_alive is False and not host_alive and target_alive is not True:
            return OwnerInspection("empty", False, accounting)
        if group_alive is None:
            return OwnerInspection("unverifiable", False, accounting, "owner_membership_unverifiable")
        if target_alive is None:
            return OwnerInspection("unverifiable", False, accounting, "owner_target_identity_missing")
        if target_alive:
            try:
                if os.getpgid(pgid) != pgid:
                    return OwnerInspection("unverifiable", False, accounting, "owner_group_identity_mismatch")
            except OSError:
                return OwnerInspection("unverifiable", False, accounting, "owner_group_identity_unverifiable")
        if group_alive and not target_alive:
            return OwnerInspection("unverifiable", False, accounting, "owner_group_leader_missing")
        return OwnerInspection("active", True, accounting)

    def signal_persisted_owner(self, evidence: PersistedOwnerEvidence, *, force: bool) -> bool:
        inspection = self.inspect_persisted_owner(evidence)
        if inspection.empty:
            return True
        if not inspection.cleanup_supported:
            return False
        values = self._persisted_group(evidence)
        if values is None:
            return False
        pgid, host_alive, target_alive = values
        selected_signal = signal.SIGKILL if force else signal.SIGTERM
        signaled = False
        if target_alive is True and isinstance(evidence.target_identity, dict) and self.identity_matches(evidence.target_identity):
            try:
                os.killpg(pgid, selected_signal)
                signaled = True
            except ProcessLookupError:
                signaled = True
            except OSError:
                return False
        host_pid = evidence.host_identity.get("pid")
        if host_alive and isinstance(host_pid, int) and self.identity_matches(evidence.host_identity):
            try:
                os.kill(host_pid, selected_signal)
                signaled = True
            except ProcessLookupError:
                signaled = True
            except OSError:
                return False
        return signaled

    def terminate_manager(self, expected: dict[str, Any], *, timeout: float) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int) or not self.identity_matches(expected):
            return False
        deadline = time.monotonic() + max(0.0, timeout)
        for selected_signal in (signal.SIGTERM, signal.SIGKILL):
            if not self.identity_matches(expected):
                return True
            try:
                os.kill(pid, selected_signal)
            except ProcessLookupError:
                return True
            except OSError:
                return False
            phase_deadline = deadline if selected_signal == signal.SIGKILL else min(deadline, time.monotonic() + 2)
            while time.monotonic() < phase_deadline:
                if not self.identity_matches(expected):
                    return True
                time.sleep(0.05)
        return not self.identity_matches(expected)
