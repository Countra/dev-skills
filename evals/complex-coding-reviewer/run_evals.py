#!/usr/bin/env python3
"""运行 Reviewer 双 profile 的纯确定性契约评测。"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import stat
import sys
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_ROOT = REPO_ROOT / "evals"
SCRIPT_ROOT = REPO_ROOT / "skills" / "complex-coding-reviewer" / "scripts"
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from review_fixture import assemble_fixture_receipt, sync_fixture_semantic
from complex_coding_reviewer.contract import (
    CODE_LENSES,
    PLAN_LENSES,
    derive_open_counts,
    validate_receipt,
)
from complex_coding_reviewer.context import RISK_IDS, build_context_target
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.target import (
    build_file_manifest_target,
    build_plan_bundle_target,
)


SKILL_ROOT = REPO_ROOT / "skills" / "complex-coding-reviewer"
EXPECTED_RISK_IDS = {
    "RISK-SECURITY-PRIVACY",
    "RISK-CONCURRENCY-INTEGRITY",
    "RISK-PERFORMANCE-RESOURCES",
    "RISK-API-DATA-COMPATIBILITY",
    "RISK-UI-ACCESSIBILITY-I18N",
    "RISK-REMOVAL-DEPENDENCIES",
}
BANNED_RUNTIME_IMPORTS = {
    "aiohttp",
    "agents",
    "anthropic",
    "cohere",
    "ftplib",
    "google",
    "http",
    "httpx",
    "litellm",
    "mistralai",
    "multiprocessing",
    "ollama",
    "openai",
    "replicate",
    "requests",
    "smtplib",
    "socket",
    "subprocess",
    "telnetlib",
    "transformers",
    "urllib",
    "urllib3",
    "webbrowser",
}
BANNED_RUNTIME_CALLS = {
    "__import__",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "importlib.import_module",
    "multiprocessing.Process",
    "os.fork",
    "os.popen",
    "os.startfile",
    "os.system",
    "webbrowser.open",
    "webbrowser.open_new",
    "webbrowser.open_new_tab",
}
RUNTIME_NEGATIVE_PROBES = {
    "network-standard-library": "import urllib.request\nurllib.request.urlopen('https://example.invalid')\n",
    "derived-process": "import multiprocessing\nmultiprocessing.Process(target=print).start()\n",
    "dynamic-import": "import importlib\nimportlib.import_module('subprocess')\n",
    "model-runtime": "import litellm\nlitellm.completion(model='x', messages=[])\n",
}
CI_REQUIRED_SNIPPETS = (
    'branches: ["**"]',
    "os: [windows-latest, ubuntu-latest, macos-latest]",
    "run_semantic_oracle.py --self-test",
    "run_evals.py --static-contract-only",
    "run_observation_packet.py --validate-only",
    "skills/skill-evaluation-lab/scripts/se_check.py",
    "cross_skill_regression.py --include-reviewer",
)
CI_FORBIDDEN_SNIPPETS = (
    "${{ secrets.",
    "branches-ignore:",
    "codex exec",
    "run_semantic_oracle.py --input",
    "--prepare-dir",
    "continue-on-error: true",
    "Invoke-WebRequest",
    "curl ",
    "wget ",
)
CURRENT_ONLY_FORBIDDEN_TERMS = (
    "critique_ref",
    "development_quality",
    "legacy_receipt",
    "receipt_schema_version",
    "review_payload",
    "review_report",
    "review_schema_version",
)
REVIEWER_ONLY_FORBIDDEN_TERMS = ("schema_version",)


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def runtime_tree_violations(tree: ast.AST, label: str) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in BANNED_RUNTIME_IMPORTS:
                    violations.append(f"{label}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if node.level == 0 and root in BANNED_RUNTIME_IMPORTS:
                violations.append(f"{label}:{node.lineno}: from {node.module}")
        elif isinstance(node, ast.Call):
            call = dotted_name(node.func)
            if call in BANNED_RUNTIME_CALLS or call.startswith(("os.exec", "os.spawn")):
                violations.append(f"{label}:{node.lineno}: {call}")
    return violations


def runtime_entry_violations(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(runtime_tree_violations(tree, path.name))
    return violations


def runtime_negative_probe_failures() -> list[str]:
    failures: list[str] = []
    for probe_id, source in RUNTIME_NEGATIVE_PROBES.items():
        tree = ast.parse(source, filename=f"<{probe_id}>")
        if not runtime_tree_violations(tree, probe_id):
            failures.append(probe_id)
    return failures


def current_only_legacy_hits(documents: list[tuple[str, str]]) -> list[str]:
    hits: list[str] = []
    for relative, content in documents:
        terms = CURRENT_ONLY_FORBIDDEN_TERMS
        if relative.startswith("skills/complex-coding-reviewer/"):
            terms += REVIEWER_ONLY_FORBIDDEN_TERMS
        for term in terms:
            if term in content:
                hits.append(f"{relative}:{term}")
    return hits


def repository_contract_checks() -> list[dict[str, Any]]:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "planner-executor.yml"
    readme_path = REPO_ROOT / "README.md"
    changelog_path = REPO_ROOT / "CHANGELOG.md"
    contract_paths = [readme_path]
    for skill_name in (
        "complex-coding-reviewer",
        "complex-coding-planner",
        "complex-coding-executor",
    ):
        skill_root = REPO_ROOT / "skills" / skill_name
        contract_paths.append(skill_root / "SKILL.md")
        contract_paths.extend(sorted((skill_root / "references").glob("*.md")))

    required_paths = [workflow_path, changelog_path, *contract_paths]
    missing_paths = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in required_paths
        if not path.is_file()
    )
    workflow = workflow_path.read_text(encoding="utf-8") if workflow_path.is_file() else ""
    readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
    changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""

    missing_ci = [snippet for snippet in CI_REQUIRED_SNIPPETS if snippet not in workflow]
    forbidden_ci = [snippet for snippet in CI_FORBIDDEN_SNIPPETS if snippet in workflow]
    all_branches = workflow.count('branches: ["**"]') == 2

    readme_markers = (
        "requirement/risk/path coverage",
        "verification gaps",
        "spec compliance",
        "delegated-review",
        "dispatch-bound",
        "`not_observed`",
        "--prepare-dir",
        "current checker",
        "attestation",
    )
    changelog_markers = (
        "target/context digest",
        "spec-first",
        "observation packet",
        "`not_observed`",
        "current-only breaking contract",
        "attestation",
    )
    missing_public_markers = [
        *(f"README:{value}" for value in readme_markers if value not in readme),
        *(f"CHANGELOG:{value}" for value in changelog_markers if value not in changelog),
    ]

    contract_documents: list[tuple[str, str]] = []
    for path in contract_paths:
        if not path.is_file():
            continue
        contract_documents.append(
            (
                path.relative_to(REPO_ROOT).as_posix(),
                path.read_text(encoding="utf-8"),
            )
        )
    legacy_hits = current_only_legacy_hits(contract_documents)
    probe_hits = current_only_legacy_hits(
        [
            (
                "skills/complex-coding-planner/references/example-schema.md",
                "schema_version",
            ),
            (
                "skills/complex-coding-reviewer/references/review-contract.md",
                "schema_version",
            ),
        ]
    )
    expected_probe_hits = [
        "skills/complex-coding-reviewer/references/review-contract.md:schema_version"
    ]

    return [
        {
            "id": "repository-ci-contract",
            "passed": not missing_paths and all_branches and not missing_ci and not forbidden_ci,
            "detail": (
                f"missing_paths={missing_paths}, all_branches={all_branches}, "
                f"missing={missing_ci}, forbidden={forbidden_ci}"
            ),
        },
        {
            "id": "public-capability-boundaries",
            "passed": not missing_public_markers,
            "detail": f"missing={missing_public_markers}",
        },
        {
            "id": "current-only-review-contract",
            "passed": not missing_paths and not legacy_hits,
            "detail": f"legacy_hits={legacy_hits}",
        },
        {
            "id": "current-only-scanner-probes",
            "passed": probe_hits == expected_probe_hits,
            "detail": f"expected={expected_probe_hits}, actual={probe_hits}",
        },
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def create_case_root(parent: Path) -> Path:
    path = parent / f"case-{uuid.uuid4().hex}"
    path.mkdir(mode=0o777)
    return path


def remove_case_root(path: Path) -> None:
    def remove_readonly(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onexc=remove_readonly)


def create_plan_target(root: Path) -> dict[str, Any]:
    write_json(
        root / "plan-contract.json",
        {
            "task_id": "reviewer-eval-plan",
            "plan_revision": 1,
            "artifacts": [
                {
                    "id": "ART-01",
                    "kind": "architecture",
                    "path": "artifacts/architecture.md",
                    "required": True,
                    "approval_included": True,
                }
            ],
        },
    )
    (root / "execution-plan.md").write_text("# Eval Plan\n\nGOAL-01 REQ-01 AC-01\n", encoding="utf-8")
    (root / "artifacts").mkdir()
    (root / "artifacts" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    return build_plan_bundle_target(root)


def create_code_target(root: Path) -> dict[str, Any]:
    (root / "src").mkdir()
    (root / "src" / "service.py").write_text("def value():\n    return 42\n", encoding="utf-8")
    return build_file_manifest_target(root, ["src/service.py"], label="reviewer-eval")


def lenses(profile: str, evidence_ref: str) -> list[dict[str, Any]]:
    values = PLAN_LENSES if profile == "plan-review" else CODE_LENSES
    return [
        {
            "id": lens,
            "status": "reviewed",
            "evidence_refs": [evidence_ref],
            "summary": f"{lens} 已完成 fixture 契约审查。",
        }
        for lens in values
    ]


def receipt(target: dict[str, Any], profile: str, root: Path) -> dict[str, Any]:
    scope = (
        {
            "kind": "managed-plan",
            "task_id": target["identity"]["task_id"],
            "plan_revision": target["identity"]["plan_revision"],
        }
        if profile == "plan-review"
        else {"kind": "standalone"}
    )
    review_id = "REV-EVAL-PLAN" if profile == "plan-review" else "REV-EVAL-CODE"
    brief_relative = "artifacts/review-brief.json" if profile == "plan-review" else "review-brief.json"
    write_json(
        root / brief_relative,
        {
            "profile": profile,
            "scope": scope,
            "summary": "验证 deterministic eval contract。",
            "requirement_refs": ["REQ-EVAL"],
            "constraint_refs": [],
            "claim_refs": [],
            "requested_risk_focus": [],
            "created_at": "2026-07-16T00:00:00+00:00",
        },
    )
    context_entries = [(brief_relative, "brief")]
    context_entries.extend(
        (
            str(item["path"]),
            "requirement" if profile == "plan-review" else "adjacent-code",
        )
        for item in target["manifest"]
        if item["state"] == "present" and item["path"] != brief_relative
    )
    context = build_context_target(
        root,
        root_kind="task-dir" if profile == "plan-review" else "workspace",
        label=f"{review_id.lower()}-context",
        entries=context_entries,
    )
    target_paths = [str(item["path"]) for item in target["manifest"]]
    semantic = {
        "kind": "review-semantic-result",
        "review_id": review_id,
        "profile": profile,
        "scope": scope,
        "target_digest": target["digest"],
        "context_digest": context["digest"],
        "standards": [],
        "coverage": {
            "target_paths": [
                {
                    "path": path,
                    "status": "reviewed",
                    "reason": "deterministic fixture 已覆盖该路径。",
                    "gap_ids": [],
                }
                for path in target_paths
            ],
            "requirement_checks": [
                {
                    "id": "REQ-EVAL",
                    "status": "satisfied",
                    "evidence_refs": [brief_relative],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "fixture 提供了直接证据。",
                }
            ],
            "risk_checks": [
                {
                    "id": risk_id,
                    "status": "not-triggered",
                    "trigger": "fixture 未包含该风险触发面。",
                    "evidence_refs": [brief_relative],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "已检查触发条件，当前不适用。",
                }
                for risk_id in RISK_IDS
            ],
            "context_expansions": [],
        },
        "lenses": lenses(profile, brief_relative),
        "strengths": [],
        "findings": [],
        "verification_gaps": [],
        "verdict": "passed",
        "open_counts": {"blocking": 0, "major": 0, "minor": 0, "advisory": 0, "total": 0},
        "summary": "fixture receipt 完成结构验证。",
        "limitations": ["不运行 Agent、网络或目标代码。"],
        "supersedes_review_id": None,
        "reviewed_at": "2026-07-16T00:00:00+00:00",
    }
    return assemble_fixture_receipt(
        root=root,
        review_root=root / "reviews",
        target=target,
        context=context,
        semantic=semantic,
        policy="conditional",
        delegated=False,
    )


def seeded_finding(severity: str, evidence_path: str) -> dict[str, Any]:
    return {
        "id": "FIND-001",
        "category": "correctness",
        "origin": {"review_id": None, "finding_id": None},
        "severity": severity,
        "status": "open",
        "title": "Seeded contract finding",
        "claim": "Fixture 声明一个可证伪的问题。",
        "impact": "用于验证 verdict 与计数门禁。",
        "recommendation": "根据 finding severity 产生正确门禁。",
        "evidence": [
            {
                "path": evidence_path,
                "line": 1,
                "symbol": "value",
                "artifact_ref": None,
                "standard_ref": None,
                "detail": "seeded evidence",
                "claim_source": "read",
            }
        ],
        "confidence": "high",
        "disposition_reason": None,
    }


def apply_mutation(value: dict[str, Any], mutation: str, root: Path) -> None:
    if mutation == "none":
        return
    if mutation == "open-minor":
        value["findings"] = [seeded_finding("minor", value["target"]["manifest"][0]["path"])]
        value["open_counts"] = derive_open_counts(value["findings"])
        value["coverage"]["requirement_checks"][0].update(
            {
                "status": "violated",
                "finding_ids": ["FIND-001"],
                "summary": "fixture requirement 存在 minor finding。",
            }
        )
    elif mutation == "blocked-lens":
        value["lenses"][0]["status"] = "blocked"
        value["verdict"] = "blocked"
    elif mutation == "major-forced-pass":
        value["findings"] = [seeded_finding("major", value["target"]["manifest"][0]["path"])]
        value["open_counts"] = derive_open_counts(value["findings"])
        value["coverage"]["requirement_checks"][0].update(
            {
                "status": "violated",
                "finding_ids": ["FIND-001"],
                "summary": "fixture requirement 存在 major finding。",
            }
        )
    elif mutation == "missing-lens":
        value["lenses"].pop()
    elif mutation == "count-drift":
        value["findings"] = [seeded_finding("minor", value["target"]["manifest"][0]["path"])]
        value["coverage"]["requirement_checks"][0].update(
            {
                "status": "violated",
                "finding_ids": ["FIND-001"],
                "summary": "fixture requirement 存在未计数 finding。",
            }
        )
    elif mutation == "false-independence":
        value["reviewer"]["independence_claim"] = True
    elif mutation == "stale-target":
        (root / "src" / "service.py").write_text("def value():\n    return 43\n", encoding="utf-8")
    elif mutation == "stale-context":
        brief = next(item for item in value["context"]["manifest"] if item["role"] == "brief")
        brief_path = root / brief["path"]
        brief_path.write_text(brief_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif mutation == "unbound-lens-evidence":
        value["lenses"][0]["evidence_refs"] = ["outside.py"]
    elif mutation == "unknown-root-field":
        value["noncanonical"] = True
    elif mutation == "plan-target-mismatch":
        plan_root = root / "plan"
        plan_root.mkdir()
        value["target"] = create_plan_target(plan_root)
    else:
        raise ValueError(f"未知 mutation：{mutation}")


def evaluate_case(case: dict[str, Any], parent: Path) -> dict[str, Any]:
    root = create_case_root(parent)
    try:
        target = create_plan_target(root) if case["profile"] == "plan-review" else create_code_target(root)
        value = receipt(target, case["profile"], root)
        apply_mutation(value, case["mutation"], root)
        sync_fixture_semantic(value, root / "reviews")
        actual_valid = True
        actual_code = None
        actual_verdict = None
        try:
            result = validate_receipt(
                value,
                review_root=root / "reviews",
                workspace=root if case["profile"] == "code-review" else None,
                task_dir=root if case["profile"] == "plan-review" else None,
                expected_dispatch_policy="conditional",
            )
            actual_verdict = result["verdict"]
        except ReviewError as exc:
            actual_valid = False
            actual_code = exc.code
        expected_code = case.get("expected_code")
        expected_verdict = case.get("expected_verdict")
        passed = (
            actual_valid == case["expected_valid"]
            and (expected_code is None or actual_code == expected_code)
            and (expected_verdict is None or actual_verdict == expected_verdict)
        )
        return {
            "id": case["id"],
            "profile": case["profile"],
            "category": case["category"],
            "mutation": case["mutation"],
            "expected_valid": case["expected_valid"],
            "actual_valid": actual_valid,
            "expected_code": expected_code,
            "actual_code": actual_code,
            "expected_verdict": expected_verdict,
            "actual_verdict": actual_verdict,
            "passed": passed,
        }
    finally:
        remove_case_root(root)


def static_contract_report() -> dict[str, Any]:
    """验证 Skill 的公开能力边界和渐进披露链接。"""

    required_files = {
        "skill": SKILL_ROOT / "SKILL.md",
        "plan": SKILL_ROOT / "references" / "plan-review.md",
        "code": SKILL_ROOT / "references" / "code-review.md",
        "workflow": SKILL_ROOT / "references" / "review-workflow.md",
        "calibration": SKILL_ROOT / "references" / "review-calibration.md",
        "risks": SKILL_ROOT / "references" / "risk-playbooks.md",
        "contract": SKILL_ROOT / "references" / "review-contract.md",
        "dispatch": SKILL_ROOT / "references" / "review-dispatch.md",
        "troubleshooting": SKILL_ROOT / "references" / "troubleshooting.md",
    }
    semantic_assets = {
        "oracle": Path(__file__).with_name("run_semantic_oracle.py"),
        "observation_runner": Path(__file__).with_name("run_observation_packet.py"),
        "observation_suite": Path(__file__).with_name("observation-suite.json"),
        "corpus": Path(__file__).with_name("semantic_cases") / "corpus.json",
    }
    texts: dict[str, str] = {}
    checks: list[dict[str, Any]] = []
    for name, path in required_files.items():
        exists = path.is_file()
        checks.append(
            {
                "id": f"file-{name}",
                "passed": exists,
                "detail": str(path.relative_to(REPO_ROOT)),
            }
        )
        texts[name] = path.read_text(encoding="utf-8") if exists else ""
    missing_semantic_assets = sorted(
        name for name, path in semantic_assets.items() if not path.is_file()
    )
    checks.append(
        {
            "id": "semantic-assets",
            "passed": not missing_semantic_assets,
            "detail": f"missing={missing_semantic_assets}",
        }
    )

    skill_links = {
        "references/plan-review.md",
        "references/code-review.md",
        "references/review-workflow.md",
        "references/review-calibration.md",
        "references/risk-playbooks.md",
        "references/review-contract.md",
        "references/review-dispatch.md",
        "references/troubleshooting.md",
    }
    missing_links = sorted(link for link in skill_links if link not in texts["skill"])
    checks.append(
        {
            "id": "progressive-disclosure-links",
            "passed": not missing_links,
            "detail": f"missing={missing_links}",
        }
    )
    runtime_paths = [
        semantic_assets["oracle"],
        semantic_assets["observation_runner"],
        SKILL_ROOT / "scripts" / "review_dispatch.py",
        SKILL_ROOT / "scripts" / "review_assemble.py",
        SKILL_ROOT / "scripts" / "review_validate.py",
        SKILL_ROOT / "scripts" / "review_render.py",
    ]
    runtime_violations = (
        runtime_entry_violations(runtime_paths)
        if all(path.is_file() for path in runtime_paths)
        else ["semantic runtime file missing"]
    )
    checks.append(
        {
            "id": "semantic-no-derived-runtime",
            "passed": not runtime_violations,
            "detail": f"violations={runtime_violations}",
        }
    )
    probe_failures = runtime_negative_probe_failures()
    checks.append(
        {
            "id": "semantic-runtime-negative-probes",
            "passed": not probe_failures,
            "detail": f"undetected_probes={probe_failures}",
        }
    )
    observation_text = (
        semantic_assets["observation_runner"].read_text(encoding="utf-8")
        if semantic_assets["observation_runner"].is_file()
        else ""
    )
    checks.append(
        {
            "id": "layered-observation-claims",
            "passed": all(
                value in observation_text
                for value in (
                    '"deterministic_contract": "separate_evidence"',
                    '"same_context_semantic": "separate_evidence"',
                    '"fresh_context_semantic": "not_observed"',
                    '"formal_review_agent_count": 1',
                    '"agent_close_status": "closed"',
                )
            ),
            "detail": "三层证据必须独立报告，fresh-context 默认未观察。",
        }
    )
    checks.extend(
        [
            {
                "id": "two-profile-boundary",
                "passed": "不创建第三个通用 profile" in texts["skill"],
                "detail": "入口必须保持 plan-review/code-review 双 profile。",
            },
            {
                "id": "plan-professional-sequence",
                "passed": all(
                    value in texts["plan"]
                    for value in ("需求符合性", "核心设计", "verification gap", "clean review")
                ),
                "detail": "plan-review 需要 spec、设计、gap 与 clean evidence。",
            },
            {
                "id": "code-spec-first",
                "passed": all(
                    value in texts["code"]
                    for value in ("Spec compliance first", "missing", "extra", "misunderstood")
                ),
                "detail": "code-review 必须先验证需求符合性。",
            },
            {
                "id": "coordinator-agent-boundary",
                "passed": all(
                    value in texts["skill"]
                    for value in (
                        "只审查显式目标",
                        "review-coordinator",
                        "delegated-reviewer",
                        "不得调用 `codex exec`",
                        "agent_calls=0",
                    )
                ),
                "detail": "只有 coordinator 使用宿主 Agent 工具，脚本与 delegated reviewer 保持边界。",
            },
            {
                "id": "dispatch-policy-and-lifecycle",
                "passed": all(
                    value in texts["dispatch"]
                    for value in (
                        "`strict`",
                        "`conditional`",
                        "`disabled`",
                        "fork_context=false",
                        "close_agent",
                        "send_input",
                        "可创建一次 attempt=2",
                    )
                ),
                "detail": "dispatch reference 必须覆盖策略、隔离、关闭和有界重试。",
            },
            {
                "id": "dispatch-package-budget",
                "passed": (
                    "512 KiB" in texts["dispatch"]
                    and "省略 `--package`" in texts["dispatch"]
                    and "package 超限不等于正式 target 必须拆分" in texts["workflow"]
                ),
                "detail": "Agent-bound package 必须有独立硬预算，超限时保留完整 target。",
            },
            {
                "id": "dispatch-timeout-class",
                "passed": all(
                    value in texts["dispatch"]
                    for value in (
                        "`timeout_class=standard`",
                        "`timeout_class=high-risk`",
                        "`requested_risk_focus`",
                        "不改变 policy 或 verdict",
                        "单次 `wait_agent` 不超过 60 秒",
                        "轮询不重置总等待预算",
                    )
                ),
                "detail": "等待预算必须从冻结风险声明派生、分段可观察，且不能改变派发策略或结论。",
            },
            {
                "id": "dispatch-provenance-hardening",
                "passed": all(
                    value in texts["dispatch"]
                    for value in (
                        "`workspace_root`",
                        "`task_dir_root`",
                        "Reviewer Skill 路径与 SHA-256",
                        "优先于 Reviewer Skill",
                        "不能把",
                        "不得运行测试、构建、目标程序、网络请求",
                        "same-context fallback",
                        "显式传入 expected policy",
                        "`prepared_at <= started_at",
                    )
                )
                and "预先冻结 `send_input`" in texts["contract"]
                and "确定性重建全部内容" in texts["contract"],
                "detail": "Skill 摘要、根路径、package、repair、重试、policy 与时间线必须形成封闭 provenance。",
            },
            {
                "id": "full-rereview",
                "passed": "完整复审" in texts["workflow"] and "前序 finding" in texts["workflow"],
                "detail": "修复后必须完整复审并交代前序 finding。",
            },
        ]
    )
    actual_risk_ids = set(re.findall(r"`(RISK-[A-Z0-9-]+)`", texts["risks"]))
    checks.append(
        {
            "id": "conditional-risk-playbooks",
            "passed": actual_risk_ids == EXPECTED_RISK_IDS and "默认全量运行" in texts["risks"],
            "detail": f"risk_ids={sorted(actual_risk_ids)}",
        }
    )
    checks.extend(repository_contract_checks())
    return {
        "suite": "complex-coding-reviewer-static-contract",
        "passed": sum(item["passed"] for item in checks),
        "failed": sum(not item["passed"] for item in checks),
        "total": len(checks),
        "claim_boundaries": {
            "semantic_review_quality_observed": False,
            "agent_calls": 0,
            "network_calls": 0,
            "target_executions": 0,
        },
        "checks": checks,
    }


def emit_report(report: dict[str, Any], output_path: Path | None) -> int:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 reviewer deterministic eval")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("manifest.json"))
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=REPO_ROOT / ".harness" / "test-tmp" / "reviewer-evals",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--static-contract-only",
        action="store_true",
        help="只验证 Skill 能力边界与渐进披露，不运行 fixture contract cases",
    )
    args = parser.parse_args()
    if args.static_contract_only:
        return emit_report(static_contract_report(), args.output)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = [evaluate_case(case, args.work_dir) for case in manifest["cases"]]
    report = {
        "suite": "complex-coding-reviewer",
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "total": len(results),
        "metrics": {
            "plan_cases": sum(item["profile"] == "plan-review" for item in results),
            "code_cases": sum(item["profile"] == "code-review" for item in results),
            "clean_cases": sum(item["category"] == "clean" for item in results),
            "near_miss_cases": sum(item["category"] == "near-miss" for item in results),
            "known_defect_cases": sum(item["category"] == "known-defect" for item in results),
        },
        "claim_boundaries": {
            "semantic_review_quality_observed": False,
            "agent_calls": 0,
            "network_calls": 0,
            "target_executions": 0,
        },
        "results": results,
    }
    return emit_report(report, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
