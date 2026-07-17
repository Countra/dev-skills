"""平台冒烟共享的公共契约、service 构造与有界轮询工具。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from process_manager.manager import ProcessManager  # noqa: E402


PUBLIC_SCRIPTS = (
    "pm_manager.py",
    "pm_init.py",
    "pm_health.py",
    "pm_validate.py",
    "pm_start.py",
    "pm_ready.py",
    "pm_status.py",
    "pm_logs.py",
    "pm_list.py",
    "pm_prune.py",
    "pm_stop.py",
    "pm_restart.py",
    "pm_doctor.py",
    "pm_shutdown.py",
)
PUBLIC_CONTRACT = {
    "launcherTypes": ["direct", "script"],
    "readinessTypes": ["process", "tcp", "http", "log"],
    "selectorKeys": ["service", "processKey"],
    "stopResultKeys": [
        "gracefulRequested",
        "gracefulSignaled",
        "forceRequired",
        "forceSignaled",
        "graceSeconds",
        "ownerEmpty",
    ],
    "errorCodes": [
        "configuration_error",
        "validation_error",
        "manager_offline",
        "state_conflict",
        "identity_mismatch",
        "not_found",
        "state_error",
        "runtime_rebuild_required",
        "supervisor_unavailable",
        "unsupported_platform",
        "invalid_request",
        "readiness_timeout",
        "probe_limit_exceeded",
    ],
    "responseEnvelope": ["ok", "operation", "data", "error", "meta"],
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wait_for_file(path: Path, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size:
            return True
        time.sleep(0.05)
    return False


def terminate_fixture(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def collect_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        result = set(value)
        for item in value.values():
            result.update(collect_keys(item))
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result.update(collect_keys(item))
        return result
    return set()


def wait_for_identities_to_exit(adapter, identities: list[dict[str, Any]], timeout: float) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(adapter.identity_matches(identity) for identity in identities):
            return True
        time.sleep(0.05)
    return not any(adapter.identity_matches(identity) for identity in identities)


def read_identities(path: Path, adapter) -> list[dict[str, Any]]:  # noqa: ANN001
    if not wait_for_file(path, 8):
        raise RuntimeError(f"fixture 未写入 identity: {path.name}")
    pids = json.loads(path.read_text(encoding="utf-8"))
    return [
        adapter.process_identity(int(pids["parentPid"])),
        adapter.process_identity(int(pids["childPid"])),
    ]


def wait_for_terminal(
    manager: ProcessManager,
    process_key: str,
    expected: set[str],
    timeout: float = 12,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    current: dict[str, Any] = {}
    while time.monotonic() < deadline:
        current = manager.status(process_key=process_key)
        if current.get("state") in expected:
            return current
        time.sleep(0.05)
    observed = {
        key: current.get(key)
        for key in ("state", "exitCode", "completion", "cleanupVerified")
        if key in current
    }
    raise RuntimeError(f"process 未进入期望终态: expected={sorted(expected)}, observed={observed}")


def inherited_environment() -> list[str]:
    return [
        name
        for name in ("SystemRoot", "WINDIR", "ComSpec", "TEMP", "TMP", "PATH", "HOME", "USERPROFILE", "LANG")
        if name in os.environ
    ]


def service_value(
    workspace: Path,
    fixture: Path,
    name: str,
    identity: Path,
    *,
    mode: str = "normal",
    readiness: dict[str, Any] | None = None,
    grace_seconds: float = 1,
    max_bytes: int = 65536,
    backups: int = 2,
    secret: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "long-running",
        "cwd": str(workspace),
        "launcher": {
            "type": "script",
            "interpreter": str(Path(sys.executable).resolve()),
            "script": str(fixture),
            "args": ["--mode", mode],
            "pathArgs": [str(identity)],
        },
        "environment": {
            "inherit": inherited_environment(),
            "set": {},
            "fromEnv": ["PM_SMOKE_SECRET"] if secret else [],
        },
        "stop": {"graceSeconds": grace_seconds},
        "readiness": readiness
        or {"type": "process", "stableSeconds": 0.1, "timeoutSeconds": 8},
        "logs": {"maxBytes": max_bytes, "backups": backups},
    }


def write_service(workspace: Path, name: str, value: dict[str, Any]) -> Path:
    path = workspace / f"{name}.json"
    write_json(path, value)
    return path


def contract_fingerprint(failures: list[str]) -> dict[str, Any]:
    help_hashes: dict[str, str] = {}
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for script in PUBLIC_SCRIPTS:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(SCRIPT_DIR / script), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
            env=environment,
        )
        if result.returncode != 0:
            failures.append(f"{script} --help exit={result.returncode}")
            continue
        normalized = result.stdout.replace("\r\n", "\n")
        help_hashes[script] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    contract = {"scripts": list(PUBLIC_SCRIPTS), **PUBLIC_CONTRACT}
    digest = hashlib.sha256(
        json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "hash": digest,
        "scriptCount": len(PUBLIC_SCRIPTS),
        "helpValidated": len(help_hashes) == len(PUBLIC_SCRIPTS),
        "helpHashes": help_hashes,
        "contract": contract,
    }


def _run_facade(arguments: list[str], timeout: float = 30) -> tuple[int, dict[str, Any]]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-B", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return 124, {
            "ok": False,
            "error": {"code": "facade_timeout", "message": f"facade 超过 {timeout} 秒未结束"},
        }
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        value = {}
    return result.returncode, value if isinstance(value, dict) else {}


def _facade_diagnostic(value: dict[str, Any]) -> dict[str, Any]:
    result = {"ok": value.get("ok")}
    error = value.get("error")
    if isinstance(error, dict):
        result["error"] = {
            key: error.get(key)
            for key in ("code", "message", "retryable")
            if key in error
        }
    return result


def manager_bootstrap_smoke(workspace: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    config = workspace / ".harness" / "process-manager" / "config.json"
    identity_path = workspace / ".harness" / "process-manager" / "control" / "manager.json"
    init_code, initialized = _run_facade(
        [str(SCRIPT_DIR / "pm_init.py"), "--workspace", str(workspace), "--pretty"]
    )
    ensure_code = status_code = stop_code = -1
    ensured: dict[str, Any] = {}
    status: dict[str, Any] = {}
    stopped: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    if init_code == 0:
        ensure_code, ensured = _run_facade(
            [str(SCRIPT_DIR / "pm_manager.py"), "ensure", "--config", str(config), "--pretty"]
        )
    try:
        if ensure_code == 0:
            status_code, status = _run_facade(
                [str(SCRIPT_DIR / "pm_manager.py"), "status", "--config", str(config), "--pretty"]
            )
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            audit = {
                "bootstrapBackend": identity.get("bootstrapBackend"),
                "bootstrapSelectionReason": identity.get("bootstrapSelectionReason"),
            }
    finally:
        if ensure_code == 0:
            stop_code, stopped = _run_facade(
                [str(SCRIPT_DIR / "pm_manager.py"), "stop", "--config", str(config), "--pretty"],
                timeout=60,
            )
    stop_data = stopped.get("data", {}) if isinstance(stopped.get("data"), dict) else {}
    cleanup = stop_data.get("cleanup", {}) if isinstance(stop_data.get("cleanup"), dict) else {}
    ok = (
        init_code == 0
        and ensure_code == 0
        and status_code == 0
        and stop_code == 0
        and initialized.get("ok") is True
        and ensured.get("ok") is True
        and status.get("ok") is True
        and stopped.get("ok") is True
        and cleanup.get("managerStopped") is True
        and cleanup.get("bootstrapCleaned") is True
        and not identity_path.exists()
    )
    return {
        "ok": ok,
        "exitCodes": {"init": init_code, "ensure": ensure_code, "status": status_code, "stop": stop_code},
        "state": ensured.get("data", {}).get("state") if isinstance(ensured.get("data"), dict) else None,
        "managerStopped": cleanup.get("managerStopped"),
        "bootstrapCleaned": cleanup.get("bootstrapCleaned"),
        "audit": audit,
        "responses": {
            "init": _facade_diagnostic(initialized),
            "ensure": _facade_diagnostic(ensured),
            "status": _facade_diagnostic(status),
            "stop": _facade_diagnostic(stopped),
        },
    }
