#!/usr/bin/env python3
"""验证跨 skill 公共契约与可选 Reviewer 生命周期。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ELECTRON_SCRIPTS = REPO_ROOT / "skills" / "electron-ui-verifier" / "scripts"
PROCESS_SCRIPTS = REPO_ROOT / "skills" / "process-manager" / "scripts"
EXECUTOR_EVAL = REPO_ROOT / "evals" / "complex-coding-executor" / "run_evals.py"
sys.path.insert(0, str(ELECTRON_SCRIPTS))

from ev_init import service_config  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_fixture_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        fixture_id = value.get("id") if isinstance(value, dict) else None
        if not isinstance(fixture_id, str) or fixture_id in ids:
            raise ValueError(f"{path.name}:{line_number} fixture id 无效或重复")
        ids.add(fixture_id)
    return ids


def run_validate(config: Path, service: Path) -> tuple[int, dict[str, Any]]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(PROCESS_SCRIPTS / "pm_validate.py"),
            "--config",
            str(config),
            "--service",
            str(service),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        value = {}
    return result.returncode, value if isinstance(value, dict) else {}


def run_reviewer_lifecycle(work_dir: Path) -> dict[str, Any]:
    manifest = work_dir / "reviewer-lifecycle-manifest.json"
    report_path = work_dir / "reviewer-lifecycle-report.json"
    write_json(
        manifest,
        {
            "capability": [
                {
                    "id": "joint-reviewer-lifecycle",
                    "profile": "lite",
                    "scenario": "complete-cli",
                    "commit_authorized": False,
                }
            ],
            "regression": [],
        },
    )
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            "-X",
            "utf8",
            "-B",
            str(EXECUTOR_EVAL),
            "--manifest",
            str(manifest),
            "--work-dir",
            str(work_dir / "reviewer-lifecycle-work"),
            "--output",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        report = {}
    passed = (
        result.returncode == 0
        and isinstance(report, dict)
        and report.get("total") == 1
        and report.get("passed") == 1
        and report.get("failed") == 0
    )
    return {
        "passed": passed,
        "exit_code": result.returncode,
        "total": report.get("total") if isinstance(report, dict) else None,
        "passed_cases": report.get("passed") if isinstance(report, dict) else None,
        "failed_cases": report.get("failed") if isinstance(report, dict) else None,
        "report": str(report_path),
    }


def evaluate(work_dir: Path, *, include_reviewer: bool = False) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    manager_config = work_dir / "manager.json"
    service_path = work_dir / "electron-service.json"
    verifier_config = work_dir / "electron-verifier.json"
    write_json(
        manager_config,
        {
            "workspaceRoot": str(REPO_ROOT),
            "stateRoot": str((work_dir / "runtime").resolve()),
            "control": {"host": "127.0.0.1", "port": 0, "maxRequestBytes": 65536},
            "history": {"maxInactive": 20, "deleteRunDirs": True},
            "logs": {"maxBytes": 10485760, "backups": 3},
        },
    )
    generated = service_config(REPO_ROOT, Path(sys.executable).resolve(), verifier_config.resolve(), 18180)
    write_json(service_path, generated)
    validation_code, validation = run_validate(manager_config, service_path)
    failures: list[str] = []
    if validation_code != 0 or validation.get("ok") is not True:
        failures.append("electron service 未通过 current pm_validate.py")
    launcher = generated.get("launcher", {})
    if launcher.get("type") != "script" or set(launcher) != {
        "type",
        "interpreter",
        "script",
        "args",
        "pathArgs",
    }:
        failures.append("electron service launcher 不是封闭 current script schema")
    if {"argv", "window", "platform", "backend"} & set(generated):
        failures.append("electron service 顶层残留旧或平台字段")
    readiness = generated.get("readiness", {})
    if (
        readiness.get("type") != "log"
        or readiness.get("extract") != {"urls": ["url"]}
        or not isinstance(readiness.get("scanBytes"), int)
    ):
        failures.append("electron service 未使用有界命名组 log readiness")

    consumer_paths = [
        REPO_ROOT / "skills" / "electron-ui-verifier" / "SKILL.md",
        REPO_ROOT / "skills" / "electron-ui-verifier" / "references" / "server.md",
        REPO_ROOT / "skills" / "electron-ui-verifier" / "references" / "workflow.md",
        REPO_ROOT / "skills" / "electron-ui-verifier" / "references" / "troubleshooting.md",
        REPO_ROOT / "skills" / "complex-coding-planner" / "SKILL.md",
        REPO_ROOT / "skills" / "complex-coding-planner" / "references" / "planning-workflow.md",
        REPO_ROOT / "skills" / "complex-coding-planner" / "templates" / "execution-plan.md",
        REPO_ROOT / "skills" / "complex-coding-executor" / "SKILL.md",
        REPO_ROOT / "skills" / "complex-coding-executor" / "references" / "execution-workflow.md",
        REPO_ROOT / "skills" / "complex-coding-executor" / "references" / "troubleshooting.md",
        REPO_ROOT / "README.md",
        REPO_ROOT / ".gitignore",
        REPO_ROOT / ".harness" / "environment.md",
    ]
    if include_reviewer:
        consumer_paths.extend(
            [
                REPO_ROOT / "skills" / "complex-coding-reviewer" / "SKILL.md",
                REPO_ROOT
                / "skills"
                / "complex-coding-reviewer"
                / "references"
                / "review-contract.md",
                REPO_ROOT
                / "skills"
                / "complex-coding-reviewer"
                / "references"
                / "plan-review.md",
                REPO_ROOT
                / "skills"
                / "complex-coding-reviewer"
                / "references"
                / "code-review.md",
            ]
        )
    consumer_text = "\n".join(path.read_text(encoding="utf-8") for path in consumer_paths)
    required_terms = (
        "pm_init.py",
        "pm_manager.py status",
        "pm_manager.py start",
        "authenticated manager identity",
        "processKey",
        "bounded logs",
        "cleanupVerified",
        "stopResult.ownerEmpty",
        "不判断 OS/backend",
        "普通流程不先运行",
    )
    if include_reviewer:
        required_terms += (
            "plan-review",
            "code-review",
            "stage-delta",
            "final-integration",
            "review_validate.py",
            "target_digest",
            "context_digest",
            "coverage_summary",
            "lineage_summary",
            "report_ref",
            "verification_gaps",
        )
    missing_terms = [term for term in required_terms if term not in consumer_text]
    if missing_terms:
        failures.append("consumer 规则缺失: " + ", ".join(missing_terms))
    forbidden_terms = (
        "start_manager.ps1",
        "stop_manager.ps1",
        "manager.pid",
        "SKILL_GITLAB_TOKEN",
        '"argv"',
        '"window"',
        "cmd-file",
        "powershell-file",
        "default port is 18080",
    )
    if include_reviewer:
        forbidden_terms += (
            "critique_ref",
            "development_quality",
            "legacy_receipt",
            "receipt_schema_version",
            "review_payload",
            "review_report",
        )
    present_forbidden = [term for term in forbidden_terms if term in consumer_text]
    if present_forbidden:
        failures.append("current consumer 残留旧契约: " + ", ".join(present_forbidden))

    planner_ids = read_fixture_ids(REPO_ROOT / "evals" / "complex-coding-planner" / "prompts.jsonl")
    executor_ids = read_fixture_ids(REPO_ROOT / "evals" / "complex-coding-executor" / "prompts.jsonl")
    if "process-manager-platform-transparent-gate" not in planner_ids:
        failures.append("planner eval 缺少 process-manager 平台透明门禁")
    required_executor_ids = {"process-manager-required-dev-server", "process-manager-doctor-on-demand"}
    if include_reviewer:
        required_executor_ids.update(
            {
                "review-handoff-uses-standards-and-current-target",
                "final-missing-current-review-receipt-blocked",
            }
        )
    if not required_executor_ids.issubset(executor_ids):
        failures.append("executor eval 缺少 process-manager current workflow 场景")
    reviewer_lifecycle = None
    if include_reviewer:
        reviewer_lifecycle = run_reviewer_lifecycle(work_dir)
        if reviewer_lifecycle["passed"] is not True:
            failures.append("Planner/Reviewer/Executor 公共 CLI 生命周期未闭环")
    return {
        "ok": not failures,
        "electron_validate_exit": validation_code,
        "electron_launcher": launcher.get("type"),
        "electron_readiness": readiness.get("type"),
        "consumer_file_count": len(consumer_paths),
        "required_term_count": len(required_terms),
        "missing_required_terms": missing_terms,
        "present_forbidden_terms": present_forbidden,
        "planner_fixture_count": len(planner_ids),
        "executor_fixture_count": len(executor_ids),
        "reviewer_included": include_reviewer,
        "reviewer_lifecycle": reviewer_lifecycle,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-reviewer", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate(
            args.work_dir.resolve(),
            include_reviewer=args.include_reviewer,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        result = {"ok": False, "failures": [f"cross-skill regression 环境无效: {exc}"]}
    output = args.output or args.work_dir / "cross-skill-regression.json"
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
