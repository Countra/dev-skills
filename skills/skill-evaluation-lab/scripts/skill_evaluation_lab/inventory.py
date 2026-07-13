"""仓库 Skill、验证资产和 CI coverage 的只读盘点。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import LabError, SkillError
from .paths import DEFAULT_LIMITS, is_link_like, read_text, resolve_workspace
from .skill_parser import FRONTMATTER_NAME, parse_skill


MAX_SKILLS = 512
MAX_WORKFLOWS = 128


def _bounded_children(path: Path, *, limit: int, label: str) -> list[Path]:
    if is_link_like(path):
        raise SkillError(
            f"{label} 必须是非链接目录",
            code="INVENTORY_DIRECTORY_INVALID",
            path=str(path),
        )
    if not path.exists():
        return []
    if not path.is_dir():
        raise SkillError(
            f"{label} 必须是非链接目录",
            code="INVENTORY_DIRECTORY_INVALID",
            path=str(path),
        )
    children: list[Path] = []
    for child in path.iterdir():
        if len(children) >= limit:
            raise SkillError(
                f"{label} 目录项超过上限",
                code="INVENTORY_ENTRY_LIMIT",
                path=str(path),
            )
        if is_link_like(child):
            raise SkillError(
                f"{label} 包含符号链接或 junction",
                code="INVENTORY_LINK_REJECTED",
                path=str(child),
            )
        children.append(child)
    return sorted(children, key=lambda item: item.name.casefold())


def _workflow_text(workflows_root: Path) -> str:
    parts: list[str] = []
    for path in _bounded_children(workflows_root, limit=MAX_WORKFLOWS, label="workflow"):
        if path.suffix.lower() in {".yml", ".yaml"} and path.is_file():
            parts.append(read_text(path))
    return "\n".join(parts)


def _metadata_issues(skill_dir: Path) -> list[dict[str, str]]:
    try:
        document = parse_skill(skill_dir)
    except LabError as exc:
        return [{"code": exc.code, "path": exc.path or "SKILL.md", "message": exc.message}]
    issues = [
        {"code": "SKILL_FRONTMATTER_INVALID", "path": "SKILL.md", "message": message}
        for message in document.frontmatter_errors
    ]
    name = document.frontmatter.get("name", "")
    description = document.frontmatter.get("description", "")
    if not FRONTMATTER_NAME.fullmatch(name):
        issues.append(
            {"code": "SKILL_NAME_INVALID", "path": "name", "message": "name 必须使用小写连字符格式"}
        )
    elif name != skill_dir.name:
        issues.append(
            {"code": "SKILL_NAME_MISMATCH", "path": "name", "message": "name 必须与目录名一致"}
        )
    if not description:
        issues.append(
            {"code": "SKILL_DESCRIPTION_MISSING", "path": "description", "message": "description 不能为空"}
        )
    elif len(description) > 1024:
        issues.append(
            {"code": "SKILL_DESCRIPTION_LONG", "path": "description", "message": "description 超过 1024 字符"}
        )
    return issues


def _file_count(path: Path) -> int:
    if is_link_like(path):
        raise SkillError(
            "inventory 资源必须是非链接目录",
            code="INVENTORY_DIRECTORY_INVALID",
            path=str(path),
        )
    if not path.exists():
        return 0
    if not path.is_dir():
        raise SkillError(
            "inventory 资源必须是非链接目录",
            code="INVENTORY_DIRECTORY_INVALID",
            path=str(path),
        )
    stack = [path]
    file_count = 0
    entry_count = 0
    while stack:
        directory = stack.pop()
        for child in directory.iterdir():
            entry_count += 1
            if entry_count > DEFAULT_LIMITS.max_entries:
                raise SkillError(
                    "inventory 资源目录项超过上限",
                    code="INVENTORY_ENTRY_LIMIT",
                    path=str(path),
                )
            if is_link_like(child):
                raise SkillError(
                    "inventory 资源包含符号链接或 junction",
                    code="INVENTORY_LINK_REJECTED",
                    path=str(child),
                )
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                file_count += 1
                if file_count > DEFAULT_LIMITS.max_files:
                    raise SkillError(
                        "inventory 资源文件数量超过上限",
                        code="INVENTORY_FILE_LIMIT",
                        path=str(path),
                    )
    return file_count


def scan_repository(root: Path) -> dict[str, Any]:
    root = resolve_workspace(root)
    skills_root = root / "skills"
    evals_root = root / "evals"
    if is_link_like(evals_root):
        raise SkillError(
            "evals 根目录不能是符号链接或 junction",
            code="INVENTORY_LINK_REJECTED",
            path=str(evals_root),
        )
    workflows = _workflow_text(root / ".github" / "workflows")
    skills: list[dict[str, Any]] = []
    if skills_root.exists():
        for skill_dir in _bounded_children(skills_root, limit=MAX_SKILLS, label="skills"):
            skill_file = skill_dir / "SKILL.md"
            if not skill_dir.is_dir():
                continue
            if is_link_like(skill_file):
                raise SkillError(
                    "SKILL.md 不能是符号链接或 junction",
                    code="INVENTORY_LINK_REJECTED",
                    path=str(skill_file),
                )
            if not skill_file.is_file():
                continue
            issues = _metadata_issues(skill_dir)
            scripts_root = skill_dir / "scripts"
            public_scripts = sorted(
                path.name
                for path in _bounded_children(
                    scripts_root,
                    limit=DEFAULT_LIMITS.max_entries,
                    label=f"{skill_dir.name} scripts",
                )
                if path.is_file() and path.match("se_*.py")
            )
            tests_root = skill_dir / "tests"
            tests = sorted(
                path.name
                for path in _bounded_children(
                    tests_root,
                    limit=DEFAULT_LIMITS.max_entries,
                    label=f"{skill_dir.name} tests",
                )
                if path.is_file() and path.match("test_*.py")
            )
            eval_dir = evals_root / skill_dir.name
            eval_file_count = _file_count(eval_dir)
            skills.append(
                {
                    "name": skill_dir.name,
                    "path": skill_dir.relative_to(root).as_posix(),
                    "valid": not issues,
                    "issues": issues,
                    "public_scripts": public_scripts,
                    "test_files": tests,
                    "reference_count": _file_count(skill_dir / "references"),
                    "schema_count": _file_count(skill_dir / "schemas"),
                    "asset_count": _file_count(skill_dir / "assets"),
                    "has_openai_metadata": (
                        (skill_dir / "agents" / "openai.yaml").is_file()
                        and not is_link_like(skill_dir / "agents" / "openai.yaml")
                    ),
                    "has_eval_dir": eval_dir.is_dir() and not is_link_like(eval_dir),
                    "eval_file_count": eval_file_count,
                    "ci_referenced": skill_dir.name in workflows,
                }
            )
    return {
        "root": str(root),
        "skill_count": len(skills),
        "valid_skill_count": sum(item["valid"] for item in skills),
        "skills": skills,
        "checker": {
            "contract": "read-only-inventory",
            "agent_calls": 0,
            "network_calls": 0,
            "target_imports": 0,
        },
    }
