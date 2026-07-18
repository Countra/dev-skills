"""process-manager 的配置与运行时状态模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import EnvironmentUnverifiableError, RuntimeInsecureError, RuntimeRebuildRequiredError, StateError
RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")
SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
ACTIVE_STATES = {"starting", "running", "stopping", "terminating"}
SESSION_ACTIVE_STATES = {"open", "terminating", "expired", "cleanup_failed"}
STATE_KEYS = frozenset("schema stateRevision workGeneration intakeFence active processes sessions "
                       "pendingPrunes tombstones".split())
RUN_RECORD_REQUIRED_KEYS = frozenset(
    "schema service processId processKey status runDir processFile createdAt recordRevision "
    "cleanupClaim ownership public internal".split()
)
RUN_RECORD_OPTIONAL_KEYS = {"updatedAt"}
INTAKE_FENCE_KEYS = frozenset("operationId kind expectedWorkGeneration installedAt".split())
CLEANUP_CLAIM_KEYS = frozenset("claimId managerInstanceId claimedAt deadlineAt".split())
OWNERSHIP_KEYS = {"kind", "sessionId"}
SESSION_KEYS = frozenset("schema sessionId revision holder kind state workspaceDigest managerInstanceId "
                         "leaseDurationSeconds createdAt renewedAt expiresAt closingReason runKeys cleanup".split())
SESSION_CLEANUP_KEYS = {"ownerEmpty", "cleanupVerified", "closedAt", "failures"}
WINDOWS_FILE_ALL_ACCESS = 0x001F01FF
WINDOWS_GRANT_ACCESS = 1
WINDOWS_SET_ACCESS = 2
WINDOWS_DENY_ACCESS = 3
WINDOWS_REVOKE_ACCESS = 4
WINDOWS_TRUSTED_SIDS = {
    "S-1-5-18",      # LocalSystem
    "S-1-5-32-544",  # Builtin Administrators
    "S-1-3-0",       # Creator Owner
    "S-1-3-4",       # Owner Rights
}
WINDOWS_BROAD_RESTRICTED_SIDS = {
    "S-1-1-0",       # Everyone
    "S-1-2-0",       # Local
    "S-1-5-4",       # Interactive
    "S-1-5-11",      # Authenticated Users
    "S-1-5-32-545",  # Builtin Users
}


@dataclass(frozen=True)
class WindowsAclEntry:
    sid: str
    mask: int
    access_mode: int
    inheritance: int


@dataclass(frozen=True)
class WindowsAclSnapshot:
    owner_sid: str
    entries: tuple[WindowsAclEntry, ...]
    effective_mask: int


def validate_windows_acl_snapshot(
    snapshot: WindowsAclSnapshot,
    current_sid: str,
    restricted_sids: tuple[str, ...] = (),
    token_owner_sid: str | None = None,
) -> None:
    """验证 Windows ACL 语义，不依赖继承形态或 SDDL 文本。"""

    accepted_owners = {current_sid} | ({token_owner_sid} if token_owner_sid else set())
    if snapshot.owner_sid not in accepted_owners:
        raise RuntimeInsecureError(
            "Windows runtime owner 不属于当前 token",
            diagnostics={"ownerSid": snapshot.owner_sid, "acceptedOwnerSids": sorted(accepted_owners)},
        )
    broad = WINDOWS_BROAD_RESTRICTED_SIDS.intersection(restricted_sids)
    if broad:
        raise EnvironmentUnverifiableError(
            "当前 Windows restricting SID 过宽，无法构造私有 runtime",
            diagnostics={"restrictingSids": sorted(broad)},
        )
    trusted = WINDOWS_TRUSTED_SIDS | accepted_owners | set(restricted_sids)
    for entry in snapshot.entries:
        if entry.access_mode in {WINDOWS_GRANT_ACCESS, WINDOWS_SET_ACCESS}:
            if entry.mask and entry.sid not in trusted:
                raise RuntimeInsecureError(
                    "Windows runtime ACL 向非信任 trustee 授予访问",
                    diagnostics={"trustee": entry.sid, "mask": entry.mask},
                )
        elif entry.access_mode not in {WINDOWS_DENY_ACCESS, WINDOWS_REVOKE_ACCESS}:
            raise EnvironmentUnverifiableError(
                "Windows runtime ACL 包含无法验证的 ACE 模式",
                diagnostics={"accessMode": entry.access_mode},
            )
    if snapshot.effective_mask & WINDOWS_FILE_ALL_ACCESS != WINDOWS_FILE_ALL_ACCESS:
        raise RuntimeInsecureError(
            "当前用户缺少 Windows runtime 完整访问权",
            diagnostics={"effectiveMask": snapshot.effective_mask},
        )


def empty_state() -> dict[str, Any]:
    return {
        "schema": "process-manager",
        "stateRevision": 0,
        "workGeneration": 0,
        "intakeFence": None,
        "active": {},
        "processes": {},
        "sessions": {},
        "pendingPrunes": {},
        "tombstones": {},
    }


def process_key(service: str, run_id: str) -> str:
    return f"{service}.{run_id}"


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
    def bootstrap(self) -> Path:
        return self.control / "bootstrap.json"

    @property
    def operation(self) -> Path:
        return self.control / "operation.json"

    @property
    def operation_lock(self) -> Path:
        return self.control / "operation.lock"

    @property
    def repository_lock(self) -> Path:
        return self.control / "repository.lock"

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
    def sessions(self) -> Path:
        return self.state_root / "sessions"

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
class StateSchema:
    paths: RuntimePaths

    def run_paths(self, service: str, run_id: str) -> tuple[Path, Path]:
        if not SERVICE_NAME_RE.fullmatch(service) or not RUN_ID_RE.fullmatch(run_id):
            raise StateError("run identity 格式无效")
        run_dir = self.paths.runs / service / run_id
        return run_dir, run_dir / "process.json"

    def session_path(self, session_id: str) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise StateError("session identity 格式无效")
        return self.paths.sessions / f"{session_id}.json"

    @staticmethod
    def _session_time(value: Any, label: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError as exc:
            raise StateError(f"session {label} 不是 RFC3339 时间") from exc
        if parsed is None or parsed.tzinfo is None:
            raise StateError(f"session {label} 不是 RFC3339 时间")
        return parsed

    @staticmethod
    def validate_ownership(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != OWNERSHIP_KEYS:
            raise StateError("run ownership 字段集合无效")
        kind, session_id = value.get("kind"), value.get("sessionId")
        if kind == "persistent" and session_id is None:
            return value
        if kind == "session" and isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id):
            return value
        raise StateError("run ownership 字段无效")

    def validate_record(self, key: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("schema") != "process-manager":
            raise RuntimeRebuildRequiredError("run record 使用旧或未知 runtime schema")
        fields = set(value)
        if not RUN_RECORD_REQUIRED_KEYS <= fields or fields - RUN_RECORD_REQUIRED_KEYS - RUN_RECORD_OPTIONAL_KEYS:
            raise StateError("run record 字段集合无效")
        service = value.get("service")
        run_id = value.get("processId")
        if (
            not isinstance(service, str)
            or not isinstance(run_id, str)
            or key != process_key(service, run_id)
            or value.get("processKey") != key
        ):
            raise StateError("run record identity 不一致")
        run_dir, process_file = self.run_paths(service, run_id)
        if value.get("runDir") != str(run_dir) or value.get("processFile") != str(process_file):
            raise StateError("run record path 不一致")
        if not isinstance(value.get("public"), dict) or not isinstance(value.get("internal"), dict):
            raise StateError("run record public/internal 必须是 object")
        ownership = self.validate_ownership(value.get("ownership"))
        if value["public"].get("ownership") != ownership:
            raise StateError("run public ownership 与 record 不一致")
        revision = value.get("recordRevision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise StateError("run record revision 无效")
        claim = value.get("cleanupClaim")
        if claim is not None:
            if not isinstance(claim, dict) or set(claim) != CLEANUP_CLAIM_KEYS:
                raise StateError("run cleanup claim 字段集合无效")
            if any(not isinstance(claim.get(name), str) or not claim[name] for name in CLEANUP_CLAIM_KEYS):
                raise StateError("run cleanup claim 字段无效")
        if value["public"].get("state") != value.get("status"):
            raise StateError("run public state 与 status 不一致")
        return value

    def validate_session(self, session_id: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != SESSION_KEYS:
            raise StateError("session record 字段集合无效")
        if (
            value.get("schema") != "process-manager-session"
            or value.get("sessionId") != session_id
            or not SESSION_ID_RE.fullmatch(session_id)
            or value.get("kind") not in {"validation", "task"}
            or value.get("state") not in SESSION_ACTIVE_STATES | {"closed"}
        ):
            raise StateError("session record identity/kind/state 无效")
        revision, ttl = value.get("revision"), value.get("leaseDurationSeconds")
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
            or isinstance(ttl, bool)
            or not isinstance(ttl, int)
            or not 60 <= ttl <= 86400
        ):
            raise StateError("session revision/TTL 无效")
        for name in ("holder", "workspaceDigest", "managerInstanceId"):
            if not isinstance(value.get(name), str) or not value[name]:
                raise StateError(f"session {name} 无效")
        created, renewed, expires = (
            self._session_time(value.get(name), name)
            for name in ("createdAt", "renewedAt", "expiresAt")
        )
        if not created <= renewed < expires:
            raise StateError("session lease 时间顺序无效")
        if len(value["holder"].encode("utf-8")) > 256 or any(ord(char) < 32 for char in value["holder"]):
            raise StateError("session holder 无效")
        if re.fullmatch(r"[0-9a-f]{64}", value["workspaceDigest"]) is None:
            raise StateError("session workspaceDigest 无效")
        if SESSION_ID_RE.fullmatch(value["managerInstanceId"]) is None:
            raise StateError("session managerInstanceId 无效")
        run_keys = value.get("runKeys")
        if not isinstance(run_keys, list) or any(not isinstance(key, str) or not key for key in run_keys):
            raise StateError("session runKeys 无效")
        if len(run_keys) != len(set(run_keys)):
            raise StateError("session runKeys 包含重复项")
        cleanup = value.get("cleanup")
        if cleanup is not None:
            if not isinstance(cleanup, dict) or set(cleanup) != SESSION_CLEANUP_KEYS:
                raise StateError("session cleanup 字段集合无效")
            failures = cleanup.get("failures")
            self._session_time(cleanup.get("closedAt"), "cleanup.closedAt")
            if (
                not isinstance(cleanup.get("ownerEmpty"), bool)
                or not isinstance(cleanup.get("cleanupVerified"), bool)
                or not isinstance(failures, list)
                or any(not isinstance(item, str) for item in failures)
            ):
                raise StateError("session cleanup 字段无效")
        state_name, closing = value["state"], value.get("closingReason")
        if state_name == "open" and (closing is not None or cleanup is not None):
            raise StateError("open session 不能包含 closing/cleanup")
        if state_name != "open" and (not isinstance(closing, str) or not closing):
            raise StateError("non-open session 必须包含 closingReason")
        if state_name in {"terminating", "expired"} and cleanup is not None:
            raise StateError("待清理 session 不能提前写 cleanup")
        if state_name == "cleanup_failed" and (not isinstance(cleanup, dict) or cleanup["cleanupVerified"]):
            raise StateError("cleanup_failed session 必须保留失败证据")
        if value["state"] == "closed":
            if run_keys or not isinstance(cleanup, dict) or not cleanup["ownerEmpty"] or not cleanup["cleanupVerified"]:
                raise StateError("closed session 必须 owner empty 且 cleanup verified")
        return value

    def validate_state(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("schema") != "process-manager":
            raise RuntimeRebuildRequiredError("process state 使用旧或未知 runtime schema")
        if set(value) != STATE_KEYS:
            raise StateError("process state 字段集合无效")
        active = value.get("active")
        processes = value.get("processes")
        sessions = value.get("sessions")
        pending_prunes = value.get("pendingPrunes")
        tombstones = value.get("tombstones")
        revision = value.get("stateRevision")
        generation = value.get("workGeneration")
        if (
            not isinstance(active, dict)
            or not isinstance(processes, dict)
            or not isinstance(sessions, dict)
            or not isinstance(pending_prunes, dict)
            or not isinstance(tombstones, dict)
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 0
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 0
        ):
            raise StateError("process state 结构无效")
        self._validate_fence(value.get("intakeFence"))
        for key, record in processes.items():
            self.validate_record(key, record)
        for session_id, session in sessions.items():
            self.validate_session(session_id, session)
        from .protocol import validate_resource_state
        validate_resource_state(pending_prunes, tombstones, processes, sessions)
        for service, key in active.items():
            if not isinstance(service, str) or not isinstance(key, str) or key not in processes:
                raise StateError("active 索引引用无效")
            record = processes[key]
            if record.get("service") != service or record.get("status") not in ACTIVE_STATES:
                raise StateError("active 索引与 run record 不一致")
        for key, record in processes.items():
            if record.get("status") in ACTIVE_STATES and active.get(record["service"]) != key:
                raise StateError("active run record 缺少唯一索引")
            ownership = record["ownership"]
            if record.get("status") in ACTIVE_STATES and ownership["kind"] == "session":
                session = sessions.get(ownership["sessionId"])
                if not isinstance(session, dict) or session["state"] not in SESSION_ACTIVE_STATES:
                    raise StateError("active run 引用无效 session")
                if session["runKeys"].count(key) != 1:
                    raise StateError("active run 缺少唯一 session 反向索引")
        for session_id, session in sessions.items():
            for key in session["runKeys"]:
                record = processes.get(key)
                if (
                    not isinstance(record, dict)
                    or record.get("status") not in ACTIVE_STATES
                    or record["ownership"] != {"kind": "session", "sessionId": session_id}
                ):
                    raise StateError("session runKeys 与 active run ownership 不一致")
        return value

    @staticmethod
    def _validate_fence(fence: Any) -> None:
        if fence is None:
            return
        if not isinstance(fence, dict) or set(fence) != INTAKE_FENCE_KEYS:
            raise StateError("intake fence 字段集合无效")
        if (
            not isinstance(fence.get("operationId"), str)
            or not fence["operationId"]
            or fence.get("kind") not in {"stop", "restart"}
            or isinstance(fence.get("expectedWorkGeneration"), bool)
            or not isinstance(fence.get("expectedWorkGeneration"), int)
            or fence["expectedWorkGeneration"] < 0
            or not isinstance(fence.get("installedAt"), str)
            or not fence["installedAt"]
        ):
            raise StateError("intake fence 字段无效")


@dataclass(frozen=True)
class ManagerConfig:
    workspace_root: Path
    state_root: Path
    host: str
    port: int
    max_request_bytes: int
    history_max_inactive: int
    history_max_age_seconds: int
    history_max_tombstones: int
    history_delete_run_dirs: bool
    limits: dict[str, int]
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
                "maxAgeSeconds": self.history_max_age_seconds,
                "maxTombstones": self.history_max_tombstones,
                "deleteRunDirs": self.history_delete_run_dirs,
            },
            "limits": dict(self.limits),
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
