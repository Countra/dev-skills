"""平台适配层的内部窄契约。"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlatformSelection:
    platform: str
    backend: str
    capability: str
    selection_reason: str

    def diagnostics(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "backend": self.backend,
            "capability": self.capability,
            "selectionReason": self.selection_reason,
        }


class ManagerLock(ABC):
    @abstractmethod
    def close(self) -> None:
        """释放当前 manager 实例锁。"""

    def __enter__(self) -> "ManagerLock":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.close()


class RunOwner(ABC):
    def __init__(self, selection: PlatformSelection, host: subprocess.Popen[str], capability_hash: str) -> None:
        self.selection = selection
        self.host = host
        self.capability_hash = capability_hash

    @property
    @abstractmethod
    def control_data(self) -> dict[str, Any]:
        """返回只供 service-host 使用的内部 owner 控制信息。"""

    @abstractmethod
    def bind_target(self, target: dict[str, Any]) -> None:
        """验证 target 已进入当前 owner。"""

    def send_host_command(self, command: str) -> None:
        if self.host.stdin is None or self.host.poll() is not None:
            return
        message = json.dumps({"command": command}, separators=(",", ":")) + "\n"
        try:
            self.host.stdin.write(message)
            self.host.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            return

    @abstractmethod
    def graceful_stop(self) -> bool:
        """请求统一的优雅停止。"""

    @abstractmethod
    def force_stop(self) -> bool:
        """强制收口当前 owner。"""

    @abstractmethod
    def is_empty(self) -> bool:
        """确认 owner 不再包含受管 target。"""

    @abstractmethod
    def close(self) -> None:
        """释放 owner 资源；不能波及 owner 外进程。"""

    def internal_identity(self) -> dict[str, Any]:
        return {
            **self.selection.diagnostics(),
            "capabilityHash": self.capability_hash,
            "hostPid": self.host.pid,
        }


class PlatformAdapter(ABC):
    def __init__(self, selection: PlatformSelection, workspace_root: Path, state_root: Path) -> None:
        self.selection = selection
        self.workspace_root = workspace_root.resolve()
        self.state_root = state_root.resolve()

    @abstractmethod
    def secure_directory(self, path: Path) -> None:
        """创建并验证仅当前用户可访问的目录。"""

    @abstractmethod
    def secure_file(self, path: Path) -> None:
        """验证文件仅当前用户可访问。"""

    @abstractmethod
    def verify_file(self, path: Path) -> None:
        """只读验证文件权限，不自动修复。"""

    @abstractmethod
    def acquire_manager_lock(self) -> ManagerLock:
        """获取 workspace 派生的单实例锁。"""

    @abstractmethod
    def spawn_manager(
        self,
        command: list[str],
        *,
        stdout: Any,
        stderr: Any,
    ) -> subprocess.Popen[Any]:
        """使用当前平台安全的 detached bootstrap 启动 manager。"""

    @abstractmethod
    def spawn_service_host(
        self,
        command: list[str],
        *,
        cwd: Path,
        environment: dict[str, str],
    ) -> subprocess.Popen[str]:
        """启动仍处于 target-before-release 阶段的 service-host。"""

    @abstractmethod
    def create_run_owner(
        self,
        run_id: str,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> RunOwner:
        """建立并验证本次 run 的内部 owner。"""

    @abstractmethod
    def process_identity(self, pid: int) -> dict[str, Any]:
        """返回当前平台可验证的进程身份补充字段。"""

    @abstractmethod
    def identity_matches(self, expected: dict[str, Any]) -> bool:
        """验证进程身份未被 PID 复用。"""

    def diagnostics(self) -> dict[str, str]:
        return self.selection.diagnostics()
