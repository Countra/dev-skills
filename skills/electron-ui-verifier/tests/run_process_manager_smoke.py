#!/usr/bin/env python3
"""通过 process-manager 公共入口验证 verifier service 生命周期。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HARNESS_ROOT = (ROOT / ".harness").resolve()
PM_SCRIPTS = ROOT / "skills" / "process-manager" / "scripts"
SOURCE_SKILL = ROOT / "skills" / "electron-ui-verifier"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_json(
    arguments: list[str],
    timeout: float = 60.0,
    *,
    python_path: Path | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    completed = subprocess.run(
        [str(python_path or Path(sys.executable)), "-X", "utf8", "-B", *arguments],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"命令未返回 JSON：rc={completed.returncode} stdout={completed.stdout[:500]} stderr={completed.stderr[:500]}"
        ) from exc
    if completed.returncode != 0 or value.get("ok") is not True:
        raise RuntimeError(f"命令失败：{arguments}: {value}")
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
    candidates.append(ROOT / ".harness" / "electron-ui-verifier" / "baseline-venv" / folder / executable)
    for candidate in candidates:
        if candidate.is_absolute() and candidate.exists() and python_has_playwright(candidate):
            return candidate
    raise RuntimeError("未找到安装 locked Playwright 的 verifier Python；请先完成 fresh-env gate")


def http_health(port: int) -> dict[str, Any]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def install_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def copy_skill(install_root: Path) -> None:
    if install_root == ROOT or ROOT not in install_root.parents:
        raise RuntimeError("复制安装目录必须位于当前仓库内")
    if install_root.exists():
        shutil.rmtree(install_root)
    shutil.copytree(
        SOURCE_SKILL,
        install_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def initialize_service(workspace: Path, install_root: Path, python_path: Path) -> tuple[dict[str, Any], Path]:
    initialized = run_json(
        [
            str(install_root / "scripts" / "ev_init.py"),
            "--workspace",
            str(workspace),
            "--python",
            str(python_path),
        ],
        timeout=90,
        python_path=python_path,
        cwd=workspace,
    )
    service = Path(str(initialized["service"])).resolve()
    expected = workspace / ".harness" / "process-manager" / "services" / "electron-ui-verifier.json"
    if service != expected.resolve():
        raise RuntimeError(f"ev_init 返回了非预期服务路径：{service}")
    return initialized, service


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    output = Path(args.output).resolve()
    if workspace == HARNESS_ROOT or HARNESS_ROOT not in workspace.parents:
        raise SystemExit("--workspace 必须是仓库 .harness 内的隔离子目录")
    install_root = workspace.parent / f"{workspace.name}-skill-install"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    manager_config = workspace / ".harness" / "process-manager" / "config.json"
    process_key = None
    manager_started = False
    install_before: str | None = None
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        selected_python = service_python(workspace)
        copy_skill(install_root)
        install_before = install_digest(install_root)
        run_json([str(PM_SCRIPTS / "pm_init.py"), "--workspace", str(workspace), "--pretty"])
        initialized, service = initialize_service(workspace, install_root, selected_python)
        service_data = json.loads(service.read_text(encoding="utf-8"))
        expected_server = (install_root / "scripts" / "ev_server.py").resolve()
        launcher_server = Path(str(service_data.get("launcher", {}).get("script", ""))).resolve()
        service_cwd = Path(str(service_data.get("cwd", ""))).resolve()
        service_environment = service_data.get("environment", {}).get("set", {})
        if launcher_server != expected_server:
            failures.append("生成的 service 未指向复制安装内的 ev_server.py")
        if service_cwd != workspace:
            failures.append("生成的 service cwd 未指向独立 workspace")
        if initialized.get("roots", {}).get("skill") != str(install_root.resolve()):
            failures.append("ev_init 未报告复制安装根")
        if initialized.get("installCheck", {}).get("ok") is not True:
            failures.append("复制安装完整性检查未通过")
        if service_environment.get("PYTHONDONTWRITEBYTECODE") != "1":
            failures.append("生成的 service 未禁用安装目录字节码写入")
        readiness_timeout = float(service_data["readiness"]["timeoutSeconds"])
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
                "--pretty",
            ],
            timeout=readiness_timeout + 15,
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
            "roots": initialized.get("roots"),
            "installCheck": initialized.get("installCheck"),
            "service": {
                "path": str(service),
                "cwd": str(service_cwd),
                "serverScript": str(launcher_server),
                "environment": service_environment,
            },
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
                manager_stop = stopped.get("data", {})
                if manager_stop.get("managerStopped") is not True:
                    failures.append("process-manager 未停止")
                if manager_stop.get("bootstrapCleaned") is not True:
                    failures.append("process-manager bootstrap 未清理")
                if manager_stop.get("ownerEmpty") is not True:
                    failures.append("process-manager owner 未清空")
                if manager_stop.get("cleanupVerified") is not True:
                    failures.append("process-manager cleanupVerified 不为 true")
            except Exception as exc:
                failures.append(f"manager stop 失败：{exc}")
        if install_root.exists() and install_before:
            try:
                install_after = install_digest(install_root)
                checks["installImmutable"] = {
                    "before": install_before,
                    "after": install_after,
                    "unchanged": install_before == install_after,
                }
                if install_before != install_after:
                    failures.append("verifier 生命周期修改了复制安装目录")
            except OSError as exc:
                failures.append(f"复制安装目录摘要复查失败：{exc}")
    result = {"ok": not failures, "checks": checks, "failures": failures}
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
