"""生成可重复、只读且不执行目标代码的静态证据。"""

from __future__ import annotations

import ast
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import IDENTIFIER, SCHEMA_VERSION, validate_static_evidence
from .errors import ContractError, SkillError
from .paths import (
    DEFAULT_LIMITS,
    is_link_like,
    read_text,
    resolve_input,
    resolve_workspace,
    source_identity,
)
from .skill_parser import (
    FRONTMATTER_NAME,
    SkillDocument,
    inspect_links,
    inspect_structure,
    inspect_syntax,
    parse_skill,
)

TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".toml"}
PROCESS_IMPORTS = {"subprocess", "pty"}
NETWORK_IMPORTS = {"socket", "requests", "httpx", "aiohttp", "urllib3"}
MODEL_IMPORTS = {"openai", "anthropic", "google.generativeai", "agents"}
PROCESS_CALLS = {"os.system", "os.popen", "subprocess.run", "subprocess.call", "subprocess.Popen"}
ENV_CALLS = {"os.getenv", "os.environ.get"}
WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "touch", "rename", "replace", "unlink", "rmdir"}
AGENT_COMMAND = re.compile(r"\b(?:codex|claude|gemini|opencode)\s+(?:exec|run|start)\b", re.IGNORECASE)


def _evidence(path: str, detail: str) -> dict[str, str]:
    return {"path": path, "detail": detail}


def _check(
    check_id: str,
    dimension: str,
    status: str,
    summary: str,
    evidence: list[dict[str, str]],
    guidance: str = "",
) -> dict[str, Any]:
    severity = {
        "pass": "info",
        "warn": "advisory",
        "fail": "blocking",
        "not_applicable": "info",
    }[status]
    return {
        "id": check_id,
        "dimension": dimension,
        "status": status,
        "severity": severity,
        "summary": summary,
        "evidence": evidence,
        "guidance": guidance,
    }


