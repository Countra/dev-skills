"""以只读方式解析 Skill metadata、引用和静态资源。"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import read_text


FRONTMATTER_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
STANDARD_TOP_LEVEL = {
    "SKILL.md",
    "agents",
    "assets",
    "references",
    "schemas",
    "scripts",
    "tests",
}


@dataclass(frozen=True)
class SkillDocument:
    """保留 metadata 与正文的机械解析结果，不承载质量判断。"""

    path: Path
    text: str
    frontmatter: dict[str, str]
    frontmatter_errors: tuple[str, ...]
    body: str
    line_count: int


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["缺少起始 frontmatter 分隔符"], text
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}, ["缺少结束 frontmatter 分隔符"], ""

    values: dict[str, str] = {}
    errors: list[str] = []
    block_key: str | None = None
    block_lines: list[str] = []
    nested_key: str | None = None

    def flush_block() -> None:
        nonlocal block_key, block_lines
        if block_key is not None:
            values[block_key] = " ".join(block_lines).strip()
            block_key = None
            block_lines = []

    for line_number, raw in enumerate(lines[1:end], start=2):
        if raw.startswith((" ", "\t")):
            if block_key is not None:
                block_lines.append(raw.strip())
            elif nested_key is None and raw.strip():
                errors.append(f"第 {line_number} 行存在无归属缩进")
            continue
        flush_block()
        nested_key = None
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            errors.append(f"第 {line_number} 行缺少键值分隔符")
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            errors.append(f"第 {line_number} 行键名为空")
            continue
        if key in values or key == block_key:
            errors.append(f"第 {line_number} 行重复字段 {key}")
            continue
        if value in {">", ">-", "|", "|-"}:
            block_key = key
            block_lines = []
        elif not value:
            values[key] = ""
            nested_key = key
        else:
            values[key] = value.strip("\"'")
    flush_block()
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return values, errors, body


def parse_skill(source: Path) -> SkillDocument:
    skill_path = source / "SKILL.md"
    if not skill_path.is_file():
        return SkillDocument(skill_path, "", {}, ("缺少 SKILL.md",), "", 0)
    text = read_text(skill_path)
    frontmatter, errors, body = parse_frontmatter(text)
    return SkillDocument(
        path=skill_path,
        text=text,
        frontmatter=frontmatter,
        frontmatter_errors=tuple(errors),
        body=body,
        line_count=len(text.splitlines()),
    )


def _link_target(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def inspect_links(source: Path, document: SkillDocument) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for match in MARKDOWN_LINK.finditer(document.text):
        target = _link_target(match.group(1))
        line = document.text.count("\n", 0, match.start()) + 1
        item: dict[str, Any] = {"target": target, "line": line}
        if not target or target.startswith("#"):
            item["status"] = "anchor"
        elif URI_SCHEME.match(target) or target.startswith("//"):
            item["status"] = "external"
        else:
            local = target.split("#", 1)[0].split("?", 1)[0]
            local_path = Path(local)
            if local_path.is_absolute():
                item["status"] = "escape"
            else:
                resolved = (document.path.parent / local_path).resolve(strict=False)
                source_resolved = source.resolve(strict=True)
                if resolved != source_resolved and not resolved.is_relative_to(source_resolved):
                    item["status"] = "escape"
                elif not resolved.exists():
                    item["status"] = "broken"
                else:
                    item["status"] = "ok"
                    item["resolved"] = resolved.relative_to(source_resolved).as_posix()
        links.append(item)
    return links


def inspect_structure(source: Path) -> dict[str, list[str]]:
    unknown: list[str] = []
    empty: list[str] = []
    for child in sorted(source.iterdir(), key=lambda item: item.name.casefold()):
        if child.name not in STANDARD_TOP_LEVEL:
            unknown.append(child.name)
        if child.is_file() and child.stat().st_size == 0:
            empty.append(child.name)
        if child.is_dir():
            empty.extend(
                path.relative_to(source).as_posix()
                for path in sorted(child.rglob("*"))
                if path.is_file() and path.stat().st_size == 0
            )
    return {"unknown_top_level": unknown, "empty_files": empty}


def _minimal_yaml_issues(path: Path, text: str) -> list[str]:
    issues: list[str] = []
    if "\x00" in text:
        issues.append("包含 NUL 字符")
    if "\t" in text:
        issues.append("包含制表符缩进")
    meaningful = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if meaningful and not any(":" in line or line.startswith("-") for line in meaningful):
        issues.append("未发现 YAML 键值或列表结构")
    if path.name == "openai.yaml" and not any(line.startswith("interface:") for line in meaningful):
        issues.append("缺少 interface 顶层字段")
    return issues


def inspect_syntax(source: Path, manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for entry in manifest:
        relative = str(entry["path"])
        path = source / relative
        suffix = path.suffix.lower()
        if suffix not in {".py", ".json", ".yaml", ".yml"}:
            continue
        try:
            text = read_text(path)
            if suffix == ".py":
                ast.parse(text, filename=relative)
            elif suffix == ".json":
                json.loads(text)
            else:
                for message in _minimal_yaml_issues(path, text):
                    issues.append({"path": relative, "message": message})
        except (SyntaxError, json.JSONDecodeError) as exc:
            issues.append({"path": relative, "message": str(exc)})
    return issues
