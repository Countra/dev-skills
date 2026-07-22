#!/usr/bin/env python3
"""验证三套 coding skill 的 compact 联动与制品边界。"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "skills" / "complex-coding-planner"
EXECUTOR = ROOT / "skills" / "complex-coding-executor"
REVIEWER = ROOT / "skills" / "complex-coding-reviewer"
PLAN_CHECK = PLANNER / "scripts" / "harness_plan_check.py"
ACTIVE_TASK = PLANNER / "scripts" / "harness_active_task.py"
STATE = EXECUTOR / "scripts" / "harness_state.py"
TEMP_ROOT = ROOT / ".harness" / "test-tmp" / "complex-coding-workflow-evals"


class EvalFailure(Exception):
    """表示 compact workflow 的可观察契约不成立。"""


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, "-u", "-X", "utf8", "-B", *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if completed.returncode != expected:
        raise EvalFailure(
            f"command failed ({completed.returncode}): {' '.join(arguments)}\n"
            f"stdout: {completed.stdout}\nstderr: {completed.stderr}"
        )
    for stream in (completed.stdout, completed.stderr):
        if any(line.lstrip().startswith(("{", "[")) for line in stream.splitlines()):
            raise EvalFailure(f"public CLI emitted JSON: {arguments[0]}")
    return completed


def _workspace() -> Path:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    return path.resolve()


def _cleanup(path: Path) -> None:
    if not path.exists():
        return

    def remove_readonly(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=remove_readonly)


def _contract() -> dict:
    return {
        "task_id": "compact-workflow",
        "plan_revision": 1,
        "risk": "medium",
        "scope": ["skills/example"],
        "stages": [
            {
                "id": "STG-01",
                "title": "实现并验证行为",
                "depends_on": [],
                "scope": ["skills/example"],
                "risk": "medium",
                "validation_ids": ["VAL-01"],
                "review": "same-context",
            }
        ],
        "validations": [
            {
                "id": "VAL-01",
                "stage_id": "STG-01",
                "command": "python -m unittest",
                "required": True,
                "timeout_seconds": 300,
            },
            {
                "id": "VAL-FINAL",
                "stage_id": "final",
                "command": "python -m unittest full-suite",
                "required": True,
                "timeout_seconds": 900,
            },
        ],
        "final_validation_ids": ["VAL-FINAL"],
        "final_review": "same-context",
        "permissions_requested": {
            "commit": False,
            "external_write": False,
            "elevated_tool": False,
        },
    }


def _assert_static_contract() -> None:
    production_python = {
        path.relative_to(ROOT).as_posix()
        for root in (PLANNER, EXECUTOR, REVIEWER)
        for path in (root / "scripts").rglob("*.py")
    }
    expected = {
        "skills/complex-coding-planner/scripts/harness_active_task.py",
        "skills/complex-coding-planner/scripts/harness_contract.py",
        "skills/complex-coding-planner/scripts/harness_plan_check.py",
        "skills/complex-coding-executor/scripts/harness_bounded_command.py",
        "skills/complex-coding-executor/scripts/harness_state.py",
        "skills/complex-coding-executor/scripts/harness_state_store.py",
    }
    if production_python != expected:
        raise EvalFailure(
            "production Python boundary changed:\n"
            f"expected={sorted(expected)}\nactual={sorted(production_python)}"
        )
    if (REVIEWER / "scripts").exists() or (REVIEWER / "templates").exists():
        raise EvalFailure("Reviewer must remain instruction/reference-only")
    template_json = {
        path.relative_to(ROOT).as_posix()
        for root in (PLANNER, EXECUTOR, REVIEWER)
        for path in (root / "templates").rglob("*.json")
    }
    expected_templates = {
        "skills/complex-coding-planner/templates/active-task.json",
        "skills/complex-coding-planner/templates/plan-contract.json",
        "skills/complex-coding-executor/templates/run-state.json",
    }
    if template_json != expected_templates:
        raise EvalFailure(
            "runtime JSON template boundary changed:\n"
            f"expected={sorted(expected_templates)}\nactual={sorted(template_json)}"
        )

    planner_text = (PLANNER / "SKILL.md").read_text(encoding="utf-8")
    executor_text = (EXECUTOR / "SKILL.md").read_text(encoding="utf-8")
    executor_safety_text = (
        EXECUTOR / "references" / "execution-safety.md"
    ).read_text(encoding="utf-8")
    reviewer_text = (REVIEWER / "SKILL.md").read_text(encoding="utf-8")
    if "direct" not in planner_text or "不创建 `.harness` 文件" not in planner_text:
        raise EvalFailure("Planner direct zero-artifact convention is missing")
    if "`final_validation_ids`" not in planner_text:
        raise EvalFailure("Planner final integration validation convention is missing")
    if "不保存 findings JSON" not in executor_text:
        raise EvalFailure("Executor review persistence boundary is missing")
    if "`validate --stage final`" not in executor_text:
        raise EvalFailure("Executor final integration validation gate is missing")
    planner_process_terms = (
        "长期进程",
        "`process-manager`",
        "有限命令",
        "deadline",
        "不进入 Process Manager",
    )
    if any(term not in planner_text for term in planner_process_terms):
        raise EvalFailure("Planner process ownership convention is missing")
    executor_process_terms = (
        "pm_manager.py status",
        "recommendedAction",
        "pm_session.py close --stop-manager-if-idle",
        "不自动提权",
    )
    if any(term not in executor_safety_text for term in executor_process_terms):
        raise EvalFailure("Executor process recovery convention is missing")
    for phrase in ("findings-first", "路径和行号", "不要向用户输出 JSON"):
        if phrase not in reviewer_text:
            raise EvalFailure(f"Reviewer human-output rule missing: {phrase}")

    required_cases = {
        "plan-clean.md",
        "plan-missing-validation.md",
        "code-clean.md",
        "code-framing-bias.md",
        "code-prompt-injection.md",
        "code-parent-contamination.md",
    }
    case_root = ROOT / "evals" / "complex-coding-reviewer" / "semantic_cases"
    available = {path.name for path in case_root.glob("*.md")}
    missing = required_cases - available
    if missing:
        raise EvalFailure(f"Reviewer semantic cases missing: {sorted(missing)}")


def _assert_managed_lifecycle() -> None:
    workspace = _workspace()
    try:
        if (workspace / ".harness").exists():
            raise EvalFailure("fresh direct workspace unexpectedly contains Harness state")
        task_dir = (
            workspace
            / ".harness"
            / "tasks"
            / "2026-07-22"
            / "feature"
            / "compact-workflow"
        )
        task_dir.mkdir(parents=True)
        _write_json(task_dir / "plan-contract.json", _contract())
        (task_dir / "execution-plan.md").write_text(
            "# Compact workflow\n\n"
            "- STG-01：实现并验证行为\n"
            "- VAL-01：运行目标测试\n"
            "- VAL-FINAL：验证全部阶段汇合后的最终状态\n",
            encoding="utf-8",
        )

        _run(str(PLAN_CHECK), "--task-dir", str(task_dir), "--mode", "approval")
        _run(
            str(ACTIVE_TASK),
            "--workspace",
            str(workspace),
            "activate",
            "--task-dir",
            str(task_dir),
        )
        _run(str(STATE), "--workspace", str(workspace), "status")
        _run(
            str(STATE),
            "--workspace",
            str(workspace),
            "approve",
            "--implementation",
            "--plan-review-mode",
            "same-context",
            "--plan-review-summary",
            "未发现 blocking 或 major 问题",
        )
        _run(str(STATE), "--workspace", str(workspace), "start", "--stage", "STG-01")
        _run(
            str(STATE),
            "--workspace",
            str(workspace),
            "validate",
            "--stage",
            "STG-01",
            "--validation",
            "VAL-01",
            "--result",
            "passed",
            "--exit-code",
            "0",
            "--summary",
            "目标测试通过",
        )
        _run(
            str(STATE),
            "--workspace",
            str(workspace),
            "review",
            "--scope",
            "STG-01",
            "--verdict",
            "passed",
            "--mode",
            "same-context",
            "--summary",
            "未发现 blocking 或 major 问题",
        )
        _run(
            str(STATE),
            "--workspace",
            str(workspace),
            "finish-stage",
            "--stage",
            "STG-01",
        )
        _run(
            str(STATE),
            "--workspace",
            str(workspace),
            "validate",
            "--stage",
            "final",
            "--validation",
            "VAL-FINAL",
            "--result",
            "passed",
            "--exit-code",
            "0",
            "--summary",
            "最终集成测试通过",
        )
        _run(
            str(STATE),
            "--workspace",
            str(workspace),
            "review",
            "--scope",
            "final",
            "--verdict",
            "passed",
            "--mode",
            "same-context",
            "--summary",
            "最终集成未发现 blocking 或 major 问题",
        )
        _run(str(STATE), "--workspace", str(workspace), "complete")

        task_files = {
            path.name for path in task_dir.iterdir() if path.is_file()
        }
        if task_files != {
            "execution-plan.md",
            "plan-contract.json",
            "run-state.json",
        }:
            raise EvalFailure(f"unexpected task artifacts: {sorted(task_files)}")
        pointer = workspace / ".harness" / "active-task.json"
        if not pointer.is_file():
            raise EvalFailure("active-task.json is missing")
        all_files = [path for path in (workspace / ".harness").rglob("*") if path.is_file()]
        if len(all_files) != 4:
            raise EvalFailure(f"managed lifecycle created {len(all_files)} files instead of 4")
        forbidden = {"ledger.jsonl", "attestation.json", "review-receipt.json"}
        if forbidden & {path.name for path in all_files}:
            raise EvalFailure("legacy workflow artifacts were created")
    finally:
        _cleanup(workspace)


def main() -> int:
    checks = [
        ("static compact boundary", _assert_static_contract),
        ("four-file managed lifecycle", _assert_managed_lifecycle),
    ]
    failures: list[str] = []
    for name, check in checks:
        try:
            check()
        except Exception as exc:  # noqa: BLE001 - eval 需要汇总所有失败
            failures.append(f"{name}: {exc}")
            print(f"FAIL: {name}: {exc}")
        else:
            print(f"PASS: {name}")
    if failures:
        print(f"FAILED: {len(failures)} compact workflow check(s).")
        return 1
    print("PASS: compact Planner/Reviewer/Executor workflow is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
