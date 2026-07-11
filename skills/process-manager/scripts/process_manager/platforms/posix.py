"""Linux/macOS 共用的 process-group guardian 实现。"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from ..errors import ConflictError, IdentityError, SupervisorError
from .base import ManagerLock, PlatformAdapter, PlatformSelection, RunOwner


class PosixManagerLock(ManagerLock):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a+", encoding="utf-8")
        os.chmod(path, 0o600)
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
    def secure_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
        stat = path.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise SupervisorError(f"runtime 目录权限不安全: {path}")

    def secure_file(self, path: Path) -> None:
        if not path.is_file():
            raise SupervisorError(f"runtime 文件不存在: {path}")
        os.chmod(path, 0o600)
        stat = path.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise SupervisorError(f"runtime 文件权限不安全: {path}")

    def verify_file(self, path: Path) -> None:
        if not path.is_file():
            raise SupervisorError(f"runtime 文件不存在: {path}")
        stat = path.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise SupervisorError(f"runtime 文件权限不安全: {path}")

    def acquire_manager_lock(self) -> ManagerLock:
        lock = PosixManagerLock(self.state_root / "manager.lock")
        self.secure_file(self.state_root / "manager.lock")
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
