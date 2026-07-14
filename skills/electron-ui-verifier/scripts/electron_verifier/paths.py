"""Electron verifier 安装根及只读资源路径。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import VerifierError


@dataclass(frozen=True)
class SkillPaths:
    """从模块位置派生的 Skill 安装资源，不承载用户运行状态。"""

    root: Path
    scripts_dir: Path
    server_script: Path
    check_script: Path
    requirements_file: Path
    schemas_dir: Path
    assets_dir: Path


def skill_paths() -> SkillPaths:
    root = Path(__file__).resolve().parents[2]
    scripts_dir = root / "scripts"
    return SkillPaths(
        root=root,
        scripts_dir=scripts_dir,
        server_script=scripts_dir / "ev_server.py",
        check_script=scripts_dir / "ev_check_env.py",
        requirements_file=root / "requirements.txt",
        schemas_dir=root / "schemas",
        assets_dir=root / "assets",
    )


def inspect_skill_install(paths: SkillPaths) -> dict[str, Any]:
    expected = {
        "skill": (paths.root, "directory"),
        "serverScript": (paths.server_script, "file"),
        "checkScript": (paths.check_script, "file"),
        "requirements": (paths.requirements_file, "file"),
        "schemas": (paths.schemas_dir, "directory"),
        "assets": (paths.assets_dir, "directory"),
    }
    checks = []
    for name, (path, kind) in expected.items():
        exists = path.is_file() if kind == "file" else path.is_dir()
        checks.append({"name": name, "path": str(path), "kind": kind, "exists": exists})
    return {
        "ok": all(item["exists"] for item in checks),
        "skillRoot": str(paths.root),
        "checks": checks,
    }


def require_skill_install(paths: SkillPaths) -> dict[str, Any]:
    result = inspect_skill_install(paths)
    if result["ok"] is not True:
        raise VerifierError(
            "skill_install_invalid",
            "electron-ui-verifier 安装根缺少必需资源",
            status=500,
            details=result,
        )
    return result
