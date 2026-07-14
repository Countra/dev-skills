#!/usr/bin/env python3
"""初始化 Electron verifier server 的本机运行环境。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ev_common import (
    EVError,
    config_to_data,
    discover_workspace_root,
    ensure_runtime_dirs,
    ensure_token,
    normalize_port,
    paths_for_workspace,
    print_json,
    require_absolute_path,
    write_environment,
    write_json,
)
from electron_verifier.security import secure_mode
from electron_verifier.errors import VerifierError
from electron_verifier.knowledge_reset import KnowledgeReset
from electron_verifier.paths import SkillPaths, inspect_skill_install, require_skill_install, skill_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="初始化 electron-ui-verifier server runtime。")
    parser.add_argument("--workspace", help="workspace 根目录绝对路径；未指定时使用当前目录")
    parser.add_argument("--python", dest="python_path", help="verifier server 使用的 Python 解释器绝对路径")
    parser.add_argument("--port", type=int, help="verifier server 初始端口，默认 18180")
    parser.add_argument("--reset-knowledge", action="store_true", help="预览或执行 fingerprint-gated knowledge direct reset")
    parser.add_argument("--confirm", help="与 reset preview 完全一致的 confirmation fingerprint")
    return parser


def service_config(
    workspace_root: Path,
    python_path: Path,
    config_file: Path,
    port: int,
    install: SkillPaths | None = None,
) -> dict[str, Any]:
    install = install or skill_paths()
    server_script = install.server_script
    if not server_script.exists():
        raise EVError(f"ev_server.py 不存在：{server_script}")
    return {
        "name": "electron-ui-verifier",
        "kind": "long-running",
        "cwd": str(workspace_root),
        "launcher": {
            "type": "script",
            "interpreter": str(python_path),
            "script": str(server_script),
            "args": ["--config"],
            "pathArgs": [str(config_file)],
        },
        "environment": {
            "inherit": ["PATH", "HOME", "USERPROFILE", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG"],
            "set": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"},
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
        "logs": {"maxBytes": 10485760, "backups": 3},
    }


def format_dependency_error(result: dict[str, Any], stderr: str = "") -> str:
    messages = []
    python_failure = result.get("pythonFailure")
    if isinstance(python_failure, dict):
        messages.append(
            f"Python 版本不满足要求：当前 {python_failure.get('actual')}，需要 {python_failure.get('required')}"
        )
    missing = result.get("missing")
    if isinstance(missing, list):
        for item in missing:
            if isinstance(item, dict):
                requirement = item.get("requirement") or item.get("package") or "unknown"
                reason = item.get("reason") or item.get("detail") or "依赖检查失败"
                messages.append(f"{requirement}: {reason}")
    if result.get("error"):
        messages.append(str(result["error"]))
    if stderr.strip():
        messages.append(f"stderr: {stderr.strip()}")
    install_command = result.get("installCommand")
    if install_command:
        messages.append(f"安装命令：{install_command}")
    return "verifier Python 环境依赖不完整，已阻塞初始化。缺失或不满足项：" + "；".join(messages)


def check_python_environment(
    python_path: Path,
    workspace_root: Path,
    install: SkillPaths | None = None,
) -> dict[str, Any]:
    install = install or skill_paths()
    check_script = install.check_script
    requirements_file = install.requirements_file
    if not check_script.exists():
        raise EVError(f"依赖检查脚本不存在：{check_script}")
    if not requirements_file.exists():
        raise EVError(f"requirements 文件不存在：{requirements_file}")
    try:
        completed = subprocess.run(
            [str(python_path), "-B", str(check_script), "--requirements", str(requirements_file), "--json"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EVError(f"verifier Python 环境依赖检查超时：{python_path}") from exc
    except OSError as exc:
        raise EVError(f"无法执行 verifier Python 依赖检查：{python_path}: {exc}") from exc
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EVError(f"verifier Python 依赖检查未返回 JSON：{completed.stdout[:500]} {completed.stderr[:500]}") from exc
    if completed.returncode != 0 or result.get("ok") is not True:
        raise EVError(format_dependency_error(result, completed.stderr))
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    install = skill_paths()
    install_check = inspect_skill_install(install)
    workspace_root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    try:
        workspace_root = discover_workspace_root(args.workspace)
        install_check = require_skill_install(install)
        paths = paths_for_workspace(workspace_root)
        reset = KnowledgeReset(paths.state_root)
        if args.confirm and not args.reset_knowledge:
            raise EVError("--confirm 只能与 --reset-knowledge 一起使用")
        if args.reset_knowledge and not args.confirm:
            print_json(
                {
                    "ok": False,
                    "code": "knowledge_reset_confirmation_required",
                    "error": "knowledge reset 需要再次传入完全一致的 --confirm fingerprint",
                    "preview": reset.preview(),
                }
            )
            return 2
        python_path = (
            require_absolute_path(args.python_path, "--python", must_exist=True)
            if args.python_path
            else Path(sys.executable).resolve()
        )
        if not python_path.exists():
            raise EVError(f"python does not exist: {python_path}")
        dependency_check = check_python_environment(python_path, workspace_root, install)
        port = normalize_port(args.port)
        knowledge = reset.apply(args.confirm) if args.reset_knowledge else reset.ensure()
        ensure_runtime_dirs(paths)
        environment = write_environment(paths, python_path=python_path, port=port, skill_root=install.root)
        ensure_token(paths)
        secure_mode(paths.state_root, 0o700)
        secure_mode(paths.token_file, 0o600)
        config = config_to_data(paths, environment)
        config["runsDir"] = str(paths.state_root / "runs")
        write_json(paths.config_file, config)
        write_json(
            paths.server_file,
            {
                "status": "initialized",
                "host": "127.0.0.1",
                "port": port,
                "processManagerService": "electron-ui-verifier",
            },
        )
        if not paths.sessions_file.exists():
            write_json(paths.sessions_file, {"schemaVersion": 1, "sessions": []})
        write_json(paths.service_file, service_config(workspace_root, python_path, paths.config_file, port, install))
        print_json(
            {
                "ok": True,
                "environment": str(paths.environment_file),
                "config": str(paths.config_file),
                "service": str(paths.service_file),
                "roots": {"skill": str(install.root), "workspace": str(workspace_root)},
                "installCheck": install_check,
                "python": str(python_path),
                "dependencyCheck": dependency_check,
                "knowledge": knowledge,
                "port": port,
            }
        )
        return 0
    except (EVError, VerifierError) as exc:
        code = exc.code if isinstance(exc, VerifierError) else "init_failed"
        details = exc.details if isinstance(exc, VerifierError) else None
        result = {
            "ok": False,
            "code": code,
            "error": str(exc),
            "roots": {"skill": str(install.root), "workspace": str(workspace_root)},
            "installCheck": install_check,
        }
        if details:
            result["details"] = details
        print_json(result)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