def _metadata_check(source: Path, document: SkillDocument) -> dict[str, Any]:
    problems = list(document.frontmatter_errors)
    advisories: list[str] = []
    name = document.frontmatter.get("name", "")
    description = document.frontmatter.get("description", "")
    if not FRONTMATTER_NAME.fullmatch(name):
        problems.append("name 必须使用小写连字符格式")
    elif name != source.name:
        problems.append("name 必须与 Skill 目录名一致")
    if not description:
        problems.append("description 不能为空")
    elif len(description) > 1024:
        problems.append("description 超过 1024 字符")
    elif len(description) < 20:
        advisories.append("description 较短，应由语义审查确认是否包含使用时机")
    unknown = sorted(
        set(document.frontmatter)
        - {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    )
    if unknown:
        advisories.append(f"发现非标准 frontmatter 字段：{', '.join(unknown)}")
    if problems:
        return _check(
            "skill.metadata",
            "metadata",
            "fail",
            "; ".join(problems),
            [_evidence("SKILL.md", item) for item in problems],
            "修复 frontmatter 后重新生成静态证据。",
        )
    if advisories:
        return _check(
            "skill.metadata",
            "metadata",
            "warn",
            "; ".join(advisories),
            [_evidence("SKILL.md", item) for item in advisories],
            "由当前 Agent 在 invocation boundary 维度确认语义边界。",
        )
    return _check(
        "skill.metadata",
        "metadata",
        "pass",
        "frontmatter、目录名和 description 机械约束有效",
        [_evidence("SKILL.md", f"name={name}; description_chars={len(description)}")],
    )


def _structure_check(source: Path, identity: dict[str, Any]) -> dict[str, Any]:
    structure = inspect_structure(source)
    advisories: list[str] = []
    if structure["unknown_top_level"]:
        advisories.append("非标准顶层资源：" + ", ".join(structure["unknown_top_level"]))
    if structure["empty_files"]:
        advisories.append("空文件：" + ", ".join(structure["empty_files"][:10]))
    evidence = [
        _evidence(
            ".",
            f"files={identity['file_count']}; total_bytes={identity['total_bytes']}",
        )
    ]
    if advisories:
        evidence.extend(_evidence(".", item) for item in advisories)
        return _check(
            "skill.structure",
            "structure",
            "warn",
            "; ".join(advisories),
            evidence,
            "确认非标准资源确有必要，并移除空 placeholder。",
        )
    return _check(
        "skill.structure",
        "structure",
        "pass",
        "必需入口存在，资源规模和顶层结构在约束内",
        evidence,
    )


def _reference_check(source: Path, identity: dict[str, Any]) -> dict[str, Any]:
    links: list[dict[str, Any]] = []
    for entry in identity["files"]:
        relative = str(entry["path"])
        if Path(relative).suffix.lower() != ".md":
            continue
        path = source / relative
        text = read_text(path)
        document = SkillDocument(path, text, {}, (), text, len(text.splitlines()))
        for item in inspect_links(source, document):
            item["document"] = relative
            links.append(item)
    invalid = [item for item in links if item["status"] in {"broken", "escape"}]
    if invalid:
        evidence = [
            _evidence(
                str(item["document"]),
                f"line={item['line']}; target={item['target']}; status={item['status']}",
            )
            for item in invalid
        ]
        return _check(
            "skill.references",
            "references",
            "fail",
            f"发现 {len(invalid)} 个断链或越界引用",
            evidence,
            "修复相对链接并确保引用留在 Skill source 内。",
        )
    local_count = sum(item["status"] == "ok" for item in links)
    return _check(
        "skill.references",
        "references",
        "pass",
        "Markdown 相对引用均可解析且未越界",
        [_evidence(".", f"local_links={local_count}; total_links={len(links)}")],
    )


def _disclosure_check(source: Path, document: SkillDocument) -> dict[str, Any]:
    reference_files = list((source / "references").glob("*.md")) if (source / "references").is_dir() else []
    advisories: list[str] = []
    if document.line_count > 500:
        advisories.append(f"SKILL.md 共 {document.line_count} 行，超过 500 行建议上限")
    if reference_files and "references/" not in document.text.replace("\\", "/"):
        advisories.append("存在 reference 文档，但 SKILL.md 未提供按需入口")
    if not reference_files and document.line_count > 200:
        advisories.append("较长 SKILL.md 未使用 references 渐进披露")
    if advisories:
        return _check(
            "skill.disclosure",
            "information_architecture",
            "warn",
            "; ".join(advisories),
            [_evidence("SKILL.md", item) for item in advisories],
            "将细节移入按需 reference，并保留单一真相源。",
        )
    return _check(
        "skill.disclosure",
        "information_architecture",
        "pass",
        "核心说明规模适中，并具备可接受的渐进披露结构",
        [_evidence("SKILL.md", f"lines={document.line_count}; references={len(reference_files)}")],
    )


def _syntax_check(source: Path, identity: dict[str, Any]) -> dict[str, Any]:
    issues = inspect_syntax(source, identity["files"])
    if issues:
        return _check(
            "skill.syntax",
            "syntax",
            "fail",
            f"发现 {len(issues)} 个静态语法问题",
            [_evidence(str(item["path"]), str(item["message"])) for item in issues],
            "修复 Python、JSON 或最小 YAML 结构后重试。",
        )
    checked = sum(
        Path(str(entry["path"])).suffix.lower() in {".py", ".json", ".yaml", ".yml"}
        for entry in identity["files"]
    )
    return _check(
        "skill.syntax",
        "syntax",
        "pass",
        "支持的代码与数据文件通过只读语法解析",
        [_evidence(".", f"parsed_files={checked}; imported_files=0")],
    )


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _append_signal(signals: list[dict[str, Any]], kind: str, path: str, detail: str, line: int) -> None:
    item = {"kind": kind, "path": path, "line": line, "detail": detail}
    if item not in signals:
        signals.append(item)


def _python_capabilities(relative: str, text: str) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError:
        return signals
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                root = name.split(".", 1)[0]
                if root in PROCESS_IMPORTS:
                    _append_signal(signals, "process", relative, f"import {name}", node.lineno)
                if root in NETWORK_IMPORTS:
                    _append_signal(signals, "network", relative, f"import {name}", node.lineno)
                if name in MODEL_IMPORTS or root in MODEL_IMPORTS:
                    _append_signal(signals, "agent_or_model", relative, f"import {name}", node.lineno)
        if isinstance(node, ast.Call):
            call = _dotted_name(node.func)
            if call in PROCESS_CALLS:
                _append_signal(signals, "process", relative, call, node.lineno)
            if call in ENV_CALLS:
                _append_signal(signals, "environment_read", relative, call, node.lineno)
            if call.rsplit(".", 1)[-1] in WRITE_METHODS:
                _append_signal(signals, "file_write", relative, call, node.lineno)
            if call == "open" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
                if any(flag in mode for flag in "wax+"):
                    _append_signal(signals, "file_write", relative, f"open mode={mode}", node.lineno)
        if isinstance(node, ast.Attribute) and _dotted_name(node) == "os.environ":
            _append_signal(signals, "environment_read", relative, "os.environ", node.lineno)
    return signals


def capability_signals(source: Path, identity: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for entry in identity["files"]:
        relative = str(entry["path"])
        path = source / relative
        if path.suffix.lower() not in TEXT_SUFFIXES or relative.startswith("tests/"):
            continue
        text = read_text(path)
        if path.suffix.lower() == ".py":
            signals.extend(_python_capabilities(relative, text))
        for match in AGENT_COMMAND.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            _append_signal(signals, "agent_command_text", relative, match.group(0), line)
    return sorted(signals, key=lambda item: (item["kind"], item["path"], item["line"], item["detail"]))


def _capability_check(signals: list[dict[str, Any]]) -> dict[str, Any]:
    if not signals:
        return _check(
            "skill.capabilities",
            "capabilities",
            "pass",
            "未发现受关注的静态能力信号",
            [_evidence(".", "process/network/environment/file-write/agent signals=0")],
        )
    counts = Counter(str(item["kind"]) for item in signals)
    summary = ", ".join(f"{name}={counts[name]}" for name in sorted(counts))
    return _check(
        "skill.capabilities",
        "capabilities",
        "warn",
        "发现需要人工确认的静态能力信号：" + summary,
        [
            _evidence(
                str(item["path"]),
                f"line={item['line']}; {item['kind']}: {item['detail']}",
            )
            for item in signals[:50]
        ],
        "这些仅是静态信号，不代表能力实际执行；由安全与权限语义审查确认。",
    )


def _validation_assets_check(workspace: Path, source: Path) -> dict[str, Any]:
    name = source.name
    tests = (source / "tests").is_dir() and any((source / "tests").glob("test_*.py"))
    evals = (workspace / "evals" / name).is_dir()
    workflow_root = workspace / ".github" / "workflows"
    ci = False
    if is_link_like(workflow_root) or (workflow_root.exists() and not workflow_root.is_dir()):
        raise SkillError(
            "CI workflow 根目录必须是非链接目录",
            code="SKILL_WORKFLOW_DIRECTORY_INVALID",
            path=str(workflow_root),
        )
    if workflow_root.exists():
        workflow_count = 0
        for path in workflow_root.iterdir():
            workflow_count += 1
            if workflow_count > DEFAULT_LIMITS.max_files:
                raise SkillError(
                    "CI workflow 数量超过静态读取上限",
                    code="SKILL_WORKFLOW_COUNT_LIMIT",
                    path=str(workflow_root),
                )
            if is_link_like(path):
                raise SkillError(
                    "CI workflow 不能是符号链接或 junction",
                    code="SKILL_WORKFLOW_LINK",
                    path=str(path),
                )
            if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}:
                ci = ci or name in read_text(path)
    coverage = {"tests": bool(tests), "evals": evals, "ci": ci}
    missing = [key for key, present in coverage.items() if not present]
    status = "warn" if missing else "pass"
    summary = "缺少可发现的验证资产：" + ", ".join(missing) if missing else "tests、evals 与 CI coverage 均可发现"
    return _check(
        "skill.validation_assets",
        "validation",
        status,
        summary,
        [_evidence(".", "; ".join(f"{key}={str(value).lower()}" for key, value in coverage.items()))],
        "按 Skill 风险补充可重复验证资产。" if missing else "",
    )


def _evaluate_one(workspace: Path, source: Path) -> dict[str, Any]:
    identity = source_identity(workspace, source)
    document = parse_skill(source)
    capabilities = capability_signals(source, identity)
    checks = [
        _metadata_check(source, document),
        _structure_check(source, identity),
        _reference_check(source, identity),
        _disclosure_check(source, document),
        _syntax_check(source, identity),
        _capability_check(capabilities),
        _validation_assets_check(workspace, source),
    ]
    return {"identity": identity, "checks": checks, "capabilities": capabilities}


def _delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    candidate_files = {item["path"]: item["sha256"] for item in candidate["identity"]["files"]}
    baseline_files = {item["path"]: item["sha256"] for item in baseline["identity"]["files"]}
    candidate_checks = {item["id"]: item["status"] for item in candidate["checks"]}
    baseline_checks = {item["id"]: item["status"] for item in baseline["checks"]}
    candidate_capabilities = {
        (item["kind"], item["path"], item["detail"])
        for item in candidate["capabilities"]
    }
    baseline_capabilities = {
        (item["kind"], item["path"], item["detail"])
        for item in baseline["capabilities"]
    }
    return {
        "added_files": sorted(set(candidate_files) - set(baseline_files)),
        "removed_files": sorted(set(baseline_files) - set(candidate_files)),
        "changed_files": sorted(
            path
            for path in set(candidate_files) & set(baseline_files)
            if candidate_files[path] != baseline_files[path]
        ),
        "check_status_changes": [
            {"id": check_id, "baseline": baseline_checks[check_id], "candidate": candidate_checks[check_id]}
            for check_id in sorted(set(candidate_checks) & set(baseline_checks))
            if candidate_checks[check_id] != baseline_checks[check_id]
        ],
        "capabilities_added": [list(item) for item in sorted(candidate_capabilities - baseline_capabilities)],
        "capabilities_removed": [list(item) for item in sorted(baseline_capabilities - candidate_capabilities)],
    }


def evaluate_skill(
    workspace: Path,
    candidate: Path,
    *,
    baseline: Path | None = None,
    evaluation_id: str | None = None,
) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    candidate = resolve_input(workspace, candidate, label="candidate", expect="directory")
    baseline_path = (
        resolve_input(workspace, baseline, label="baseline", expect="directory")
        if baseline is not None
        else None
    )
    if baseline_path == candidate:
        raise SkillError(
            "baseline 不能与 candidate 指向同一目录",
            code="SKILL_BASELINE_IDENTICAL",
            path=str(candidate),
        )
    candidate_result = _evaluate_one(workspace, candidate)
    baseline_result = _evaluate_one(workspace, baseline_path) if baseline_path else None
    identifier = evaluation_id or f"{candidate.name}-{candidate_result['identity']['tree_sha256'][:12]}"
    if not IDENTIFIER.fullmatch(identifier):
        raise ContractError(
            "evaluation_id 格式无效",
            code="CONTRACT_EVALUATION_ID",
            path="$.evaluation_id",
        )

    if baseline_result:
        delta = _delta(candidate_result, baseline_result)
        delta_check = _check(
            "skill.baseline_delta",
            "baseline",
            "pass",
            "已生成 candidate/baseline 的确定性差异",
            [
                _evidence(
                    ".",
                    "added={}; removed={}; changed={}".format(
                        len(delta["added_files"]),
                        len(delta["removed_files"]),
                        len(delta["changed_files"]),
                    ),
                )
            ],
        )
    else:
        delta = None
        delta_check = _check(
            "skill.baseline_delta",
            "baseline",
            "not_applicable",
            "未提供 baseline，不生成比较结论",
            [_evidence(".", "baseline=not_provided")],
        )
    checks = candidate_result["checks"] + [delta_check]
    counts = Counter(str(item["status"]) for item in checks)
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": identifier,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "checker": {
            "name": "skill-evaluation-lab",
            "contract": "deterministic-static-only",
            "agent_calls": 0,
            "network_calls": 0,
            "target_imports": 0,
        },
        "candidate": candidate_result["identity"],
        "baseline": baseline_result["identity"] if baseline_result else None,
        "checks": checks,
        "capabilities": candidate_result["capabilities"],
        "delta": delta,
        "summary": {status: counts.get(status, 0) for status in ("pass", "warn", "fail", "not_applicable")},
    }
    return validate_static_evidence(evidence)
