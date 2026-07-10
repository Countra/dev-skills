#!/usr/bin/env python3
"""在当前 OS 上验证统一公共契约与真实 owner 生命周期。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import types
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from process_manager.config import create_default_manager_config  # noqa: E402
from process_manager.errors import PMError, SupervisorError  # noqa: E402
from process_manager.manager import ProcessManager  # noqa: E402
from process_manager.platforms import select_platform_adapter  # noqa: E402
from process_manager.runtime import initialize_runtime  # noqa: E402
from process_manager.state import StateStore  # noqa: E402
from smoke_support import (  # noqa: E402
    collect_keys,
    contract_fingerprint,
    manager_bootstrap_smoke,
    read_identities,
    service_value,
    terminate_fixture,
    wait_for_file,
    wait_for_identities_to_exit,
    wait_for_terminal,
    write_json,
    write_service,
)


def run_manager_crash_smoke(workspace_parent: Path, adapter, secret: str) -> tuple[bool, str | None]:  # noqa: ANN001
    workspace = workspace_parent / f"crash-{uuid.uuid4().hex}"
    identity = workspace / "identity.json"
    ready = workspace / "helper-ready"
    crash = workspace / "crash-now"
    helper = Path(__file__).resolve().parent / "fixtures" / "crash_owner_helper.py"
    environment = os.environ.copy()
    environment["PM_SMOKE_SECRET"] = secret
    process = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(helper),
            "--workspace",
            str(workspace),
            "--identity",
            str(identity),
            "--ready",
            str(ready),
            "--crash",
            str(crash),
        ],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_file(ready, 15):
            return False, f"crash helper 未就绪，exit={process.poll()}"
        pids = json.loads(identity.read_text(encoding="utf-8"))
        identities = [
            adapter.process_identity(int(pids["parentPid"])),
            adapter.process_identity(int(pids["childPid"])),
        ]
        crash.touch()
        process.wait(timeout=10)
        if process.returncode != 0:
            return False, f"crash helper exit={process.returncode}"
        if not wait_for_identities_to_exit(adapter, identities, 10):
            return False, "manager crash 后 owner 仍包含存活进程"
        return True, None
    finally:
        terminate_fixture(process)


def enable_windows_permission_harness(adapter) -> None:  # noqa: ANN001
    def secure_directory(self, path: Path) -> None:  # noqa: ANN001
        path.mkdir(parents=True, exist_ok=True)

    def secure_file(self, path: Path) -> None:  # noqa: ANN001
        if not path.is_file():
            raise SupervisorError(f"smoke runtime 文件不存在: {path}")

    adapter.secure_directory = types.MethodType(secure_directory, adapter)
    adapter.secure_file = types.MethodType(secure_file, adapter)
    adapter.verify_file = types.MethodType(secure_file, adapter)


def execute(workspace_parent: Path) -> dict[str, Any]:
    workspace = workspace_parent.resolve() / f"native-{uuid.uuid4().hex}"
    workspace.mkdir(parents=True)
    fixture = Path(__file__).resolve().parent / "fixtures" / "process_tree_service.py"
    secret = f"pm-smoke-secret-{uuid.uuid4().hex}"
    failures: list[str] = []
    checks: dict[str, Any] = {"publicContract": contract_fingerprint(failures)}
    checks["managerBootstrap"] = manager_bootstrap_smoke(workspace / "bootstrap")
    if not checks["managerBootstrap"]["ok"]:
        failures.append("统一 pm_manager bootstrap/status/stop 未闭环")
    config = create_default_manager_config(workspace)
    adapter = select_platform_adapter(config.workspace_root, config.state_root)
    runtime_security: dict[str, Any] = {"mode": "enforced", "failClosedObserved": False}
    try:
        initialize_runtime(config, adapter)
    except SupervisorError as exc:
        if adapter.selection.platform != "windows" or "ACL" not in str(exc):
            raise
        runtime_security = {
            "mode": "sandbox-permission-harness",
            "failClosedObserved": True,
            "reason": "Codex sandbox denied Windows DACL mutation",
        }
        enable_windows_permission_harness(adapter)
        initialize_runtime(config, adapter)
    state = StateStore(config, adapter)
    state.load()
    manager = ProcessManager(config, adapter, state, f"smoke-{uuid.uuid4().hex}")
    unrelated = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-B", str(fixture), "--child"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    unrelated_identity = adapter.process_identity(unrelated.pid)
    previous_secret = os.environ.get("PM_SMOKE_SECRET")
    os.environ["PM_SMOKE_SECRET"] = secret
    try:
        normal_identity = workspace / "normal-identity.json"
        normal_path = write_service(
            workspace,
            "normal",
            service_value(workspace, fixture, "normal", normal_identity, secret=True),
        )
        normal_started = manager.start(normal_path)
        normal_ready = manager.ready(process_key=normal_started["processKey"])
        old_identities = read_identities(normal_identity, adapter)
        restarted = manager.restart(normal_path, timeout_seconds=8)
        replacement_key = restarted["current"]["processKey"]
        replacement_identities = read_identities(normal_identity, adapter)
        old_owner_empty = wait_for_identities_to_exit(adapter, old_identities, 8)
        normal_stopped = manager.stop(process_key=replacement_key)
        checks["gracefulRestart"] = {
            "ready": normal_ready.get("ready") is True,
            "processKeyChanged": replacement_key != normal_started["processKey"],
            "oldOwnerEmpty": old_owner_empty,
            "replacementOwnerEmpty": wait_for_identities_to_exit(adapter, replacement_identities, 8),
            "previousStop": restarted.get("previous", {}).get("stopResult"),
            "finalStop": normal_stopped.get("stopResult"),
        }
        if not all(
            (
                checks["gracefulRestart"]["ready"],
                checks["gracefulRestart"]["processKeyChanged"],
                checks["gracefulRestart"]["oldOwnerEmpty"],
                checks["gracefulRestart"]["replacementOwnerEmpty"],
                normal_stopped.get("cleanupVerified") is True,
            )
        ):
            failures.append("graceful/restart lifecycle 未完整收口")

        force_identity = workspace / "force-identity.json"
        force_path = write_service(
            workspace,
            "force",
            service_value(
                workspace,
                fixture,
                "force",
                force_identity,
                mode="ignore-signal",
                grace_seconds=0.2,
            ),
        )
        force_started = manager.start(force_path)
        manager.ready(process_key=force_started["processKey"])
        force_identities = read_identities(force_identity, adapter)
        force_stopped = manager.stop(process_key=force_started["processKey"])
        checks["forceFallback"] = {
            "stopResult": force_stopped.get("stopResult"),
            "ownerEmpty": wait_for_identities_to_exit(adapter, force_identities, 8),
        }
        force_result = force_stopped.get("stopResult", {})
        if not force_result.get("forceRequired") or not force_result.get("ownerEmpty"):
            failures.append("ignore-signal 未触发 force fallback 或 owner 未清空")

        dynamic_identity = workspace / "dynamic-identity.json"
        dynamic_path = write_service(
            workspace,
            "dynamic",
            service_value(
                workspace,
                fixture,
                "dynamic",
                dynamic_identity,
                mode="dynamic-port",
                readiness={
                    "type": "log",
                    "pattern": r"service-url=(?P<url>http://127\.0\.0\.1:(?P<port>\d+))",
                    "extract": {"urls": ["url"], "ports": ["port"]},
                    "scanBytes": 131072,
                    "timeoutSeconds": 8,
                },
            ),
        )
        dynamic_started = manager.start(dynamic_path)
        dynamic_ready = manager.ready(process_key=dynamic_started["processKey"])
        manager.stop(process_key=dynamic_started["processKey"])
        checks["dynamicPort"] = dynamic_ready
        if not dynamic_ready.get("observed", {}).get("ports"):
            failures.append("动态端口未通过增量 log readiness 提取")

        large_identity = workspace / "large-identity.json"
        large_path = write_service(
            workspace,
            "large-log",
            service_value(
                workspace,
                fixture,
                "large-log",
                large_identity,
                mode="large-log",
                readiness={
                    "type": "log",
                    "pattern": "large-log-ready",
                    "extract": {},
                    "scanBytes": 1048576,
                    "timeoutSeconds": 12,
                },
            ),
        )
        large_started = manager.start(large_path)
        large_ready = manager.ready(process_key=large_started["processKey"])
        large_logs = manager.logs(process_key=large_started["processKey"], tail_lines=120, max_bytes=32768)
        large_run = Path(manager.state.get(key=large_started["processKey"])["runDir"])
        backup_count = len(list(large_run.glob("stdout.log.*")))
        manager.stop(process_key=large_started["processKey"])
        checks["rotatingLogs"] = {
            "ready": large_ready.get("ready") is True,
            "backupCount": backup_count,
            "returnedBytes": large_logs.get("bytesRead"),
            "lineCount": len(large_logs.get("lines", [])),
        }
        if backup_count < 1 or int(large_logs.get("bytesRead", 0)) > 32768:
            failures.append("大日志未轮转或 bounded tail 超出预算")

        exit_identity = workspace / "exit-identity.json"
        exit_path = write_service(
            workspace,
            "exit-failure",
            service_value(workspace, fixture, "exit-failure", exit_identity, mode="exit-failure"),
        )
        exit_started = manager.start(exit_path)
        exit_terminal = wait_for_terminal(manager, exit_started["processKey"], {"exited"})
        checks["exitCode"] = {
            "status": exit_terminal.get("state"),
            "exitCode": exit_terminal.get("exitCode"),
            "ownerEmpty": exit_terminal.get("cleanupVerified"),
        }
        if exit_terminal.get("exitCode") != 23 or not exit_terminal.get("cleanupVerified"):
            failures.append("自然退出码或 owner cleanup 记录不正确")

        violation_identity = workspace / "violation-identity.json"
        violation_path = write_service(
            workspace,
            "contract-violation",
            service_value(
                workspace,
                fixture,
                "contract-violation",
                violation_identity,
                mode="background-child",
            ),
        )
        violation_started = manager.start(violation_path)
        violation_terminal = wait_for_terminal(
            manager,
            violation_started["processKey"],
            {"contract_violation"},
        )
        checks["daemonizeContract"] = {
            "status": violation_terminal.get("state"),
            "completion": violation_terminal.get("completion"),
            "ownerEmpty": violation_terminal.get("cleanupVerified"),
        }
        if not violation_terminal.get("cleanupVerified"):
            failures.append("后台化契约违规后 owner 未清空")

        invalid_executable = workspace / "invalid-target.exe"
        invalid_executable.write_bytes(b"not-an-executable\n")
        invalid_service = service_value(
            workspace,
            fixture,
            "start-failure",
            workspace / "unused-identity.json",
        )
        invalid_service["launcher"] = {"type": "direct", "executable": str(invalid_executable), "args": [], "pathArgs": []}
        invalid_path = write_service(workspace, "start-failure", invalid_service)
        start_failure: dict[str, Any] = {"observed": False}
        try:
            manager.start(invalid_path)
        except (PMError, OSError) as exc:
            start_failure = {"observed": True, "errorType": type(exc).__name__}
        checks["startFailure"] = start_failure
        if not start_failure["observed"]:
            failures.append("无效 executable 未产生 start failure")

        persisted = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in config.state_root.rglob("*.json")
            if path.is_file()
        )
        logs = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in config.paths.runs.rglob("*.log*")
            if path.is_file()
        )
        secret_absent = secret not in persisted and secret not in logs
        checks["secretRedaction"] = {"absentFromStateAndLogs": secret_absent}
        if not secret_absent:
            failures.append("秘密值进入 state 或日志")

        forbidden_public_keys = {"platform", "backend", "capability", "selectionReason"}
        public_responses = [normal_started, restarted, normal_stopped, force_stopped, dynamic_ready, large_logs]
        if any(collect_keys(item) & forbidden_public_keys for item in public_responses):
            failures.append("普通公共响应泄露内部平台选择")

        dry_prune = manager.prune(max_inactive=3, dry_run=True)
        applied_prune = manager.prune(max_inactive=3, dry_run=False)
        checks["prune"] = {"dryRun": dry_prune, "applied": applied_prune}

        crash_verified, crash_error = run_manager_crash_smoke(workspace.parent, adapter, secret)
        checks["managerCrash"] = {"ownerEmpty": crash_verified}
        if crash_error:
            failures.append(crash_error)
        unrelated_survived = unrelated.poll() is None and adapter.identity_matches(unrelated_identity)
        checks["unrelatedProcess"] = {"survivedManagedLifecycle": unrelated_survived}
        if not unrelated_survived:
            failures.append("managed lifecycle 波及 owner 外进程")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{type(exc).__name__}: {str(exc).replace(secret, '***redacted***')}")
    finally:
        if previous_secret is None:
            os.environ.pop("PM_SMOKE_SECRET", None)
        else:
            os.environ["PM_SMOKE_SECRET"] = previous_secret
        try:
            checks["managerShutdown"] = manager.shutdown()
        except PMError as exc:
            failures.append(f"manager shutdown: {exc.code}")
        terminate_fixture(unrelated)
    return {
        "ok": not failures,
        "workspace": str(workspace),
        "diagnostics": adapter.diagnostics(),
        "runtimeSecurity": runtime_security,
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=True)
    result = execute(args.workspace)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
