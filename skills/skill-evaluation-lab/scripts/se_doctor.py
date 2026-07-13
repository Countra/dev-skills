#!/usr/bin/env python3
"""检查离线运行环境和可选 Codex CLI。"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.codex_runner import probe_codex
from skill_evaluation_lab.errors import DependencyError
from skill_evaluation_lab.output import render_json
from skill_evaluation_lab.security import build_child_env


def _version(command: str) -> dict[str, object]:
    executable = shutil.which(command)
    if not executable:
        return {"available": False, "path": None, "version": None}
    try:
        result = subprocess.run(
            [executable, "--version"],
            env=build_child_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "path": executable, "version": None}
    output = (result.stdout or result.stderr).strip().splitlines()
    return {"available": result.returncode == 0, "path": executable, "version": output[0] if output else None}


def collect_diagnostics(
    *,
    require_live: bool,
    probe_skill: Path | None,
    workspace: Path,
) -> dict[str, object]:
    """收集稳定环境证据；可选 probe 只检查 CLI，不调用模型。"""
    data: dict[str, object] = {
        "python": {"version": platform.python_version(), "supported": sys.version_info >= (3, 12)},
        "platform": {"system": platform.system(), "release": platform.release()},
        "git": _version("git"),
        "codex": _version("codex"),
        "live_model_called": False,
    }
    if not data["python"]["supported"]:
        raise DependencyError("需要 Python 3.12 或更高版本")
    if not data["git"]["available"]:
        raise DependencyError("缺少 Git")
    if (require_live or probe_skill is not None) and not data["codex"]["available"]:
        raise DependencyError("live capability 检查需要 Codex CLI")
    if probe_skill is not None:
        data["capability_probe"] = probe_codex(
            probe_skill.resolve(),
            workspace=workspace.resolve(),
        )
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Skill Evaluation Lab 运行环境")
    parser.add_argument("--live", action="store_true", help="要求 Codex CLI 可用；不会调用模型")
    parser.add_argument("--probe-skill", type=Path, help="可选待检查 skill；验证可见性且不会调用模型")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="capability probe 临时目录所属工作区")
    parser.add_argument("--output", type=Path, help="可选 JSON evidence 路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        data = collect_diagnostics(
            require_live=args.live,
            probe_skill=args.probe_skill,
            workspace=args.workspace,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(render_json(data, pretty=True) + "\n", encoding="utf-8")
        return data

    return run_cli("doctor.check", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
