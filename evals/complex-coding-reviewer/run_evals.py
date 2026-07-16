#!/usr/bin/env python3
"""运行 Reviewer 双 profile 的纯确定性契约评测。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "skills" / "complex-coding-reviewer" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from complex_coding_reviewer.contract import (
    CODE_LENSES,
    PLAN_LENSES,
    derive_open_counts,
    validate_receipt,
)
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


def lenses(profile: str) -> list[dict[str, Any]]:
    values = PLAN_LENSES if profile == "plan-review" else CODE_LENSES
    return [
        {
            "id": lens,
            "status": "reviewed",
            "evidence_refs": ["target:fixture"],
            "summary": f"{lens} 已完成 fixture 契约审查。",
        }
        for lens in values
    ]


def receipt(target: dict[str, Any], profile: str) -> dict[str, Any]:
    scope = (
        {
            "kind": "managed-plan",
            "task_id": target["identity"]["task_id"],
            "plan_revision": target["identity"]["plan_revision"],
        }
        if profile == "plan-review"
        else {"kind": "standalone"}
    )
    return {
        "review_id": "REV-EVAL-PLAN" if profile == "plan-review" else "REV-EVAL-CODE",
        "profile": profile,
        "scope": scope,
        "target": deepcopy(target),
        "reviewer": {
            "mode": "same-context",
            "identity": "deterministic-eval",
            "independence_claim": False,
            "capability_limits": ["fixture 只验证 contract，不声明真实审查质量。"],
        },
        "standards": [],
        "lenses": lenses(profile),
        "findings": [],
        "verdict": "passed",
        "open_counts": {"blocking": 0, "major": 0, "minor": 0, "advisory": 0, "total": 0},
        "summary": "fixture receipt 完成结构验证。",
        "limitations": ["不运行 Agent、网络或目标代码。"],
        "supersedes_review_id": None,
        "reviewed_at": "2026-07-16T00:00:00+00:00",
    }


def seeded_finding(severity: str) -> dict[str, Any]:
    return {
        "id": "FIND-001",
        "severity": severity,
        "status": "open",
        "title": "Seeded contract finding",
        "claim": "Fixture 声明一个可证伪的问题。",
        "impact": "用于验证 verdict 与计数门禁。",
        "recommendation": "根据 finding severity 产生正确门禁。",
        "evidence": [
            {
                "path": "src/service.py",
                "line": 1,
                "symbol": "value",
                "artifact_ref": None,
                "standard_ref": None,
                "detail": "seeded evidence",
            }
        ],
        "confidence": "high",
        "disposition_reason": None,
    }


def apply_mutation(value: dict[str, Any], mutation: str, root: Path) -> None:
    if mutation == "none":
        return
    if mutation == "open-minor":
        value["findings"] = [seeded_finding("minor")]
        value["open_counts"] = derive_open_counts(value["findings"])
    elif mutation == "blocked-lens":
        value["lenses"][0]["status"] = "blocked"
        value["verdict"] = "blocked"
    elif mutation == "major-forced-pass":
        value["findings"] = [seeded_finding("major")]
        value["open_counts"] = derive_open_counts(value["findings"])
    elif mutation == "missing-lens":
        value["lenses"].pop()
    elif mutation == "count-drift":
        value["findings"] = [seeded_finding("minor")]
    elif mutation == "false-independence":
        value["reviewer"]["independence_claim"] = True
    elif mutation == "stale-target":
        (root / "src" / "service.py").write_text("def value():\n    return 43\n", encoding="utf-8")
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
        value = receipt(target, case["profile"])
        apply_mutation(value, case["mutation"], root)
        actual_valid = True
        actual_code = None
        actual_verdict = None
        try:
            result = validate_receipt(
                value,
                workspace=root if case["profile"] == "code-review" else None,
                task_dir=root if case["profile"] == "plan-review" else None,
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

    skill_links = {
        "references/plan-review.md",
        "references/code-review.md",
        "references/review-workflow.md",
        "references/review-calibration.md",
        "references/risk-playbooks.md",
        "references/review-contract.md",
    }
    missing_links = sorted(link for link in skill_links if link not in texts["skill"])
    checks.append(
        {
            "id": "progressive-disclosure-links",
            "passed": not missing_links,
            "detail": f"missing={missing_links}",
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
                "id": "read-only-no-agent",
                "passed": all(
                    value in texts["skill"]
                    for value in ("只审查显式目标", "不得修改计划", "不运行 `codex exec`")
                ),
                "detail": "Reviewer 只读且不自动运行 Agent/目标。",
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
