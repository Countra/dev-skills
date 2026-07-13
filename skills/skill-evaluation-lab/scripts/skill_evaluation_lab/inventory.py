"""仓库 skill、eval 和 CI coverage 的只读 inventory。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    values: dict[str, str] = {}
    active: str | None = None
    folded: list[str] = []
    for raw in lines[1:end]:
        if active and (raw.startswith(" ") or raw.startswith("\t")):
            folded.append(raw.strip())
            continue
        if active:
            values[active] = " ".join(folded).strip()
            active = None
            folded = []
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"\'')
        if value in {">", ">-", "|", "|-"}:
            active = key
        else:
            values[key] = value
    if active:
        values[active] = " ".join(folded).strip()
    return values


def validate_skill(skill_dir: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.is_file():
        return [{"code": "skill_missing", "path": str(skill_path), "message": "缺少 SKILL.md"}]
    try:
        frontmatter = _frontmatter(skill_path)
    except (OSError, UnicodeError) as exc:
        return [{"code": "skill_unreadable", "path": str(skill_path), "message": str(exc)}]
    allowed = {"name", "description"}
    unknown = sorted(set(frontmatter) - allowed)
    if unknown:
        issues.append(
            {
                "code": "frontmatter_unknown",
                "path": unknown[0],
                "message": "frontmatter 只允许 name 和 description",
            }
        )
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if not NAME_PATTERN.fullmatch(name):
        issues.append({"code": "skill_name_invalid", "path": "name", "message": "name 必须是小写连字符格式"})
    elif name != skill_dir.name:
        issues.append({"code": "skill_name_mismatch", "path": "name", "message": "name 必须与目录名一致"})
    if not description:
        issues.append({"code": "skill_description_missing", "path": "description", "message": "description 不能为空"})
    elif len(description) > 1024:
        issues.append({"code": "skill_description_long", "path": "description", "message": "description 超过 1024 字符"})
    return issues


def scan_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    skills_root = root / "skills"
    evals_root = root / "evals"
    workflows_root = root / ".github" / "workflows"
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(workflows_root.glob("*.yml"))
    ) if workflows_root.is_dir() else ""
    skills: list[dict[str, Any]] = []
    if skills_root.is_dir():
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            if not (skill_dir / "SKILL.md").is_file():
                continue
            issues = validate_skill(skill_dir)
            scripts = list((skill_dir / "scripts").glob("*.py")) if (skill_dir / "scripts").is_dir() else []
            tests = list((skill_dir / "tests").glob("test_*.py")) if (skill_dir / "tests").is_dir() else []
            eval_dir = evals_root / skill_dir.name
            skills.append(
                {
                    "name": skill_dir.name,
                    "path": str(skill_dir.relative_to(root)).replace("\\", "/"),
                    "valid": not issues,
                    "issues": issues,
                    "public_script_count": len(scripts),
                    "test_count": len(tests),
                    "has_openai_metadata": (skill_dir / "agents" / "openai.yaml").is_file(),
                    "has_eval_dir": eval_dir.is_dir(),
                    "eval_file_count": len(list(eval_dir.rglob("*"))) if eval_dir.is_dir() else 0,
                    "ci_referenced": skill_dir.name in workflow_text,
                }
            )
    return {
        "root": str(root),
        "skill_count": len(skills),
        "valid_skill_count": sum(item["valid"] for item in skills),
        "skills": skills,
    }
