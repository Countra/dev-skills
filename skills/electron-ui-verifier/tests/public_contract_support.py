"""公共契约 fixture 的复制安装、CLI、HTTP 与进程生命周期支撑。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HARNESS_ROOT = (ROOT / ".harness").resolve()
SOURCE_SKILL = ROOT / "skills" / "electron-ui-verifier"
PM_SCRIPTS = ROOT / "skills" / "process-manager" / "scripts"
HOST_PYTHON_ENV = "EV_CONTRACT_HOST_PYTHON"


def guarded_harness_path(value: str | Path, label: str) -> Path:
    path = Path(value).resolve()
    if path == HARNESS_ROOT or HARNESS_ROOT not in path.parents:
        raise RuntimeError(f"{label} 必须是当前仓库 .harness 内的隔离子路径")
    return path


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_json(
    command: list[str],
    *,
    cwd: Path,
    timeout: float = 90.0,
    expected_codes: tuple[int, ...] = (0,),
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"命令未返回 JSON：rc={completed.returncode} stdout={completed.stdout[:500]} "
            f"stderr={completed.stderr[:500]}"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeError("命令 JSON 根节点不是 object")
    if completed.returncode not in expected_codes:
        raise RuntimeError(f"命令返回码不符合预期：rc={completed.returncode} command={command} result={value}")
    return value


def python_command(python_path: Path, script: Path, *arguments: str) -> list[str]:
    return [str(python_path), "-u", "-X", "utf8", "-B", str(script), *arguments]


def python_has_playwright(python_path: Path) -> bool:
    completed = subprocess.run(
        [str(python_path), "-X", "utf8", "-B", "-c", "import playwright.async_api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return completed.returncode == 0


def select_service_python(work_dir: Path) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    folder = "Scripts" if os.name == "nt" else "bin"
    candidates = []
    if os.environ.get("EV_SERVICE_PYTHON"):
        candidates.append(Path(str(os.environ["EV_SERVICE_PYTHON"])))
    candidates.extend(
        (
            Path(sys.executable),
            work_dir.parent / "fresh-env" / folder / executable,
            ROOT / ".harness" / "electron-ui-verifier" / "baseline-venv" / folder / executable,
        )
    )
    for candidate in candidates:
        if candidate.is_absolute() and candidate.exists() and python_has_playwright(candidate):
            return candidate.resolve()
    raise RuntimeError("未找到安装 locked Playwright 的 verifier Python")


def install_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


class ManagedVerifier:
    """通过 process-manager 公共 CLI 管理复制安装的 verifier。"""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = guarded_harness_path(work_dir, "--work-dir")
        self.install_root = self.work_dir / "install" / "electron-ui-verifier"
        self.workspace = self.work_dir / "workspace"
        self.manager_config = self.workspace / ".harness" / "process-manager" / "config.json"
        self.service_file = (
            self.workspace
            / ".harness"
            / "process-manager"
            / "services"
            / "electron-ui-verifier.json"
        )
        host_python = Path(os.environ.get(HOST_PYTHON_ENV, sys.executable)).resolve()
        if not host_python.is_absolute() or not host_python.exists():
            raise RuntimeError(f"公共契约宿主 Python 不存在：{host_python}")
        self.host_python = host_python
        self.python_path: Path | None = None
        self.process_key: str | None = None
        self.manager_started = False
        self.install_before: str | None = None

    def _pm(self, script: str, *arguments: str, timeout: float = 90.0) -> dict[str, Any]:
        return run_json(
            python_command(self.host_python, PM_SCRIPTS / script, *arguments),
            cwd=ROOT,
            timeout=timeout,
        )

    def reset(self) -> None:
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
        self.workspace.mkdir(parents=True)
        shutil.copytree(
            SOURCE_SKILL,
            self.install_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

    def start(self) -> dict[str, Any]:
        self.reset()
        self.python_path = select_service_python(self.work_dir)
        self.install_before = install_digest(self.install_root)
        self._pm("pm_init.py", "--workspace", str(self.workspace), "--pretty")
        initialized = run_json(
            python_command(
                self.python_path,
                self.install_root / "scripts" / "ev_init.py",
                "--workspace",
                str(self.workspace),
                "--python",
                str(self.python_path),
            ),
            cwd=self.workspace,
        )
        self._pm("pm_validate.py", "--service", str(self.service_file), "--pretty")
        self._pm("pm_manager.py", "start", "--config", str(self.manager_config), "--pretty")
        self.manager_started = True
        started = self._pm(
            "pm_start.py",
            "--config",
            str(self.manager_config),
            "--service",
            str(self.service_file),
            "--pretty",
        )
        self.process_key = str(started["data"]["processKey"])
        ready = self._pm(
            "pm_ready.py",
            "--config",
            str(self.manager_config),
            "--process-key",
            self.process_key,
            "--timeout",
            "30",
            "--pretty",
        )
        return {"initialized": initialized, "started": started.get("data"), "ready": ready.get("data")}

    def cli(
        self,
        script: str,
        *arguments: str,
        timeout: float = 90.0,
        expected_codes: tuple[int, ...] = (0,),
    ) -> dict[str, Any]:
        if self.python_path is None:
            raise RuntimeError("verifier 尚未初始化")
        command = python_command(
            self.python_path,
            self.install_root / "scripts" / script,
            "--workspace",
            str(self.workspace),
            *arguments,
        )
        return run_json(command, cwd=self.workspace, timeout=timeout, expected_codes=expected_codes)

    def http_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        state_root = self.workspace / ".harness" / "electron-ui-verifier"
        server = json.loads((state_root / "server.json").read_text(encoding="utf-8"))
        token = (state_root / "token").read_text(encoding="utf-8").strip()
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{int(server['port'])}{path}",
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"verifier HTTP 失败：{method} {path} status={exc.code} body={error}") from exc
        if not isinstance(value, dict):
            raise RuntimeError("verifier HTTP JSON 根节点不是 object")
        return value

    def stop(self) -> tuple[dict[str, Any], list[str]]:
        checks: dict[str, Any] = {}
        failures: list[str] = []
        if self.process_key:
            try:
                stopped = self._pm(
                    "pm_stop.py",
                    "--config",
                    str(self.manager_config),
                    "--process-key",
                    self.process_key,
                    "--pretty",
                )
                service_stop = stopped.get("data", {})
                checks["serviceStop"] = service_stop
                if service_stop.get("cleanupVerified") is not True:
                    failures.append("verifier service cleanupVerified 不为 true")
                if service_stop.get("stopResult", {}).get("ownerEmpty") is not True:
                    failures.append("verifier service owner 未清空")
            except Exception as exc:
                failures.append(f"service stop 失败：{exc}")
            self.process_key = None
        if self.manager_started:
            try:
                stopped = self._pm(
                    "pm_manager.py",
                    "stop",
                    "--config",
                    str(self.manager_config),
                    "--pretty",
                )
                manager_stop = stopped.get("data", {})
                checks["managerStop"] = manager_stop
                for field in ("managerStopped", "bootstrapCleaned", "ownerEmpty", "cleanupVerified"):
                    if manager_stop.get(field) is not True:
                        failures.append(f"process-manager {field} 不为 true")
            except Exception as exc:
                failures.append(f"manager stop 失败：{exc}")
            self.manager_started = False
        if self.install_root.exists() and self.install_before:
            try:
                install_after = install_digest(self.install_root)
                checks["installImmutable"] = {
                    "before": self.install_before,
                    "after": install_after,
                    "unchanged": self.install_before == install_after,
                }
                if self.install_before != install_after:
                    failures.append("公共 fixture 修改了复制安装目录")
            except OSError as exc:
                failures.append(f"复制安装完整性复核失败：{exc}")
        return checks, failures
