"""manager 的平台透明 bootstrap 策略。"""

from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .atomic import atomic_write_bytes
from .models import ManagerConfig
from .platforms.base import PlatformAdapter


CommandFactory = Callable[[str, str], list[str]]


@dataclass(frozen=True)
class BootstrapResult:
    backend: str
    selection_reason: str
    process: subprocess.Popen[Any] | None


class ManagerBootstrap:
    def __init__(
        self,
        config: ManagerConfig,
        adapter: PlatformAdapter,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.runner = runner
        self.which = which
        digest = hashlib.sha256(str(config.workspace_root).encode("utf-8")).hexdigest()[:16]
        self.unit_name = f"dev-skills-pm-{digest}"
        self.launchd_label = f"dev.skills.process-manager.{digest}"
        self.launchd_plist = config.state_root / "manager-launchd.plist"

    def _run(self, command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return self.runner(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )

    def _detached(
        self,
        factory: CommandFactory,
        stdout: Any,
        stderr: Any,
        *,
        backend: str,
        reason: str,
    ) -> BootstrapResult:
        process = self.adapter.spawn_manager(factory(backend, reason), stdout=stdout, stderr=stderr)
        return BootstrapResult(backend, reason, process)

    def _systemd_available(self) -> bool:
        if not self.which("systemd-run") or not self.which("systemctl") or not os.environ.get("XDG_RUNTIME_DIR"):
            return False
        try:
            result = self._run(["systemctl", "--user", "show-environment"], 3)
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def _start_systemd(
        self,
        factory: CommandFactory,
        stdout_path: Path,
        stderr_path: Path,
    ) -> BootstrapResult | None:
        if not self._systemd_available():
            return None
        reason = "systemd user manager 可用，使用 workspace-scoped transient service"
        command = [
            "systemd-run",
            "--user",
            "--quiet",
            "--collect",
            "--service-type=exec",
            f"--unit={self.unit_name}",
            f"--working-directory={self.config.workspace_root}",
            f"--property=StandardOutput=append:{stdout_path}",
            f"--property=StandardError=append:{stderr_path}",
            "--",
            *factory("systemd-user", reason),
        ]
        try:
            result = self._run(command, 10)
        except (OSError, subprocess.SubprocessError):
            return None
        return BootstrapResult("systemd-user", reason, None) if result.returncode == 0 else None

    def _launchd_domain(self) -> str | None:
        if not hasattr(os, "getuid") or not Path("/bin/launchctl").is_file():
            return None
        domain = f"gui/{os.getuid()}"
        try:
            result = self._run(["/bin/launchctl", "print", domain], 3)
        except (OSError, subprocess.SubprocessError):
            return None
        return domain if result.returncode == 0 else None

    def _start_launchd(
        self,
        factory: CommandFactory,
        stdout_path: Path,
        stderr_path: Path,
    ) -> BootstrapResult | None:
        domain = self._launchd_domain()
        if domain is None:
            return None
        reason = "launchd GUI user domain 可用，使用 workspace-scoped transient job"
        command = factory("launchd-user", reason)
        plist = {
            "Label": self.launchd_label,
            "ProgramArguments": command,
            "WorkingDirectory": str(self.config.workspace_root),
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Background",
            "StandardOutPath": str(stdout_path),
            "StandardErrorPath": str(stderr_path),
        }
        try:
            if not self.config.paths.manager.exists() and self.launchd_plist.exists():
                self._run(["/bin/launchctl", "bootout", f"{domain}/{self.launchd_label}"], 5)
            atomic_write_bytes(self.launchd_plist, plistlib.dumps(plist, fmt=plistlib.FMT_XML))
            self.adapter.secure_file(self.launchd_plist)
            result = self._run(["/bin/launchctl", "bootstrap", domain, str(self.launchd_plist)], 10)
        except (OSError, subprocess.SubprocessError):
            return None
        return BootstrapResult("launchd-user", reason, None) if result.returncode == 0 else None

    def start(
        self,
        factory: CommandFactory,
        *,
        stdout_path: Path,
        stderr_path: Path,
        stdout: Any,
        stderr: Any,
    ) -> BootstrapResult:
        platform = self.adapter.selection.platform
        if platform == "windows":
            return self._detached(
                factory,
                stdout,
                stderr,
                backend="windows-detached",
                reason="Windows detached process 与 workspace named mutex",
            )
        if platform == "linux":
            systemd = self._start_systemd(factory, stdout_path, stderr_path)
            if systemd is not None:
                return systemd
            return self._detached(
                factory,
                stdout,
                stderr,
                backend="posix-session",
                reason="systemd user manager 不可用，自动使用独立 POSIX session",
            )
        if platform == "macos":
            launchd = self._start_launchd(factory, stdout_path, stderr_path)
            if launchd is not None:
                return launchd
            return self._detached(
                factory,
                stdout,
                stderr,
                backend="posix-session",
                reason="launchd user domain 不可用，自动使用独立 POSIX session",
            )
        return self._detached(
            factory,
            stdout,
            stderr,
            backend="platform-session",
            reason="测试 adapter 使用平台 session bootstrap",
        )

    def cleanup(self, backend: str) -> bool:
        if backend == "systemd-user":
            try:
                result = self._run(["systemctl", "--user", "stop", self.unit_name], 10)
            except (OSError, subprocess.SubprocessError):
                return False
            if result.returncode == 0:
                return True
            try:
                active = self._run(["systemctl", "--user", "is-active", "--quiet", self.unit_name], 3)
            except (OSError, subprocess.SubprocessError):
                return False
            return active.returncode != 0
        if backend != "launchd-user":
            return True
        domain = self._launchd_domain()
        if domain is None:
            return False
        try:
            target = f"{domain}/{self.launchd_label}"
            result = self._run(["/bin/launchctl", "bootout", target], 5)
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode != 0:
            try:
                result = self._run(["/bin/launchctl", "print", target], 3)
            except (OSError, subprocess.SubprocessError):
                return False
            if result.returncode == 0:
                return False
        try:
            self.launchd_plist.unlink(missing_ok=True)
        except OSError:
            return False
        return True
