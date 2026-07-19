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
    "ev_suggest.py", "ev_assets.py", "ev_risk.py", "ev_server.py",
    "ev_operation.py", "ev_prune.py",
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
    required_schemas = {
        "risk-receipt.schema.json",
        "operation.schema.json",
        "knowledge-decision.schema.json",
    }
    missing_schemas = sorted(name for name in required_schemas if not (SCHEMAS / name).exists())
    if len(schema_ids) < 9 or missing_schemas:
        failures.append("当前契约 schema 数量不足")
    knowledge_schema = json.loads((SCHEMAS / "knowledge.schema.json").read_text(encoding="utf-8"))
    knowledge_properties = knowledge_schema.get("properties", {})
    sealed_format = knowledge_properties.get("format", {}).get("const")
    if sealed_format != "electron-verifier-sealed":
        failures.append("knowledge schema 未固定 sealed direct-cutover format")
    required_security_modules = (
        PACKAGE / "sensitivity.py",
        PACKAGE / "risk_authorization.py",
        PACKAGE / "operations.py",
        PACKAGE / "compatibility.py",
        PACKAGE / "asset_execution.py",
        PACKAGE / "run_context.py",
        PACKAGE / "paths.py",
        PACKAGE / "retention.py",
        PACKAGE / "retention_policy.py",
    )
    missing_security_modules = [path.name for path in required_security_modules if not path.exists()]
    if missing_security_modules:
        failures.append(f"安全、安装或 operation 边界模块缺失：{missing_security_modules}")
    legacy_knowledge_markers = (
        '"canonicalDir"',
        "electron-verifier-canonical",
        'paths["canonical"]',
        "def persist(",
    )
    legacy_knowledge_hits = [marker for marker in legacy_knowledge_markers if marker in package_text]
    if legacy_knowledge_hits:
        failures.append(f"生产代码仍包含旧 canonical truth 路径：{legacy_knowledge_hits}")
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
        for marker in (
            "ev_knowledge_store",
            "ev_knowledge_extract",
            "supplemental_actions",
            "ev_asset_runner",
            "executable_from_asset",
        ):
            if marker in text:
                public_legacy_hits.append(f"{name}:{marker}")
    if public_parse_failures:
        failures.append(f"公共 CLI 缺失或语法错误：{public_parse_failures}")
    if public_legacy_hits:
        failures.append(f"公共 CLI 仍依赖旧知识路径：{public_legacy_hits}")
    id_only_clis = ("ev_action.py", "ev_workflow.py", "ev_risk.py")
    missing_id_handoff = [
        name
        for name in id_only_clis
        if 'payload["assetId"]' not in (SKILL / "scripts" / name).read_text(encoding="utf-8")
    ]
    if missing_id_handoff:
        failures.append(f"资产复用 CLI 未把 assetId 原样交给服务端：{missing_id_handoff}")
    removed_paths = (
        "ev_knowledge_store.py", "ev_knowledge_extract.py", "ev_learn.py", "ev_promote.py",
        "ev_asset_extract.py", "ev_asset_runner.py", "ev_export_workflow.py",
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
    reference_text = "\n".join(
        (SKILL / "references" / name).read_text(encoding="utf-8") for name in sorted(required_references)
    )
    stale_doc_markers = [
        marker
        for marker in ("knowledge/canonical", "canonical 原子提交、derived 单事务更新、sealed decision")
        if marker in skill_text or marker in reference_text
    ]
    if stale_doc_markers:
        failures.append(f"Skill 文档仍描述旧知识布局或激活顺序：{stale_doc_markers}")
    required_doc_markers = (
        "knowledge/objects",
        "knowledge/decisions",
        "sealed approved decision",
        "ev_operation.py",
        "ev_risk.py",
        "ev_prune.py",
        "PYTHONDONTWRITEBYTECODE=1",
    )
    missing_doc_markers = [
        marker for marker in required_doc_markers if marker not in skill_text and marker not in reference_text
    ]
    if missing_doc_markers:
        failures.append(f"Skill 文档未覆盖 current 公共契约：{missing_doc_markers}")
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
    required_matrix = (
        "windows-latest",
        "ubuntu-latest",
        "macos-latest",
        'branches: ["**"]',
        "run_fixture_cdp_smoke.py",
        "run_portability_retention.py",
        "run_retrieval_benchmark.py",
        ".harness/electron-ui-verifier-ci",
    )
    if not matrix_text or any(marker not in matrix_text for marker in required_matrix):
        failures.append("三平台 Electron fixture workflow 缺失或触发范围不完整")
    persistence_markers = (
        "actions/upload-artifact",
        "actions/download-artifact",
        "actions/cache",
        "cache:",
        "retention-days:",
    )
    present_persistence = [marker for marker in persistence_markers if marker in matrix_text]
    if present_persistence:
        failures.append(f"Electron workflow 不得持久化 artifact 或 cache：{present_persistence}")
    if "runner.temp" in matrix_text:
        failures.append("Electron workflow 仍把受管 fixture/eval 输出写到仓库外 runner.temp")
    fixture_path = SKILL / "tests" / "run_fixture_cdp_smoke.py"
    fixture_support = SKILL / "tests" / "public_contract_support.py"
    fixture_internal_hits: list[str] = []
    missing_fixture_markers: list[str] = []
    if not fixture_path.exists():
        failures.append("跨平台 fixture CDP smoke 缺失")
    else:
        try:
            fixture_text = fixture_path.read_text(encoding="utf-8")
            ast.parse(fixture_text, filename=str(fixture_path))
        except SyntaxError as exc:
            failures.append(f"fixture CDP smoke 语法错误：{exc}")
        else:
            forbidden_fixture_markers = (
                "PlaywrightCdpDriver",
                "RunService",
                "SessionManager",
                "electron_verifier.",
            )
            fixture_internal_hits = [marker for marker in forbidden_fixture_markers if marker in fixture_text]
            if fixture_internal_hits:
                failures.append(f"公共 fixture 仍直接调用 verifier 内部实现：{fixture_internal_hits}")
            required_fixture_markers = (
                "ManagedVerifier",
                "ev_probe.py",
                "/sessions/attach",
                "ev_operation.py",
                "ev_persist.py",
                "ev_knowledge.py",
                "ev_assets.py",
                "--workflow-id",
                '"cancel"',
                "installImmutable",
            )
            missing_fixture_markers = [marker for marker in required_fixture_markers if marker not in fixture_text]
            if missing_fixture_markers:
                failures.append(f"公共 fixture 未覆盖完整用户入口：{missing_fixture_markers}")
    if not fixture_support.exists():
        failures.append("公共 fixture 复制安装/process-manager 支撑缺失")
        support_text = ""
    else:
        support_text = fixture_support.read_text(encoding="utf-8")
        try:
            ast.parse(support_text, filename=str(fixture_support))
        except SyntaxError as exc:
            failures.append(f"公共 fixture 支撑语法错误：{exc}")
        required_support_markers = (
            "shutil.copytree",
            "pm_manager.py",
            "pm_session.py",
            "pm_start.py",
            "pm_stop.py",
            "--session-id",
            "--stop-manager-if-idle",
            "renew_session",
            "sessionClose",
            "guarded_harness_path",
            "install_digest",
        )
        missing_support_markers = [marker for marker in required_support_markers if marker not in support_text]
        if missing_support_markers:
            failures.append(f"公共 fixture 支撑未闭合复制安装或进程生命周期：{missing_support_markers}")
        forbidden_support_markers = (
            "manager_started",
            '"pm_manager.py", "start"',
            "pm_health.py",
            "pm_shutdown.py",
            "manager_offline",
        )
        support_legacy_hits = [
            marker for marker in forbidden_support_markers if marker in support_text
        ]
        if support_legacy_hits:
            failures.append(f"公共 fixture 支撑残留旧 Process Manager 契约：{support_legacy_hits}")
    termous_paths = (
        SKILL / "tests" / "run_termous_smoke.py",
        SKILL / "tests" / "termous_contract_support.py",
    )
    termous_text = "\n".join(
        path.read_text(encoding="utf-8") for path in termous_paths if path.exists()
    )
    missing_termous_files = [path.name for path in termous_paths if not path.exists()]
    if missing_termous_files:
        failures.append(f"Termous 公共契约模块缺失：{missing_termous_files}")
    termous_internal_hits = [
        marker
        for marker in (
            "subprocess.Popen",
            "taskkill",
            "VerifierApplication",
            "_bind_server",
            "electron_verifier.",
            "threading.Thread",
        )
        if marker in termous_text
    ]
    if termous_internal_hits:
        failures.append(f"Termous smoke 仍绕过统一公共生命周期：{termous_internal_hits}")
    missing_termous_markers = [
        marker
        for marker in (
            "ManagedVerifier",
            "start_managed_service",
            "stop_managed_service",
            "guarded_harness_path",
            "wait_operation",
            "--no-learn",
            '"processOwnership": "process-manager"',
        )
        if marker not in termous_text and marker not in support_text
    ]
    if missing_termous_markers:
        failures.append(f"Termous smoke 未覆盖 current 公共契约：{missing_termous_markers}")
    for termous_path in termous_paths:
        if termous_path.exists():
            try:
                ast.parse(termous_path.read_text(encoding="utf-8"), filename=str(termous_path))
            except SyntaxError as exc:
                failures.append(f"Termous smoke 语法错误：{exc}")
    metrics["productionFiles"] = len(files)
    metrics["schemaFiles"] = len(schema_ids)
    metrics["oversized"] = oversized
    metrics["rawTransportHits"] = transport_hits
    metrics["legacyKnowledgeReader"] = store_facade.exists()
    metrics["publicScriptCount"] = len(PUBLIC_SCRIPTS)
    metrics["publicLegacyHits"] = public_legacy_hits
    metrics["idOnlyAssetHandoff"] = not missing_id_handoff
    metrics["skillLines"] = len(skill_text.splitlines())
    metrics["linkedReferences"] = sorted(linked_references)
    metrics["removedLegacyPaths"] = stale_paths
    metrics["platformMatrixDefined"] = bool(matrix_text)
    metrics["publicFixtureInternalHits"] = fixture_internal_hits if fixture_path.exists() else []
    metrics["missingFixtureMarkers"] = missing_fixture_markers if fixture_path.exists() else []
    metrics["missingFixtureSupportMarkers"] = missing_support_markers if fixture_support.exists() else []
    metrics["termousInternalHits"] = termous_internal_hits
    metrics["missingTermousMarkers"] = missing_termous_markers
    metrics["staleDocMarkers"] = stale_doc_markers
    metrics["missingDocMarkers"] = missing_doc_markers
    metrics["securityBoundaryModules"] = [path.name for path in required_security_modules if path.exists()]
    metrics["mutationBypassHits"] = bypass_hits
    metrics["missingRequiredSchemas"] = missing_schemas
    metrics["knowledgeFormat"] = sealed_format
    metrics["legacyKnowledgeMarkers"] = legacy_knowledge_hits
    metrics["knowledgeLayoutModules"] = [
        name
        for name in ("canonical_store.py", "knowledge_index.py", "knowledge_reset.py")
        if (PACKAGE / name).exists()
    ]
    result = {"ok": not failures, "failures": failures, "metrics": metrics}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
