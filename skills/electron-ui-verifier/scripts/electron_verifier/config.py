"""Verifier service 的运行配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import VerifierError
from .security import validate_bind_host


def _absolute(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise VerifierError("invalid_config", f"{label} 必须是绝对路径")
    path = Path(value)
    if not path.is_absolute():
        raise VerifierError("invalid_config", f"{label} 必须是绝对路径：{value}")
    return path


def _within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    resolved_root = root.resolve()
    return resolved == resolved_root or resolved_root in resolved.parents


@dataclass(frozen=True)
class ServiceConfig:
    config_file: Path
    host: str
    port: int
    max_port_switches: int
    workspace_root: Path
    state_root: Path
    token_file: Path
    server_file: Path
    sessions_file: Path
    reports_dir: Path
    pending_dir: Path
    workflows_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    tmp_dir: Path
    runs_dir: Path
    operations_dir: Path

    @classmethod
    def load(cls, path: Path) -> "ServiceConfig":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("invalid_config", f"无法读取 verifier config：{exc}", status=500) from exc
        if not isinstance(data, dict):
            raise VerifierError("invalid_config", "verifier config 根节点必须是 object", status=500)
        host = validate_bind_host(str(data.get("host") or "127.0.0.1"))
        port = int(data.get("port") or 18180)
        if port < 1 or port > 65535:
            raise VerifierError("invalid_config", "config.port 必须在 1..65535", status=500)
        retry = data.get("portRetry") or {}
        if not isinstance(retry, dict):
            raise VerifierError("invalid_config", "config.portRetry 必须是 object", status=500)
        workspace_root = _absolute(data.get("workspaceRoot"), "config.workspaceRoot")
        state_root = _absolute(data.get("stateRoot"), "config.stateRoot")
        if state_root.resolve() == workspace_root.resolve() or not _within(state_root, workspace_root):
            raise VerifierError("invalid_config", "config.stateRoot 必须是 workspaceRoot 内的独立目录", status=500)
        if not _within(path, workspace_root):
            raise VerifierError("invalid_config", "verifier config 必须位于 workspaceRoot 内", status=500)
        enabled = retry.get("enabled", True) is not False
        switches = int(retry.get("maxSwitches", 3)) if enabled else 0
        if switches < 0 or switches > 20:
            raise VerifierError("invalid_config", "config.portRetry.maxSwitches 必须在 0..20", status=500)
        paths = {
            "token_file": _absolute(data.get("tokenFile"), "config.tokenFile"),
            "server_file": _absolute(data.get("serverFile"), "config.serverFile"),
            "sessions_file": _absolute(data.get("sessionsFile"), "config.sessionsFile"),
            "reports_dir": _absolute(data.get("reportsDir"), "config.reportsDir"),
            "pending_dir": _absolute(data.get("pendingDir") or str(state_root / "pending"), "config.pendingDir"),
            "workflows_dir": _absolute(data.get("workflowsDir") or str(state_root / "workflows"), "config.workflowsDir"),
            "artifacts_dir": _absolute(data.get("artifactsDir"), "config.artifactsDir"),
            "logs_dir": _absolute(data.get("logsDir"), "config.logsDir"),
            "tmp_dir": _absolute(data.get("tmpDir"), "config.tmpDir"),
            "runs_dir": _absolute(data.get("runsDir") or str(state_root / "runs"), "config.runsDir"),
            "operations_dir": _absolute(
                data.get("operationsDir") or str(state_root / "operations"),
                "config.operationsDir",
            ),
        }
        escaped = [name for name, candidate in paths.items() if not _within(candidate, state_root)]
        if escaped:
            raise VerifierError(
                "invalid_config",
                "verifier runtime 路径必须位于 stateRoot 内",
                status=500,
                details={"fields": escaped},
            )
        return cls(
            config_file=path,
            host=host,
            port=port,
            max_port_switches=switches,
            workspace_root=workspace_root,
            state_root=state_root,
            **paths,
        )

    def ensure_directories(self) -> None:
        for path in (
            self.state_root,
            self.reports_dir,
            self.pending_dir,
            self.workflows_dir,
            self.artifacts_dir,
            self.logs_dir,
            self.tmp_dir,
            self.runs_dir,
            self.operations_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def token(self) -> str:
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise VerifierError("token_unavailable", f"无法读取 verifier token：{exc}", status=500) from exc
        if not token:
            raise VerifierError("token_unavailable", "verifier token 为空", status=500)
        return token
