#!/usr/bin/env python3
"""Skill Evaluation Lab 的纯静态、自包含回归评测。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = REPO_ROOT / "skills" / "skill-evaluation-lab" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import (
    SCHEMA_VERSION,
    SEMANTIC_DIMENSIONS,
    load_json_document,
    load_suite,
    validate_semantic_review,
)
from skill_evaluation_lab.errors import ContractError
from skill_evaluation_lab.inventory import scan_repository
from skill_evaluation_lab.observations import import_observations
from skill_evaluation_lab.output import write_new_json, write_new_text
from skill_evaluation_lab.packets import build_packet, suite_receipt, write_packet
from skill_evaluation_lab.paths import resolve_output, resolve_workspace
from skill_evaluation_lab.reports import build_report, render_markdown, verify_current_sources
from skill_evaluation_lab.static_checks import evaluate_skill


EXPECTED_PUBLIC_SCRIPTS = [
    "se_check.py",
    "se_import.py",
    "se_inventory.py",
    "se_prepare.py",
    "se_report.py",
    "se_validate.py",
]


def _assertion(assertion_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": assertion_id, "passed": passed, "detail": detail}


def _require_passed(assertions: list[dict[str, Any]]) -> None:
    failures = [item for item in assertions if not item["passed"]]
    if failures:
        raise ContractError(
            "self-eval assertion 失败",
            code="SELF_EVAL_FAILED",
            path="$.assertions",
            guidance=str(failures),
        )


def _inventory_eval(work_dir: Path) -> dict[str, Any]:
    inventory = scan_repository(REPO_ROOT)
    by_name = {item["name"]: item for item in inventory["skills"]}
    lab = by_name.get("skill-evaluation-lab")
    assertions = [
        _assertion("lab-discovered", lab is not None, "inventory 必须发现 skill-evaluation-lab"),
        _assertion(
            "lab-valid",
            bool(lab and lab["valid"]),
            "skill-evaluation-lab metadata 必须有效",
        ),
        _assertion(
            "public-cli-boundary",
            bool(lab and lab["public_scripts"] == EXPECTED_PUBLIC_SCRIPTS),
            f"expected={EXPECTED_PUBLIC_SCRIPTS}; actual={lab['public_scripts'] if lab else None}",
        ),
        _assertion(
            "validation-assets",
            bool(lab and lab["test_files"] and lab["has_eval_dir"] and lab["ci_referenced"]),
            "tests、evals 和 CI coverage 必须可发现",
        ),
        _assertion(
            "zero-derived-calls",
            inventory["checker"]["agent_calls"] == 0 and inventory["checker"]["network_calls"] == 0,
            "inventory 必须声明零 Agent 与网络调用",
        ),
    ]
    result = {
        "schema_version": SCHEMA_VERSION,
        "suite": "inventory",
        "passed": all(item["passed"] for item in assertions),
        "assertions": assertions,
        "inventory": inventory,
        "agent_calls": 0,
        "network_calls": 0,
    }
    write_new_json(work_dir / "inventory-evals.json", result)
    _require_passed(assertions)
    return result


def _synthetic_review(static: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    review = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": static["evaluation_id"],
        "candidate_tree_sha256": static["candidate"]["tree_sha256"],
        "dimensions": [
            {
                "dimension": dimension,
                "status": fixture["status"],
                "summary": fixture["summary"],
                "evidence": [
                    {
                        "path": fixture["evidence_path"],
                        "detail": fixture["evidence_detail"],
                    }
                ],
            }
            for dimension in SEMANTIC_DIMENSIONS
        ],
        "assumptions": ["该文档只验证 contract，不代表真实语义评审。"],
        "limitations": [fixture["limitation"]],
        "observation_decision": "provided",
    }
    return validate_semantic_review(review)


def _synthetic_bundle(packet: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_fingerprint": packet["packet_fingerprint"],
        "declared_by": fixture["declared_by"],
        "sessions": [
            {
                "case_id": case["case_id"],
                "variant": case["variant"],
                "session_ref": f"{fixture['session_ref_prefix']}-{index + 1}",
                "status": fixture["status"],
                "notes": fixture["notes"],
                "artifacts": [],
            }
            for index, case in enumerate(packet["cases"])
        ],
    }


def _check_status(static: dict[str, Any], check_id: str) -> str:
    return next(item["status"] for item in static["checks"] if item["id"] == check_id)


def _static_eval(work_dir: Path) -> dict[str, Any]:
    fixtures = REPO_ROOT / "evals" / "skill-evaluation-lab" / "fixtures"
    candidate = fixtures / "candidate-skill"
    baseline = fixtures / "baseline-skill"
    invalid = fixtures / "invalid-skill"
    static = evaluate_skill(REPO_ROOT, candidate, baseline=baseline, evaluation_id="static-self-eval")
    invalid_static = evaluate_skill(REPO_ROOT, invalid, evaluation_id="invalid-self-eval")
    suite = load_suite(fixtures / "suite.json")
    receipt = suite_receipt(REPO_ROOT, suite)
    packet, _ = build_packet(REPO_ROOT, suite)
    packet_result = write_packet(work_dir / "packet", packet)
    session_fixture = load_json_document(fixtures / "synthetic-session-fixture.json")
    imported = import_observations(REPO_ROOT, packet, _synthetic_bundle(packet, session_fixture))
    review_fixture = load_json_document(fixtures / "synthetic-review-fixture.json")
    review = _synthetic_review(static, review_fixture)
    verify_current_sources(REPO_ROOT, static)
    report = build_report(static, review, imported)
    assertions = [
        _assertion(
            "candidate-mechanical-validity",
            static["summary"]["fail"] == 0,
            f"candidate static fail count={static['summary']['fail']}",
        ),
        _assertion(
            "invalid-fixture-detected",
            _check_status(invalid_static, "skill.metadata") == "fail"
            and _check_status(invalid_static, "skill.references") == "fail",
            "invalid fixture 必须触发 metadata 与 reference fail",
        ),
        _assertion(
            "baseline-delta",
            static["delta"] is not None and bool(static["delta"]["changed_files"]),
            "candidate/baseline 必须形成确定性文件差异",
        ),
        _assertion(
            "manual-packet-only",
            packet_result["execution_mode"] == "user_operated_independent_session"
            and packet_result["agent_calls"] == 0,
            "packet 只能进入用户独立会话分支",
        ),
        _assertion(
            "synthetic-import-complete",
            imported["coverage"]["status"] == "complete" and len(imported["sessions"]) == 6,
            "synthetic fixture 必须覆盖 3 cases x 2 variants",
        ),
        _assertion(
            "layered-report",
            report["completion"]["conclusion_owner"] == "current_agent"
            and "overall_score" not in report
            and not report["runtime_claims_allowed"],
            "synthetic report 不得生成总分、脚本结论或运行时质量许可",
        ),
        _assertion(
            "zero-derived-calls",
            static["checker"]["agent_calls"] == 0
            and static["checker"]["network_calls"] == 0
            and imported["provenance"]["agent_calls"] == 0,
            "静态 self-eval 必须保持零 Agent 与网络调用",
        ),
    ]
    write_new_json(work_dir / "static-evidence.json", static)
    write_new_json(work_dir / "invalid-static-evidence.json", invalid_static)
    write_new_json(work_dir / "suite-receipt.json", receipt)
    write_new_json(work_dir / "semantic-review.fixture.json", review)
    write_new_json(work_dir / "imported-observation.json", imported)
    write_new_json(work_dir / "report.json", report)
    write_new_text(work_dir / "report.md", render_markdown(report))
    result = {
        "schema_version": SCHEMA_VERSION,
        "suite": "static",
        "passed": all(item["passed"] for item in assertions),
        "assertions": assertions,
        "synthetic_contract_fixture": True,
        "runtime_quality_claims": False,
        "agent_calls": 0,
        "network_calls": 0,
    }
    write_new_json(work_dir / "static-self-evals.json", result)
    _require_passed(assertions)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Skill Evaluation Lab 的纯静态 self-eval")
    parser.add_argument("--suite", choices=("inventory", "static"), required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="必须尚不存在的 workspace 内输出目录")
    args = parser.parse_args()

    def handler() -> object:
        workspace = resolve_workspace(REPO_ROOT)
        work_dir = resolve_output(workspace, args.work_dir, label="self-eval work directory")
        work_dir.mkdir(parents=True, exist_ok=False)
        return _inventory_eval(work_dir) if args.suite == "inventory" else _static_eval(work_dir)

    return run_cli(f"self_eval.{args.suite}", handler, pretty=True)


if __name__ == "__main__":
    raise SystemExit(main())
