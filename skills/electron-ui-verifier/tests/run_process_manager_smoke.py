#!/usr/bin/env python3
"""通过 process-manager 公共入口验证 verifier service 生命周期。"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PM_SCRIPTS = ROOT / "skills" / "process-manager" / "scripts"
SERVER_SCRIPT = ROOT / "skills" / "electron-ui-verifier" / "scripts" / "ev_server.py"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_json(arguments: list[str], timeout: float = 60.0) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"process-manager 未返回 JSON：rc={completed.returncode} stdout={completed.stdout[:500]} stderr={completed.stderr[:500]}"
        ) from exc
    if completed.returncode != 0 or value.get("ok") is not True:
        raise RuntimeError(f"process-manager 命令失败：{arguments}: {value}")
    return value


def python_has_playwright(path: Path) -> bool:
    completed = subprocess.run(
        [str(path), "-X", "utf8", "-B", "-c", "import playwright.async_api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return completed.returncode == 0


def service_python(workspace: Path) -> Path:
    explicit = os.environ.get("EV_SERVICE_PYTHON")
    candidates = [Path(explicit)] if explicit else []
    candidates.append(Path(sys.executable))
    executable = "python.exe" if os.name == "nt" else "python"
    folder = "Scripts" if os.name == "nt" else "bin"
    candidates.append(workspace.parent / "fresh-env" / folder / executable)
    for candidate in candidates:
        if candidate.is_absolute() and candidate.exists() and python_has_playwright(candidate):
            return candidate
    raise RuntimeError("未找到安装 locked Playwright 的 verifier Python；请先完成 fresh-env gate")


def http_health(port: int) -> dict[str, Any]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def build_service(workspace: Path, python_path: Path) -> tuple[Path, Path]:
    state = workspace / ".harness" / "electron-ui-verifier"
    config = state / "config.json"
    token = state / "token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    write_json(state / "sessions.json", {"schemaVersion": 1, "sessions": []})
    write_json(
        config,
        {
            "host": "127.0.0.1",
            "port": 19380,
            "portRetry": {"enabled": True, "maxSwitches": 10},
            "workspaceRoot": str(workspace),
            "stateRoot": str(state),
            "tokenFile": str(token),
            "serverFile": str(state / "server.json"),
            "sessionsFile": str(state / "sessions.json"),
            "reportsDir": str(state / "reports"),
            "pendingDir": str(state / "pending"),
            "workflowsDir": str(state / "workflows"),
            "artifactsDir": str(state / "artifacts"),
            "logsDir": str(state / "logs"),
            "tmpDir": str(state / "tmp"),
            "runsDir": str(state / "runs"),
        },
    )
    service = workspace / ".harness" / "process-manager" / "services" / "electron-ui-verifier.json"
    write_json(
        service,
        {
            "name": "electron-ui-verifier",
            "kind": "long-running",
            "cwd": str(workspace),
            "launcher": {
                "type": "script",
                "interpreter": str(python_path),
                "script": str(SERVER_SCRIPT),
                "args": ["--config"],
                "pathArgs": [str(config)],
            },
            "environment": {
                "inherit": ["PATH", "HOME", "USERPROFILE", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG"],
                "set": {"PYTHONUNBUFFERED": "1"},
                "fromEnv": [],
            },
            "stop": {"graceSeconds": 8},
            "readiness": {
                "type": "log",
                "stream": "stdout",
                "pattern": "EV_READY\\s+(?P<url>http://127\\.0\\.0\\.1:\\d+/health)",
                "extract": {"urls": ["url"]},
                "scanBytes": 262144,
                "timeoutSeconds": 30,
            },
            "logs": {"maxBytes": 1048576, "backups": 1},
        },
    )
    return config, service


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    if workspace == ROOT or ROOT not in workspace.parents:
        raise SystemExit("--workspace 必须是仓库内的隔离子目录")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    manager_config = workspace / ".harness" / "process-manager" / "config.json"
    process_key = None
    manager_started = False
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        selected_python = service_python(workspace)
        run_json([str(PM_SCRIPTS / "pm_init.py"), "--workspace", str(workspace), "--pretty"])
        _, service = build_service(workspace, selected_python)
        run_json([str(PM_SCRIPTS / "pm_validate.py"), "--service", str(service), "--pretty"])
        run_json([str(PM_SCRIPTS / "pm_manager.py"), "start", "--config", str(manager_config), "--pretty"])
        manager_started = True
        manager_status = run_json(
            [str(PM_SCRIPTS / "pm_manager.py"), "status", "--config", str(manager_config), "--pretty"]
        )
        started = run_json(
            [str(PM_SCRIPTS / "pm_start.py"), "--config", str(manager_config), "--service", str(service), "--pretty"]
        )
        process_key = started["data"]["processKey"]
        ready = run_json(
            [
                str(PM_SCRIPTS / "pm_ready.py"),
                "--config",
                str(manager_config),
                "--process-key",
                process_key,
                "--timeout",
                "30",
                "--pretty",
            ]
        )
        server_state = json.loads(
            (workspace / ".harness" / "electron-ui-verifier" / "server.json").read_text(encoding="utf-8")
        )
        health = http_health(int(server_state["port"]))
        checks = {
            "manager": manager_status.get("data"),
            "ready": ready.get("data"),
            "health": health,
            "server": server_state,
            "servicePython": str(selected_python),
        }
        if ready.get("data", {}).get("ready") is not True:
            failures.append("process-manager readiness 未通过")
        if health.get("ok") is not True or health.get("backend") != "playwright-cdp":
            failures.append("verifier health/backend 契约未闭环")
        if health.get("automation", {}).get("ownerAlive") is not True:
            failures.append("automation owner 未运行")
    except Exception as exc:
        failures.append(str(exc))
    finally:
        if process_key:
            try:
                stopped = run_json(
                    [
                        str(PM_SCRIPTS / "pm_stop.py"),
                        "--config",
                        str(manager_config),
                        "--process-key",
                        process_key,
                        "--pretty",
                    ],
                    timeout=60,
                )
                checks["serviceStop"] = stopped.get("data")
                stop_data = stopped.get("data", {})
                if stop_data.get("cleanupVerified") is not True:
                    failures.append("verifier service cleanupVerified 不为 true")
                if stop_data.get("stopResult", {}).get("ownerEmpty") is not True:
                    failures.append("verifier service owner 未清空")
            except Exception as exc:
                failures.append(f"service stop 失败：{exc}")
        if manager_started:
            try:
                stopped = run_json(
                    [str(PM_SCRIPTS / "pm_manager.py"), "stop", "--config", str(manager_config), "--pretty"],
                    timeout=60,
                )
                checks["managerStop"] = stopped.get("data")
                if stopped.get("data", {}).get("managerStopped") is not True:
                    failures.append("process-manager 未停止")
            except Exception as exc:
                failures.append(f"manager stop 失败：{exc}")
    result = {"ok": not failures, "checks": checks, "failures": failures}
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
