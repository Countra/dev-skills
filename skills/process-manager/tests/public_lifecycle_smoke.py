"""通过公共 facade 验证 manager、session 与 service 生命周期。"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from process_manager.config import load_manager_config
from process_manager.platforms import select_platform_adapter
from process_manager.state import StateStore
from smoke_support import (
    _facade_diagnostic,
    _run_facade,
    remove_tree,
    service_value,
    write_service,
)


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "process_tree_service.py"

class PublicLifecycleSmoke:
    """用真实公共命令执行可恢复且可清场的生命周期验证。"""

    def __init__(self, workspace_parent: Path) -> None:
        self.workspace = workspace_parent.resolve() / f"public-{uuid.uuid4().hex}"
        self.workspace.mkdir(parents=True)
        self.config_path = self.workspace / ".harness" / "process-manager" / "config.json"
        self.checks: dict[str, Any] = {}
        self.failures: list[str] = []
        self.open_sessions: list[str] = []
        self.service_path: Path | None = None
        self.persistent_path: Path | None = None

    @staticmethod
    def data(value: dict[str, Any]) -> dict[str, Any]:
        current = value.get("data")
        return current if isinstance(current, dict) else {}

    def invoke(
        self,
        script: str,
        *arguments: str,
        timeout: float = 60,
    ) -> tuple[int, dict[str, Any]]:
        return _run_facade([str(SCRIPT_DIR / script), *arguments], timeout=timeout)

    def prepare_services(self) -> None:
        self.service_path = write_service(
            self.workspace,
            "public-session",
            service_value(
                self.workspace,
                FIXTURE,
                "public-session",
                self.workspace / "public-session-identity.json",
            ),
        )
        self.persistent_path = write_service(
            self.workspace,
            "public-persistent",
            service_value(
                self.workspace,
                FIXTURE,
                "public-persistent",
                self.workspace / "public-persistent-identity.json",
            ),
        )

    def verify_context_and_ensure(self) -> None:
        code, response = self.invoke(
            "pm_manager.py",
            "status",
            "--workspace",
            str(self.workspace),
            "--pretty",
        )
        current = self.data(response)
        runtime_created = (self.workspace / ".harness").exists()
        self.checks["uninitializedStatus"] = {
            "exitCode": code,
            "state": current.get("state"),
            "initialized": current.get("initialized"),
            "recommendedAction": current.get("recommendedAction"),
            "runtimeCreated": runtime_created,
        }
        if (
            code != 0
            or current.get("state") != "absent"
            or current.get("initialized") is not False
            or current.get("recommendedAction") != "init"
            or runtime_created
        ):
            self.failures.append("未初始化 public status 未返回 absent/init 或发生写入")

        init_code, initialized = self.invoke(
            "pm_init.py",
            "--workspace",
            str(self.workspace),
            "--pretty",
        )
        status_code, status = self.invoke(
            "pm_manager.py",
            "status",
            "--config",
            str(self.config_path),
            "--pretty",
        )
        absent = self.data(status)
        self.checks["initializedAbsent"] = {
            "initExitCode": init_code,
            "statusExitCode": status_code,
            "state": absent.get("state"),
            "recommendedAction": absent.get("recommendedAction"),
        }
        if (
            init_code != 0
            or initialized.get("ok") is not True
            or status_code != 0
            or absent.get("state") != "absent"
            or absent.get("recommendedAction") != "ensure"
        ):
            self.failures.append("初始化后的 public status 未返回 absent/ensure")

        command = [
            str(SCRIPT_DIR / "pm_manager.py"),
            "ensure",
            "--config",
            str(self.config_path),
            "--pretty",
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: _run_facade(command), range(2)))
        instances = {
            self.data(value).get("manager", {}).get("managerInstanceId")
            for result_code, value in results
            if result_code == 0 and isinstance(self.data(value).get("manager"), dict)
        }
        self.checks["concurrentEnsure"] = {
            "exitCodes": [result_code for result_code, _ in results],
            "instanceIds": sorted(str(item) for item in instances if item),
        }
        if any(result_code != 0 for result_code, _ in results) or len(instances) != 1:
            self.failures.append("并发 ensure 未收敛到单一 ready manager")

    def open_session(self, holder: str) -> str:
        code, response = self.invoke(
            "pm_session.py",
            "open",
            "--config",
            str(self.config_path),
            "--kind",
            "validation",
            "--holder",
            holder,
            "--ttl-seconds",
            "300",
            "--pretty",
        )
        session_id = self.data(response).get("sessionId")
        if code != 0 or not isinstance(session_id, str):
            raise RuntimeError(f"{holder} session open 失败")
        self.open_sessions.append(session_id)
        return session_id

    def verify_service_lifecycle(self) -> None:
        assert self.service_path is not None
        assert self.persistent_path is not None
        validate_code, validated = self.invoke(
            "pm_validate.py",
            "--config",
            str(self.config_path),
            "--service",
            str(self.service_path),
            "--pretty",
        )
        self.checks["validation"] = {
            "exitCode": validate_code,
            **_facade_diagnostic(validated),
        }
        if validate_code != 0 or validated.get("ok") is not True:
            self.failures.append("public service validation 失败")

        first = self.open_session("public-session-a")
        second = self.open_session("public-session-b")
        self.checks["sessionOpen"] = {"sessionIds": [first, second]}
        start_code, started = self.invoke(
            "pm_start.py",
            "--config",
            str(self.config_path),
            "--service",
            str(self.service_path),
            "--session-id",
            first,
            "--pretty",
        )
        process_key = self.data(started).get("processKey")
        ready_code, ready = self.invoke(
            "pm_ready.py",
            "--config",
            str(self.config_path),
            "--process-key",
            str(process_key),
            "--pretty",
            timeout=30,
        )
        restart_code, restarted = self.invoke(
            "pm_restart.py",
            "--config",
            str(self.config_path),
            "--service",
            str(self.service_path),
            "--timeout",
            "8",
            "--pretty",
            timeout=45,
        )
        restart = self.data(restarted)
        self.checks["sessionService"] = {
            "startExitCode": start_code,
            "readyExitCode": ready_code,
            "restartExitCode": restart_code,
            "processKey": process_key,
            "replacementProcessKey": restart.get("current", {}).get("processKey"),
            "previousCleanupVerified": restart.get("previous", {}).get("cleanupVerified"),
        }
        if (
            start_code != 0
            or not isinstance(process_key, str)
            or ready_code != 0
            or self.data(ready).get("ready") is not True
            or restart_code != 0
            or restart.get("previous", {}).get("cleanupVerified") is not True
        ):
            self.failures.append("session-owned public start/ready/restart 未闭环")

        persistent_code, persistent = self.invoke(
            "pm_start.py",
            "--config",
            str(self.config_path),
            "--service",
            str(self.persistent_path),
            "--persistent",
            "--pretty",
        )
        persistent_key = self.data(persistent).get("processKey")
        stop_code, stopped = self.invoke(
            "pm_stop.py",
            "--config",
            str(self.config_path),
            "--process-key",
            str(persistent_key),
            "--pretty",
            timeout=30,
        )
        stop = self.data(stopped)
        self.checks["persistentService"] = {
            "startExitCode": persistent_code,
            "stopExitCode": stop_code,
            "cleanupVerified": stop.get("cleanupVerified"),
            "ownerEmpty": stop.get("stopResult", {}).get("ownerEmpty"),
        }
        if (
            persistent_code != 0
            or not isinstance(persistent_key, str)
            or stop_code != 0
            or stop.get("cleanupVerified") is not True
            or stop.get("stopResult", {}).get("ownerEmpty") is not True
        ):
            self.failures.append("persistent public start/stop 未闭环")

        status_code, status = self.invoke(
            "pm_manager.py",
            "status",
            "--config",
            str(self.config_path),
            "--pretty",
        )
        resources = self.data(status).get("resources")
        self.checks["resourceSummary"] = resources
        fields = {"usedBytes", "reservedBytes", "limitBytes", "overBudget", "cleanupPending"}
        if status_code != 0 or not isinstance(resources, dict) or not fields <= set(resources):
            self.failures.append("public status 缺少 resource summary")

    def close_validation_sessions(self) -> None:
        first, second = list(self.open_sessions)
        first_code, first_response = self.invoke(
            "pm_session.py",
            "close",
            "--config",
            str(self.config_path),
            "--session-id",
            first,
            "--stop-manager-if-idle",
            "--pretty",
            timeout=45,
        )
        first_data = self.data(first_response)
        self.checks["firstSessionClose"] = first_data
        if first_code == 0:
            self.open_sessions.remove(first)
        if (
            first_code != 0
            or first_data.get("sessionId") != first
            or first_data.get("cleanup", {}).get("cleanupVerified") is not True
            or first_data.get("managerRetained") is not True
            or first_data.get("idleStop", {}).get("state") != "precondition_changed"
        ):
            self.failures.append("session close/idle-stop 竞态未安全保留 manager")

        second_code, second_response = self.invoke(
            "pm_session.py",
            "close",
            "--config",
            str(self.config_path),
            "--session-id",
            second,
            "--stop-manager-if-idle",
            "--pretty",
            timeout=45,
        )
        second_data = self.data(second_response)
        self.checks["secondSessionClose"] = second_data
        if second_code == 0:
            self.open_sessions.remove(second)
        cleanup = second_data.get("idleStop", {}).get("cleanup", {})
        if (
            second_code != 0
            or second_data.get("sessionId") != second
            or second_data.get("cleanup", {}).get("cleanupVerified") is not True
            or second_data.get("managerRetained") is not False
            or cleanup.get("ownersEmpty") is not True
            or cleanup.get("managerStopped") is not True
            or cleanup.get("bootstrapCleaned") is not True
        ):
            self.failures.append("最后 session close 未收口 idle manager")

    def verify_manager_restart(self) -> None:
        ensure_code, _ = self.invoke(
            "pm_manager.py",
            "ensure",
            "--config",
            str(self.config_path),
            "--pretty",
        )
        session_id = self.open_session("public-restart")
        assert self.service_path is not None
        start_code, started = self.invoke(
            "pm_start.py",
            "--config",
            str(self.config_path),
            "--service",
            str(self.service_path),
            "--session-id",
            session_id,
            "--pretty",
        )
        process_key = self.data(started).get("processKey")
        rejected_code, rejected = self.invoke(
            "pm_manager.py",
            "restart",
            "--config",
            str(self.config_path),
            "--pretty",
        )
        confirmed_code, confirmed = self.invoke(
            "pm_manager.py",
            "restart",
            "--config",
            str(self.config_path),
            "--confirm-stop-owned-runs",
            "--timeout-seconds",
            "30",
            "--pretty",
            timeout=90,
        )
        confirmed_data = self.data(confirmed)
        if confirmed_code == 0:
            self.open_sessions.remove(session_id)
        self.checks["managerRestart"] = {
            "ensureExitCode": ensure_code,
            "startExitCode": start_code,
            "unconfirmedExitCode": rejected_code,
            "unconfirmedError": rejected.get("error", {}).get("code"),
            "confirmedExitCode": confirmed_code,
            "servicesRestored": confirmed_data.get("servicesRestored"),
            "stoppedRunKeys": confirmed_data.get("stoppedRunKeys"),
            "sessionsCleanupVerified": confirmed_data.get("sessions", {}).get("cleanupVerified"),
        }
        if (
            ensure_code != 0
            or start_code != 0
            or rejected_code != 4
            or rejected.get("error", {}).get("code") != "restart_confirmation_required"
            or confirmed_code != 0
            or confirmed_data.get("servicesRestored") is not False
            or process_key not in confirmed_data.get("stoppedRunKeys", [])
            or confirmed_data.get("sessions", {}).get("cleanupVerified") is not True
        ):
            self.failures.append("manager restart 确认边界未闭环")

    def final_cleanup(self) -> None:
        for session_id in list(self.open_sessions):
            try:
                code, response = self.invoke(
                    "pm_session.py",
                    "close",
                    "--config",
                    str(self.config_path),
                    "--session-id",
                    session_id,
                    "--pretty",
                    timeout=45,
                )
                if code != 0:
                    error = response.get("error", {}).get("code")
                    self.failures.append(f"public lifecycle final session close 失败: {error}")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"public lifecycle final session close 异常: {exc}")
        if self.config_path.exists():
            try:
                code, response = self.invoke(
                    "pm_manager.py",
                    "stop",
                    "--config",
                    str(self.config_path),
                    "--confirm-stop-owned-runs",
                    "--pretty",
                    timeout=60,
                )
                self.checks["finalManagerStop"] = {
                    "exitCode": code,
                    **_facade_diagnostic(response),
                }
                if code != 0:
                    self.failures.append("public lifecycle final manager stop 失败")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"public lifecycle final manager stop 异常: {exc}")
        if self.config_path.exists():
            try:
                code, response = self.invoke(
                    "pm_manager.py",
                    "status",
                    "--config",
                    str(self.config_path),
                    "--pretty",
                )
                current = self.data(response)
                config = load_manager_config(self.config_path)
                adapter = select_platform_adapter(config.workspace_root, config.state_root)
                summary = StateStore(config, adapter).work_summary()
                self.checks["finalAudit"] = {
                    "statusExitCode": code,
                    "state": current.get("state"),
                    "activeRunKeys": summary["activeRunKeys"],
                    "activeSessionIds": summary["activeSessionIds"],
                    "identityPresent": config.paths.manager.exists(),
                    "bootstrapResidue": current.get("evidence", {}).get("bootstrapResidue"),
                }
                if (
                    code != 0
                    or current.get("state") != "absent"
                    or summary["activeRunKeys"]
                    or summary["activeSessionIds"]
                    or config.paths.manager.exists()
                    or current.get("evidence", {}).get("bootstrapResidue") is not False
                ):
                    self.failures.append("public lifecycle final audit 仍有 active residue")
            except Exception as exc:  # noqa: BLE001
                self.failures.append(f"public lifecycle final audit 异常: {exc}")
        try:
            remove_tree(self.workspace)
            self.checks["workspaceRemoved"] = not self.workspace.exists()
        except OSError as exc:
            self.checks["workspaceRemoved"] = False
            self.failures.append(f"public lifecycle workspace 清理失败: {exc}")

    def run(self) -> dict[str, Any]:
        try:
            self.verify_context_and_ensure()
            self.prepare_services()
            self.verify_service_lifecycle()
            self.close_validation_sessions()
            self.verify_manager_restart()
        except Exception as exc:  # noqa: BLE001
            self.failures.append(f"public lifecycle exception: {type(exc).__name__}: {exc}")
        finally:
            self.final_cleanup()
        return {
            "ok": not self.failures,
            "workspace": str(self.workspace),
            "checks": self.checks,
            "failures": self.failures,
        }

def execute_public_lifecycle(workspace_parent: Path) -> dict[str, Any]:
    return PublicLifecycleSmoke(workspace_parent).run()
