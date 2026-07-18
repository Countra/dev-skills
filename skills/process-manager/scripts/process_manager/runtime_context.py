"""显式 workspace/config 到唯一 runtime 的只读解析。"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .config import load_manager_config
from .errors import ContextInvalidError, PMError
from .models import ManagerConfig
from .runtime import config_digest


@dataclass(frozen=True)
class RuntimeContext:
    workspace_root: Path
    config_path: Path
    state_root: Path
    workspace_digest: str
    config_digest: str | None
    initialized: bool
    config: ManagerConfig | None

    def public_dict(self) -> dict[str, str | bool | None]:
        return {
            "workspaceRoot": str(self.workspace_root),
            "configPath": str(self.config_path),
            "stateRoot": str(self.state_root),
            "workspaceDigest": self.workspace_digest,
            "configDigest": self.config_digest,
            "initialized": self.initialized,
        }


def _absolute_path(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ContextInvalidError(f"{label} 必须是绝对路径", recommended_action="provide_context")
    return path.resolve()


def _workspace_digest(workspace: Path) -> str:
    normalized = os.path.normcase(str(workspace.resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _workspace_config_path(workspace: Path) -> Path:
    return workspace / ".harness" / "process-manager" / "config.json"


def _infer_workspace(config_path: Path) -> Path:
    expected_tail = (".harness", "process-manager", "config.json")
    if tuple(config_path.parts[-3:]) != expected_tail:
        raise ContextInvalidError(
            "尚未创建的 --config 必须指向 <workspace>/.harness/process-manager/config.json",
            recommended_action="init",
        )
    workspace = config_path.parents[2]
    if not workspace.is_dir():
        raise ContextInvalidError(f"workspace 不存在: {workspace}", recommended_action="provide_context")
    return workspace.resolve()


def _load_context(config_path: Path, expected_workspace: Path | None) -> RuntimeContext:
    try:
        config = load_manager_config(config_path)
    except PMError as exc:
        raise ContextInvalidError(
            f"manager context 无效: {config_path}",
            diagnostics={"causeCode": exc.code},
            recommended_action="doctor",
        ) from exc
    if expected_workspace is not None and config.workspace_root != expected_workspace:
        raise ContextInvalidError(
            "config.workspaceRoot 与显式 workspace 不匹配",
            recommended_action="provide_context",
        )
    return RuntimeContext(
        workspace_root=config.workspace_root,
        config_path=config.config_path,
        state_root=config.state_root,
        workspace_digest=_workspace_digest(config.workspace_root),
        config_digest=config_digest(config),
        initialized=True,
        config=config,
    )


def resolve_runtime_context(
    *,
    workspace: str | Path | None = None,
    config: str | Path | None = None,
) -> RuntimeContext:
    if (workspace is None) == (config is None):
        raise ContextInvalidError(
            "必须且只能提供 --workspace 或 --config 之一",
            recommended_action="provide_context",
        )
    if workspace is not None:
        workspace_root = _absolute_path(workspace, "--workspace")
        if not workspace_root.is_dir():
            raise ContextInvalidError(
                f"workspace 不存在: {workspace_root}",
                recommended_action="provide_context",
            )
        config_path = _workspace_config_path(workspace_root)
        if config_path.exists():
            return _load_context(config_path, workspace_root)
        return RuntimeContext(
            workspace_root=workspace_root,
            config_path=config_path,
            state_root=config_path.parent,
            workspace_digest=_workspace_digest(workspace_root),
            config_digest=None,
            initialized=False,
            config=None,
        )

    config_path = _absolute_path(config, "--config")
    if config_path.exists():
        return _load_context(config_path, None)
    workspace_root = _infer_workspace(config_path)
    return RuntimeContext(
        workspace_root=workspace_root,
        config_path=config_path,
        state_root=config_path.parent,
        workspace_digest=_workspace_digest(workspace_root),
        config_digest=None,
        initialized=False,
        config=None,
    )
