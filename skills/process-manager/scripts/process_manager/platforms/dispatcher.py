"""唯一的平台探测与内部 owner 选择点。"""

from __future__ import annotations

import sys
from pathlib import Path

from ..errors import UnsupportedPlatformError
from .base import PlatformAdapter, PlatformSelection


def describe_platform_selection(
    platform_name: str,
    *,
    delegated_cgroup_available: bool = False,
    reason: str = "automatic platform detection",
) -> PlatformSelection:
    if platform_name.startswith("win"):
        return PlatformSelection("windows", "job-object", "kernel-process-tree", reason)
    if platform_name.startswith("linux"):
        if delegated_cgroup_available:
            return PlatformSelection("linux", "cgroup-v2", "kernel-process-tree", reason)
        return PlatformSelection("linux", "process-group-guardian", "process-group", reason)
    if platform_name == "darwin":
        return PlatformSelection("macos", "process-group-guardian", "process-group+kqueue", reason)
    raise UnsupportedPlatformError(
        "当前平台没有受支持的安全进程 owner",
        diagnostics={"platform": platform_name, "backend": "none", "capability": "none"},
    )


def select_platform_adapter(
    workspace_root: Path,
    state_root: Path,
    *,
    platform_name: str | None = None,
    delegated_cgroup: Path | None | object = Ellipsis,
) -> PlatformAdapter:
    current = platform_name or sys.platform
    if current.startswith("win"):
        from .windows import WindowsAdapter

        return WindowsAdapter(
            describe_platform_selection(current, reason="Windows Job Object 可用"),
            workspace_root,
            state_root,
        )
    if current.startswith("linux"):
        from .linux import LinuxCgroupAdapter, LinuxProcessGroupAdapter, discover_delegated_cgroup

        if delegated_cgroup is Ellipsis:
            cgroup_root, reason = discover_delegated_cgroup()
        else:
            cgroup_root = delegated_cgroup
            reason = "测试注入 delegated cgroup" if isinstance(cgroup_root, Path) else "delegated cgroup 不可用"
        if isinstance(cgroup_root, Path):
            return LinuxCgroupAdapter(
                describe_platform_selection(current, delegated_cgroup_available=True, reason=reason),
                workspace_root,
                state_root,
                cgroup_root,
            )
        return LinuxProcessGroupAdapter(
            describe_platform_selection(current, delegated_cgroup_available=False, reason=reason),
            workspace_root,
            state_root,
        )
    if current == "darwin":
        from .macos import MacOSAdapter

        return MacOSAdapter(
            describe_platform_selection(
                current,
                reason="macOS 使用 guardian 与 kqueue；launchd 仅用于可用时的 manager bootstrap",
            ),
            workspace_root,
            state_root,
        )
    raise UnsupportedPlatformError(
        "当前平台没有受支持的安全进程 owner",
        diagnostics={"platform": current, "backend": "none", "capability": "none"},
    )
