"""process-manager 的不可变配置模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimePaths:
    state_root: Path

    @property
    def config(self) -> Path:
        return self.state_root / "config.json"

    @property
    def control(self) -> Path:
        return self.state_root / "control"

    @property
    def token(self) -> Path:
        return self.control / "token"

    @property
    def manager(self) -> Path:
        return self.control / "manager.json"

    @property
    def manager_lock(self) -> Path:
        return self.control / "manager.lock"

    @property
    def operation(self) -> Path:
        return self.control / "operation.json"

    @property
    def operation_lock(self) -> Path:
        return self.control / "operation.lock"

    @property
    def processes(self) -> Path:
        return self.state_root / "processes.json"

    @property
    def processes_backup(self) -> Path:
        return self.state_root / "processes.json.bak"

    @property
    def services(self) -> Path:
        return self.state_root / "services"

    @property
    def runs(self) -> Path:
        return self.state_root / "runs"

    @property
    def logs(self) -> Path:
        return self.state_root / "logs"

    @property
    def tmp(self) -> Path:
        return self.state_root / "tmp"


@dataclass(frozen=True)
class ManagerConfig:
    workspace_root: Path
    state_root: Path
    host: str
    port: int
    max_request_bytes: int
    history_max_inactive: int
    history_delete_run_dirs: bool
    log_max_bytes: int
    log_backups: int
    config_path: Path

    @property
    def paths(self) -> RuntimePaths:
        return RuntimePaths(self.state_root)

    def public_dict(self) -> dict[str, Any]:
        return {
            "workspaceRoot": str(self.workspace_root),
            "stateRoot": str(self.state_root),
            "control": {
                "host": self.host,
                "port": self.port,
                "maxRequestBytes": self.max_request_bytes,
            },
            "history": {
                "maxInactive": self.history_max_inactive,
                "deleteRunDirs": self.history_delete_run_dirs,
            },
            "logs": {
                "maxBytes": self.log_max_bytes,
                "backups": self.log_backups,
            },
        }


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    kind: str
    cwd: Path
    launcher: dict[str, Any]
    environment: dict[str, Any]
    stop: dict[str, Any]
    readiness: dict[str, Any] | None
    logs: dict[str, Any]
    source_path: Path
    config_digest: str
    launcher_digest: str

    def state_summary(self) -> dict[str, Any]:
        launcher_type = str(self.launcher["type"])
        summary: dict[str, Any] = {
            "type": launcher_type,
            "sha256": self.launcher_digest,
            "pathArgCount": len(self.launcher.get("pathArgs", [])),
            "argCount": len(self.launcher.get("args", [])),
        }
        if launcher_type == "direct":
            summary["executableName"] = Path(str(self.launcher["executable"])).name
        else:
            summary["interpreterName"] = Path(str(self.launcher["interpreter"])).name
            summary["scriptName"] = Path(str(self.launcher["script"])).name
        return summary

    def public_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "cwd": str(self.cwd),
            "launcher": self.state_summary(),
            "environment": {
                "inherit": list(self.environment["inherit"]),
                "setKeys": sorted(self.environment["set"]),
                "fromEnv": list(self.environment["fromEnv"]),
            },
            "stop": dict(self.stop),
            "readiness": dict(self.readiness) if self.readiness else None,
            "logs": dict(self.logs),
            "configSha256": self.config_digest,
        }
