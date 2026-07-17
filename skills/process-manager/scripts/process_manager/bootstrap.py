"""manager 的平台透明 bootstrap 策略。"""

from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .atomic import atomic_write_bytes, atomic_write_json, read_json_file
from .client import ManagerClient
from .errors import ConflictError, EnvironmentUnverifiableError, ManagerUnresponsiveError, PMError, RuntimeCorruptError
from .models import ManagerConfig
from .platforms.base import PlatformAdapter
from .runtime import SHA256_RE, config_digest, now_text, remove_manager_identity


CommandFactory = Callable[[str, str], list[str]]
MAX_BOOTSTRAP_CAPTURE_BYTES = 64 * 1024
BOOTSTRAP_CAPTURE_KEYS = frozenset(
    "schema operationId backend processIdentity expectedRuntimeFingerprint configDigest createdAt".split()
)
NON_NATIVE_BOOTSTRAP_BACKENDS = frozenset(
    {"windows-detached", "posix-session", "platform-session"}
)


def _validate_bootstrap_capture(
    config: ManagerConfig,
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != BOOTSTRAP_CAPTURE_KEYS:
        raise RuntimeCorruptError("manager bootstrap capture 字段集合无效")
    strings = ("operationId", "backend", "expectedRuntimeFingerprint", "configDigest", "createdAt")
    if value.get("schema") != "process-manager-bootstrap" or any(
        not isinstance(value.get(name), str) or not value[name] for name in strings
    ):
        raise RuntimeCorruptError("manager bootstrap capture 字段无效")
    try:
        canonical_id = uuid.UUID(value["operationId"]).hex
    except (ValueError, AttributeError) as exc:
        raise RuntimeCorruptError("manager bootstrap capture operationId 无效") from exc
    identity = value.get("processIdentity")
    if (
        canonical_id != value["operationId"]
        or value["configDigest"] != config_digest(config)
        or SHA256_RE.fullmatch(value["expectedRuntimeFingerprint"]) is None
        or not isinstance(identity, dict)
        or isinstance(identity.get("pid"), bool)
        or not isinstance(identity.get("pid"), int)
        or identity["pid"] <= 0
    ):
        raise RuntimeCorruptError("manager bootstrap capture identity 无效")
    return value


def read_bootstrap_capture(
    config: ManagerConfig,
    adapter: PlatformAdapter,
) -> dict[str, Any] | None:
    path = adapter.validate_runtime_path(config.paths.bootstrap)
    if not path.exists():
        return None
    adapter.verify_file(path)
    return _validate_bootstrap_capture(
        config,
        read_json_file(path, max_bytes=MAX_BOOTSTRAP_CAPTURE_BYTES),
    )


def write_bootstrap_capture(
    config: ManagerConfig,
    adapter: PlatformAdapter,
    *,
    operation_id: str,
    backend: str,
    runtime_fingerprint: str,
) -> dict[str, Any]:
    if read_bootstrap_capture(config, adapter) is not None:
        raise ConflictError("已有 manager bootstrap capture，拒绝覆盖")
    value = _validate_bootstrap_capture(
        config,
        {
            "schema": "process-manager-bootstrap",
            "operationId": operation_id,
            "backend": backend,
            "processIdentity": adapter.process_identity(os.getpid()),
            "expectedRuntimeFingerprint": runtime_fingerprint,
            "configDigest": config_digest(config),
            "createdAt": now_text(),
        },
    )
    atomic_write_json(config.paths.bootstrap, value)
    adapter.secure_file(config.paths.bootstrap)
    return value


def remove_bootstrap_capture(
    config: ManagerConfig,
    adapter: PlatformAdapter,
    *,
    operation_id: str,
    process_identity: dict[str, Any],
) -> bool:
    path = adapter.validate_runtime_path(config.paths.bootstrap)
    value = read_bootstrap_capture(config, adapter)
    if value is None:
        return True
    if value["operationId"] != operation_id or value["processIdentity"] != process_identity:
        return False
    if not path.exists():
        return True
    adapter.verify_file(path)
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    return not path.exists()


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
        manager_probe: Callable[[], bool] | None = None,
        native_ready_timeout: float = 5.0,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.runner = runner
        self.which = which
        self.manager_probe = manager_probe or self._manager_healthy
        self.native_ready_timeout = native_ready_timeout
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

    def _manager_healthy(self) -> bool:
        try:
            _, value = ManagerClient(self.config, self.adapter, timeout=0.5).request("GET", "/health")
        except PMError:
            return False
        data = value.get("data")
        return value.get("ok") is True and isinstance(data, dict) and data.get("managerReady") is True

    def _wait_for_native_manager(self) -> bool:
        deadline = time.monotonic() + max(0.0, self.native_ready_timeout)
        while True:
            if self.manager_probe():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def _systemd_unit_active(self) -> bool:
        try:
            result = self._run(["systemctl", "--user", "is-active", "--quiet", self.unit_name], 3)
        except (OSError, subprocess.SubprocessError) as exc:
            raise EnvironmentUnverifiableError("systemd user unit 状态无法读取") from exc
        if result.returncode == 0:
            return True
        if result.returncode in {3, 4}:
            return False
        raise EnvironmentUnverifiableError(
            "systemd user unit 状态无法验证",
            diagnostics={"returnCode": result.returncode},
        )

    def residue_present(self) -> bool:
        """只读检查确定性 native bootstrap 是否仍有残留。"""
        if read_bootstrap_capture(self.config, self.adapter) is not None:
            return True
        platform = self.adapter.selection.platform
        if platform == "linux":
            if not self.which("systemctl") or not os.environ.get("XDG_RUNTIME_DIR"):
                return False
            return self._systemd_unit_active()
        if platform != "macos":
            return False
        if self.launchd_plist.exists():
            return True
        domain = self._launchd_domain()
        if domain is None:
            return False
        try:
            result = self._run(
                ["/bin/launchctl", "print", f"{domain}/{self.launchd_label}"],
                3,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PMError("无法检查 launchd manager residue") from exc
        return result.returncode == 0

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
        except (OSError, subprocess.SubprocessError) as exc:
            raise EnvironmentUnverifiableError("systemd user manager 环境无法读取") from exc
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
            if self._systemd_unit_active():
                raise ManagerUnresponsiveError("systemd user manager unit 已存在但未形成可验证 identity")
            return None
        if result.returncode != 0:
            if self._systemd_unit_active():
                raise ManagerUnresponsiveError("systemd user manager unit 已存在但未形成可验证 identity")
            return None
        launched = BootstrapResult("systemd-user", reason, None)
        if self._wait_for_native_manager():
            return launched
        return launched if not self.cleanup(launched.backend) else None

    def _launchd_domain(self) -> str | None:
        if not hasattr(os, "getuid") or not Path("/bin/launchctl").is_file():
            return None
        domain = f"gui/{os.getuid()}"
        try:
            result = self._run(["/bin/launchctl", "print", domain], 3)
        except (OSError, subprocess.SubprocessError) as exc:
            raise EnvironmentUnverifiableError("launchd GUI user domain 无法读取") from exc
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
            if not self.config.paths.manager.exists() and not self._cleanup_launchd_job(domain):
                raise ManagerUnresponsiveError("launchd manager residue 清理未验证")
            atomic_write_bytes(self.launchd_plist, plistlib.dumps(plist, fmt=plistlib.FMT_XML))
            self.adapter.secure_file(self.launchd_plist)
            result = self._run(["/bin/launchctl", "bootstrap", domain, str(self.launchd_plist)], 10)
        except (OSError, subprocess.SubprocessError) as exc:
            if not self._cleanup_launchd_job(domain):
                raise ManagerUnresponsiveError("launchd bootstrap 异常且 residue 清理未验证") from exc
            return None
        if result.returncode != 0:
            if not self._cleanup_launchd_job(domain):
                raise ManagerUnresponsiveError("launchd bootstrap 失败且 residue 清理未验证")
            return None
        launched = BootstrapResult("launchd-user", reason, None)
        if self._wait_for_native_manager():
            return launched
        return launched if not self._cleanup_launchd_job(domain) else None

    def _cleanup_launchd_job(self, domain: str) -> bool:
        target = f"{domain}/{self.launchd_label}"
        try:
            self._run(["/bin/launchctl", "bootout", target], 5)
            result = self._run(["/bin/launchctl", "print", target], 3)
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode not in {3, 113}:
            return False
        try:
            self.launchd_plist.unlink(missing_ok=True)
        except OSError:
            return False
        return True

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
                reason="systemd user service 未形成可验证 manager，自动使用独立 POSIX session",
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
                reason="launchd 未形成可验证 manager，自动使用独立 POSIX session",
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
                self._run(["systemctl", "--user", "stop", self.unit_name], 10)
            except (OSError, subprocess.SubprocessError):
                return False
            active = self._systemd_unit_active()
            return not active
        if backend == "launchd-user":
            domain = self._launchd_domain()
            return domain is not None and self._cleanup_launchd_job(domain)
        return backend in NON_NATIVE_BOOTSTRAP_BACKENDS

    def stop_manager(
        self,
        identity: dict[str, Any],
        *,
        request_shutdown: Callable[[], dict[str, Any]] | None,
        allow_terminate: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """停止已验证的 manager identity，并清理精确 bootstrap。"""

        expected = identity["identity"]
        deadline = time.monotonic() + max(0.0, timeout)
        shutdown_result: dict[str, Any] = {}
        graceful_requested = False
        if request_shutdown is not None:
            try:
                shutdown_result = request_shutdown()
                graceful_requested = True
            except PMError:
                if not allow_terminate:
                    raise
        if graceful_requested:
            while self.adapter.identity_matches(expected) and time.monotonic() < deadline:
                time.sleep(0.1)
        if self.adapter.identity_matches(expected):
            if not allow_terminate or not self.adapter.terminate_manager(
                expected,
                timeout=max(0.0, deadline - time.monotonic()),
            ):
                raise ManagerUnresponsiveError(
                    "manager 未在停止期限内退出",
                    recommended_action="doctor",
                )
        remove_manager_identity(self.config, self.adapter, str(identity["instanceId"]))
        manager_path = self.adapter.validate_runtime_path(self.config.paths.manager)
        manager_stopped = not self.adapter.identity_matches(expected) and not manager_path.exists()
        bootstrap_cleaned = manager_stopped and self.cleanup(str(identity["bootstrapBackend"]))
        if not manager_stopped or not bootstrap_cleaned:
            raise ManagerUnresponsiveError(
                "manager identity 或 bootstrap 清理未验证",
                diagnostics={
                    "managerStopped": manager_stopped,
                    "bootstrapCleaned": bootstrap_cleaned,
                },
                recommended_action="doctor",
            )
        return {
            "managerStopped": True,
            "bootstrapCleaned": True,
            "shutdown": shutdown_result,
        }

    def cleanup_residue(
        self,
        *,
        timeout: float = 5.0,
        preferred_backend: str | None = None,
    ) -> bool:
        capture = read_bootstrap_capture(self.config, self.adapter)
        if capture is not None:
            identity = capture["processIdentity"]
            if self.adapter.identity_matches(identity) and not self.adapter.terminate_manager(
                identity,
                timeout=timeout,
            ):
                return False
            if self.adapter.identity_matches(identity) or not remove_bootstrap_capture(
                self.config,
                self.adapter,
                operation_id=str(capture["operationId"]),
                process_identity=identity,
            ):
                return False
        if preferred_backend is not None:
            return self.cleanup(preferred_backend)
        if not self.residue_present():
            return True
        platform = self.adapter.selection.platform
        if platform == "linux":
            return self.cleanup("systemd-user")
        if platform == "macos":
            return self.cleanup("launchd-user")
        return True
