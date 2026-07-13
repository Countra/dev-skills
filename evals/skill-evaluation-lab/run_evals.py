#!/usr/bin/env python3
"""执行 Skill Evaluation Lab 的离线自评测。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "skill-evaluation-lab" / "scripts"
FIXTURE_DIR = EVAL_DIR / "fixtures"
MAX_CLI_OUTPUT_BYTES = 4 * 1024 * 1024


def _run(script: str, *arguments: str, timeout: int = 120) -> tuple[int, dict[str, Any]]:
    try:
        result = subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-B", str(SCRIPT_DIR / script), *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, {"ok": False, "error": {"code": "cli_execution_failed", "message": str(exc)}}
    encoded_size = len(result.stdout.encode("utf-8")) + len(result.stderr.encode("utf-8"))
    if encoded_size > MAX_CLI_OUTPUT_BYTES:
        return 1, {"ok": False, "error": {"code": "cli_output_too_large", "message": str(encoded_size)}}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        detail = (result.stderr or result.stdout).strip()[:2000]
        payload = {"ok": False, "error": {"code": "invalid_cli_json", "message": detail}}
    return result.returncode, payload


def _step_ok(code: int, payload: dict[str, Any]) -> bool:
    return code == 0 and payload.get("ok") is True


def _coverage(inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    coverage: list[dict[str, Any]] = []
    suggestions: list[dict[str, str]] = []
    for skill in inventory.get("data", {}).get("skills", []):
        item = {
            "name": skill.get("name"),
            "valid": skill.get("valid"),
            "public_script_count": skill.get("public_script_count"),
            "test_count": skill.get("test_count"),
            "has_eval_dir": skill.get("has_eval_dir"),
            "eval_file_count": skill.get("eval_file_count"),
            "ci_referenced": skill.get("ci_referenced"),
        }
        coverage.append(item)
        if not item["has_eval_dir"]:
            suggestions.append({"skill": str(item["name"]), "action": "保留现有测试并新增独立 suite"})
        elif not item["ci_referenced"]:
            suggestions.append({"skill": str(item["name"]), "action": "评估是否把现有离线 eval 接入 CI"})
    return coverage, suggestions


def inventory_suite() -> dict[str, Any]:
    example_suite = REPO_ROOT / "skills" / "skill-evaluation-lab" / "assets" / "eval-suite.example.json"
    inventory_code, inventory = _run(
        "se_inventory.py",
        "--root",
        str(REPO_ROOT),
        "--require-valid-skill",
        "skill-evaluation-lab",
    )
    validate_code, validation = _run("se_validate.py", "--suite", str(example_suite))
    plan_code, plan = _run("se_plan.py", "--suite", str(example_suite))
    failures: list[str] = []
    if not _step_ok(inventory_code, inventory):
        failures.append("inventory CLI 失败")
    elif inventory.get("data", {}).get("skill_count", 0) < 6:
        failures.append("inventory 未发现全部 skill")
    if not _step_ok(validate_code, validation):
        failures.append("example suite 校验失败")
    if not _step_ok(plan_code, plan):
        failures.append("example suite 预算预览失败")
    coverage, suggestions = _coverage(inventory)
    return {
        "ok": not failures,
        "suite": "inventory",
        "steps": {
            "inventory": {"exit_code": inventory_code, "ok": _step_ok(inventory_code, inventory)},
            "validate_example": {"exit_code": validate_code, "ok": _step_ok(validate_code, validation)},
            "plan_example": {"exit_code": plan_code, "ok": _step_ok(plan_code, plan)},
        },
        "skill_count": inventory.get("data", {}).get("skill_count"),
        "coverage": coverage,
        "conversion_suggestions": suggestions,
        "example_plan": {
            "fingerprint": plan.get("data", {}).get("fingerprint"),
            "agent_run_count": plan.get("data", {}).get("agent_run_count"),
            "runner": plan.get("data", {}).get("runner"),
        },
        "model_calls": 0,
        "failures": failures,
    }


def offline_suite(work_dir: Path) -> dict[str, Any]:
    suite_path = FIXTURE_DIR / "fake-suite" / "suite.json"
    run_copy = work_dir / "run.json"
    grade_path = work_dir / "grade.json"
    report_path = work_dir / "report.json"
    markdown_path = work_dir / "report.md"
    run_id = f"offline-{uuid.uuid4().hex[:12]}"
    steps: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    validate_code, validation = _run("se_validate.py", "--suite", str(suite_path))
    steps["validate"] = {"exit_code": validate_code, "ok": _step_ok(validate_code, validation)}
    if not steps["validate"]["ok"]:
        failures.append("fake suite 校验失败")

    plan_code, plan = _run("se_plan.py", "--suite", str(suite_path))
    steps["plan"] = {"exit_code": plan_code, "ok": _step_ok(plan_code, plan)}
    if not steps["plan"]["ok"]:
        failures.append("fake suite 预算预览失败")

    run_code, run = _run(
        "se_run.py",
        "--suite",
        str(suite_path),
        "--work-root",
        str(work_dir / "runs"),
        "--run-id",
        run_id,
        "--output",
        str(run_copy),
    )
    steps["run"] = {"exit_code": run_code, "ok": _step_ok(run_code, run)}
    if not steps["run"]["ok"] or run.get("data", {}).get("status") != "PASS":
        failures.append("fake paired run 未通过")

    grade_code, grade = _run("se_grade.py", "--run", str(run_copy), "--output", str(grade_path))
    steps["grade"] = {"exit_code": grade_code, "ok": _step_ok(grade_code, grade)}
    if not steps["grade"]["ok"]:
        failures.append("fake run 确定性评分失败")

    report_code, report = _run(
        "se_report.py",
        "--grade",
        str(grade_path),
        "--json-output",
        str(report_path),
        "--markdown-output",
        str(markdown_path),
    )
    steps["report"] = {"exit_code": report_code, "ok": _step_ok(report_code, report)}
    report_data = report.get("data", {})
    if not steps["report"]["ok"]:
        failures.append("fake grade 报告生成失败")
    elif report_data.get("paired_delta", {}).get("n_pairs") != 1:
        failures.append("fake behavior pair 未进入兼容 paired delta")
    elif not report_data.get("uncertainty", {}).get("paired_low_information"):
        failures.append("单个 tie pair 未标记低信息")
    elif not report_data.get("gate_decisions", {}).get("all_required_passed"):
        failures.append("fake suite 的 required gates 未闭环")
    elif not report_data.get("uncertainty", {}).get("duration_available"):
        failures.append("fake runner 耗时未进入报告")
    elif report_data.get("trigger", {}).get("confusion_matrix", {}).get("true_negative") != 1:
        failures.append("fake trigger truth 未进入 confusion matrix")
    elif report_data.get("provenance", {}).get("lab_identity", {}).get(
        "tree_sha256"
    ) != report_data.get("provenance", {}).get("grader_identity", {}).get("tree_sha256"):
        failures.append("run 与 grader implementation identity 不一致")

    return {
        "ok": not failures,
        "suite": "offline",
        "steps": steps,
        "pipeline": {
            "fingerprint": plan.get("data", {}).get("fingerprint"),
            "agent_run_count": plan.get("data", {}).get("agent_run_count"),
            "run_status": run.get("data", {}).get("status"),
            "record_count": len(grade.get("data", {}).get("records", [])),
            "paired_count": report_data.get("paired_delta", {}).get("n_pairs"),
            "paired_ties": report_data.get("paired_delta", {}).get("ties"),
            "low_information": report_data.get("uncertainty", {}).get("paired_low_information"),
            "all_required_gates_passed": report_data.get("gate_decisions", {}).get(
                "all_required_passed"
            ),
            "duration_available": report_data.get("uncertainty", {}).get("duration_available"),
            "trigger_confusion": report_data.get("trigger", {}).get("confusion_matrix"),
            "lab_tree_sha256": report_data.get("provenance", {})
            .get("lab_identity", {})
            .get("tree_sha256"),
            "grader_tree_sha256": report_data.get("provenance", {})
            .get("grader_identity", {})
            .get("tree_sha256"),
        },
        "artifacts": {
            "run": str(run_copy.relative_to(work_dir)).replace("\\", "/"),
            "grade": str(grade_path.relative_to(work_dir)).replace("\\", "/"),
            "report_json": str(report_path.relative_to(work_dir)).replace("\\", "/"),
            "report_markdown": str(markdown_path.relative_to(work_dir)).replace("\\", "/"),
        },
        "model_calls": 0,
        "failures": failures,
    }


def _safe_work_dir(raw: Path) -> Path:
    resolved = raw.resolve()
    if resolved == REPO_ROOT or REPO_ROOT not in resolved.parents:
        raise ValueError("--work-dir 必须位于仓库内部且不能是仓库根目录")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Skill Evaluation Lab 离线自评测")
    parser.add_argument("--suite", choices=["inventory", "offline"], default="offline")
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        work_dir = _safe_work_dir(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        result = inventory_suite() if args.suite == "inventory" else offline_suite(work_dir)
        output_name = "inventory-evals.json" if args.suite == "inventory" else "self-evals.json"
        (work_dir / output_name).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        result = {"ok": False, "suite": args.suite, "failures": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
