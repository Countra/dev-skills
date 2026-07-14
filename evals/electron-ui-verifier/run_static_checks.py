#!/usr/bin/env python3
"""检查 electron-ui-verifier 的架构与静态契约。"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "electron-ui-verifier"
PACKAGE = SKILL / "scripts" / "electron_verifier"
SCHEMAS = SKILL / "schemas"
PUBLIC_SCRIPTS = (
    "ev_init.py", "ev_probe.py", "ev_prepare.py", "ev_action.py", "ev_workflow.py",
    "ev_finalize.py", "ev_pending.py", "ev_persist.py", "ev_knowledge.py",
    "ev_suggest.py", "ev_assets.py", "ev_asset_extract.py", "ev_asset_runner.py",
    "ev_export_workflow.py", "ev_risk.py", "ev_server.py",
    "ev_operation.py",
)


def package_dependencies(files: list[Path]) -> dict[str, set[str]]:
    names = {path.stem for path in files}
    graph: dict[str, set[str]] = {name: set() for name in names}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                target = node.module.split(".", 1)[0]
                if target in names:
                    graph[path.stem].add(target)
    return graph


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> list[str] | None:
        if name in visiting:
            start = visiting.index(name)
            return visiting[start:] + [name]
        if name in visited:
            return None
        visiting.append(name)
        for target in sorted(graph[name]):
            cycle = visit(target)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(name)
        return None

    for name in sorted(graph):
        cycle = visit(name)
        if cycle:
            return cycle
    return None


def main() -> int:
    failures: list[str] = []
    metrics: dict[str, Any] = {}
    files = sorted(PACKAGE.glob("*.py"))
    if not files:
        failures.append("领域 package 为空")
    oversized = []
    for path in files:
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > 500:
            oversized.append({"path": str(path.relative_to(ROOT)), "lines": lines})
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"Python 语法错误：{path}: {exc}")
    if oversized:
        failures.append("新增生产 Python 文件超过 500 行")
    cycle = find_cycle(package_dependencies(files)) if files else None
    if cycle:
        failures.append(f"package 存在循环依赖：{' -> '.join(cycle)}")
    bootstrap = SKILL / "scripts" / "ev_server.py"
    bootstrap_text = bootstrap.read_text(encoding="utf-8")
    if len(bootstrap_text.splitlines()) > 100:
        failures.append("ev_server.py 不再是薄 bootstrap")
    forbidden_transport = ("MinimalWebSocket", "class CDPClient", "Sec-WebSocket", "socket.create_connection")
    transport_hits = [pattern for pattern in forbidden_transport if pattern in bootstrap_text]
    for path in files:
        text = path.read_text(encoding="utf-8")
        transport_hits.extend(f"{path.name}:{pattern}" for pattern in forbidden_transport if pattern in text)
    if transport_hits:
        failures.append(f"生产代码仍包含手写 raw transport：{transport_hits}")
    store_facade = SKILL / "scripts" / "ev_knowledge_store.py"
    if store_facade.exists():
        failures.append("旧 knowledge store facade 仍存在")
    index_text = (PACKAGE / "knowledge_index.py").read_text(encoding="utf-8") if (PACKAGE / "knowledge_index.py").exists() else ""
    if "journal_mode=WAL" in index_text.replace(" ", ""):
        failures.append("derived index 生产代码启用了 WAL")
    package_text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for forbidden_domain in ("VideoForensic", "Termous"):
        if forbidden_domain in package_text:
            failures.append(f"生产 package 包含应用专属词：{forbidden_domain}")
    schema_ids: set[str] = set()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"Schema JSON 无效：{path}: {exc}")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            failures.append(f"Schema 未声明 Draft 2020-12：{path}")
        identifier = schema.get("$id")
        if not identifier or identifier in schema_ids:
            failures.append(f"Schema $id 缺失或重复：{path}")
        schema_ids.add(str(identifier))
    if len(schema_ids) < 7 or not (SCHEMAS / "risk-receipt.schema.json").exists():
        failures.append("当前契约 schema 数量不足")
    required_security_modules = (
        PACKAGE / "sensitivity.py",
        PACKAGE / "risk_authorization.py",
        PACKAGE / "operations.py",
    )
    missing_security_modules = [path.name for path in required_security_modules if not path.exists()]
    if missing_security_modules:
        failures.append(f"安全或 operation 边界模块缺失：{missing_security_modules}")
    if not (SCHEMAS / "operation.schema.json").exists():
        failures.append("durable operation schema 缺失")
    forbidden_bypasses = ("allowWithoutPostcondition", "confirmRisk", "allowCoordinate", "riskConfirmed")
    bypass_hits = [marker for marker in forbidden_bypasses if marker in package_text]
    action_schema_text = (SCHEMAS / "action.schema.json").read_text(encoding="utf-8")
    bypass_hits.extend(f"action.schema.json:{marker}" for marker in forbidden_bypasses if marker in action_schema_text)
    if bypass_hits:
        failures.append(f"旧 mutation 自签旁路仍存在：{bypass_hits}")
    public_legacy_hits = []
    public_parse_failures = []
    for name in PUBLIC_SCRIPTS:
        path = SKILL / "scripts" / name
        try:
            text = path.read_text(encoding="utf-8")
            ast.parse(text, filename=str(path))
        except (OSError, SyntaxError) as exc:
            public_parse_failures.append(f"{name}:{exc}")
            continue
        for marker in ("ev_knowledge_store", "ev_knowledge_extract", "supplemental_actions"):
            if marker in text:
                public_legacy_hits.append(f"{name}:{marker}")
    if public_parse_failures:
        failures.append(f"公共 CLI 缺失或语法错误：{public_parse_failures}")
    if public_legacy_hits:
        failures.append(f"公共 CLI 仍依赖旧知识路径：{public_legacy_hits}")
    removed_paths = (
        "ev_knowledge_store.py", "ev_knowledge_extract.py", "ev_learn.py", "ev_promote.py",
        "ev_asset_extract_smoke.py", "ev_asset_reuse_smoke.py", "ev_knowledge_smoke.py",
        "ev_pending_smoke.py", "ev_progressive_suggest_smoke.py",
    )
    stale_paths = [name for name in removed_paths if (SKILL / "scripts" / name).exists()]
    if stale_paths:
        failures.append(f"旧知识兼容/烟测文件仍存在：{stale_paths}")
    source_scripts = sorted((SKILL / "scripts").glob("*.py"))
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_scripts)
    for forbidden_domain in ("VideoForensic", "videoForensic"):
        if forbidden_domain in source_text:
            failures.append(f"生产脚本包含应用专属词：{forbidden_domain}")
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    if len(skill_text.splitlines()) > 500:
        failures.append("SKILL.md 超过 progressive disclosure 行数预算")
    required_references = {"server.md", "actions.md", "workflow.md", "knowledge.md", "troubleshooting.md"}
    linked_references = {name for name in required_references if f"references/{name}" in skill_text}
    if linked_references != required_references or "不要在普通任务中预先加载全部 references" not in skill_text:
        failures.append("SKILL.md 条件 reference 索引不完整")
    old_asset_markers = []
    for path in sorted((SKILL / "assets").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for marker in ('"clickText"', '"readiness"', '"learn"', '"domSnapshot"', '"accessibilitySnapshot"'):
            if marker in text:
                old_asset_markers.append(f"{path.name}:{marker}")
    if old_asset_markers:
        failures.append(f"assets 仍使用旧 action contract：{old_asset_markers}")
    requirements = (SKILL / "requirements.txt").read_text(encoding="utf-8")
    if "playwright==1.61.0" not in requirements:
        failures.append("Playwright runtime 未锁定到批准版本")
    agent_metadata = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "$electron-ui-verifier" not in agent_metadata:
        failures.append("agents/openai.yaml 与 skill 名称不同步")
    matrix_path = ROOT / ".github" / "workflows" / "electron-ui-verifier.yml"
    matrix_text = matrix_path.read_text(encoding="utf-8") if matrix_path.exists() else ""
    required_matrix = ("windows-latest", "ubuntu-latest", "macos-latest", 'branches: ["**"]', "run_fixture_cdp_smoke.py")
    if not matrix_text or any(marker not in matrix_text for marker in required_matrix):
        failures.append("三平台 Electron fixture workflow 缺失或触发范围不完整")
    fixture_path = SKILL / "tests" / "run_fixture_cdp_smoke.py"
    if not fixture_path.exists():
        failures.append("跨平台 fixture CDP smoke 缺失")
    else:
        try:
            ast.parse(fixture_path.read_text(encoding="utf-8"), filename=str(fixture_path))
        except SyntaxError as exc:
            failures.append(f"fixture CDP smoke 语法错误：{exc}")
    metrics["productionFiles"] = len(files)
    metrics["schemaFiles"] = len(schema_ids)
    metrics["oversized"] = oversized
    metrics["rawTransportHits"] = transport_hits
    metrics["legacyKnowledgeReader"] = store_facade.exists()
    metrics["publicScriptCount"] = len(PUBLIC_SCRIPTS)
    metrics["publicLegacyHits"] = public_legacy_hits
    metrics["skillLines"] = len(skill_text.splitlines())
    metrics["linkedReferences"] = sorted(linked_references)
    metrics["removedLegacyPaths"] = stale_paths
    metrics["platformMatrixDefined"] = bool(matrix_text)
    metrics["securityBoundaryModules"] = [path.name for path in required_security_modules if path.exists()]
    metrics["mutationBypassHits"] = bypass_hits
    result = {"ok": not failures, "failures": failures, "metrics": metrics}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
