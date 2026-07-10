"""Linux delegated cgroup v2 与安全 fallback。"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from ..errors import IdentityError, SupervisorError
from .base import PlatformSelection, RunOwner
from .posix import PosixAdapter, PosixRunOwner


CGROUP_ROOT = Path("/sys/fs/cgroup")


def discover_delegated_cgroup() -> tuple[Path | None, str]:
    controllers = CGROUP_ROOT / "cgroup.controllers"
    membership = Path("/proc/self/cgroup")
    if not controllers.is_file() or not membership.is_file():
        return None, "cgroup v2 不可用"
    try:
        lines = membership.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, "无法读取当前 cgroup membership"
    unified = next((line.split("::", 1)[1] for line in lines if line.startswith("0::")), None)
    if unified is None:
        return None, "当前进程不在 unified cgroup v2 hierarchy"
    candidate = (CGROUP_ROOT / unified.lstrip("/")).resolve()
    try:
        candidate.relative_to(CGROUP_ROOT.resolve())
    except ValueError:
        return None, "当前 cgroup 路径越界"
    required = (candidate / "cgroup.procs", candidate / "cgroup.subtree_control")
    if not all(path.exists() for path in required) or not os.access(candidate, os.W_OK):
        return None, "当前 cgroup 未委托写权限"
    return candidate, "检测到可写 delegated cgroup v2 subtree"


class LinuxProcessGroupAdapter(PosixAdapter):
    def process_identity(self, pid: int) -> dict[str, Any]:
        stat_path = Path(f"/proc/{pid}/stat")
        exe_path = Path(f"/proc/{pid}/exe")
        try:
            stat_text = stat_path.read_text(encoding="utf-8")
            closing = stat_text.rfind(")")
            fields = stat_text[closing + 2 :].split()
            start_time = fields[19]
            executable = str(exe_path.resolve())
        except (OSError, IndexError, ValueError) as exc:
            raise IdentityError("Linux 进程身份不可读取") from exc
        return {"pid": pid, "startTimeTicks": start_time, "executable": executable}

    def identity_matches(self, expected: dict[str, Any]) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int):
            return False
        try:
            return self.process_identity(pid) == expected
        except IdentityError:
            return False


class CgroupRunOwner(PosixRunOwner):
    def __init__(
        self,
        selection: PlatformSelection,
        host: subprocess.Popen[str],
        capability_hash: str,
        cgroup_path: Path,
    ) -> None:
        super().__init__(selection, host, capability_hash)
        self.cgroup_path = cgroup_path
        self.cgroup_path.mkdir(mode=0o700)
        if not (self.cgroup_path / "cgroup.kill").exists():
            raise SupervisorError("delegated cgroup 不支持 cgroup.kill")
        try:
            (self.cgroup_path / "cgroup.procs").write_text(f"{host.pid}\n", encoding="ascii")
        except OSError as exc:
            raise SupervisorError("无法把 service-host 加入 delegated cgroup") from exc
        if str(host.pid) not in self._member_pids():
            raise SupervisorError("service-host cgroup membership 验证失败")

    @property
    def control_data(self) -> dict[str, Any]:
        return {"mode": "cgroup-v2", "cgroupPath": str(self.cgroup_path)}

    def _member_pids(self) -> set[str]:
        try:
            return set((self.cgroup_path / "cgroup.procs").read_text(encoding="ascii").split())
        except OSError as exc:
            raise SupervisorError("无法读取 run cgroup membership") from exc

    def bind_target(self, target: dict[str, Any]) -> None:
        super().bind_target(target)
        pid = target.get("pid")
        if str(pid) not in self._member_pids():
            raise IdentityError("target 未继承 run cgroup membership")

    def force_stop(self) -> bool:
        self.send_host_command("force_stop")
        try:
            (self.cgroup_path / "cgroup.kill").write_text("1\n", encoding="ascii")
            return True
        except OSError:
            return False

    def is_empty(self) -> bool:
        try:
            events = (self.cgroup_path / "cgroup.events").read_text(encoding="ascii").splitlines()
        except OSError:
            return False
        populated = next((line.split()[1] for line in events if line.startswith("populated ")), None)
        return populated == "0" and self.host.poll() is not None

    def close(self) -> None:
        super().close()
        if self.is_empty():
            try:
                self.cgroup_path.rmdir()
            except OSError:
                return

    def internal_identity(self) -> dict[str, Any]:
        return {**super().internal_identity(), "cgroupPath": str(self.cgroup_path)}


class LinuxCgroupAdapter(LinuxProcessGroupAdapter):
    def __init__(
        self,
        selection: PlatformSelection,
        workspace_root: Path,
        state_root: Path,
        delegated_root: Path,
    ) -> None:
        super().__init__(selection, workspace_root, state_root)
        workspace_hash = hashlib.sha256(str(workspace_root.resolve()).encode("utf-8")).hexdigest()[:12]
        self.cgroup_base = delegated_root / f"dev-skills-pm-{workspace_hash}"

    def create_run_owner(
        self,
        run_id: str,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> RunOwner:
        if host.poll() is not None:
            raise SupervisorError("service-host 在 owner 建立前退出")
        try:
            self.cgroup_base.mkdir(mode=0o700, exist_ok=True)
            run_path = self.cgroup_base / run_id
            return CgroupRunOwner(self.selection, host, capability_hash, run_path)
        except OSError as exc:
            raise SupervisorError("delegated cgroup owner 创建失败") from exc
