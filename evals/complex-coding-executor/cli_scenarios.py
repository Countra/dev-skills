#!/usr/bin/env python3
"""executor eval 的公开 CLI 生命周期场景。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


EXECUTOR_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "complex-coding-executor"
    / "scripts"
)


def run_cli(
    workspace: Path,
    task_dir: Path,
    script_name: str,
    arguments: list[str],
) -> dict[str, Any]:
    script = EXECUTOR_SCRIPTS / script_name
    command = [
        sys.executable,
        "-X",
        "utf8",
        "-B",
        str(script),
        "--workspace",
        str(workspace),
        "--task-dir",
        str(task_dir),
        "--format",
        "json",
        *arguments,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=120,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{script_name} 未返回 JSON：{result.stdout!r} {result.stderr!r}"
        ) from exc
    if result.returncode != 0 or payload.get("ok") is not True:
        raise AssertionError(f"{script_name} 失败：{payload}")
    return payload["result"]


def record_stage_cli(
    workspace: Path,
    task_dir: Path,
    stage: dict[str, Any],
) -> None:
    stage_id = stage["id"]
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        ["--event", "stage_started", "--stage-id", stage_id, "--attempt", "1"],
    )
    for validation_id in stage["validation_ids"]:
        payload = json.dumps(
            {
                "validation_id": validation_id,
                "result": "passed",
                "summary": "CLI validation passed",
            },
            ensure_ascii=False,
        )
        run_cli(
            workspace,
            task_dir,
            "harness_ledger_append.py",
            [
                "--event",
                "validation_recorded",
                "--stage-id",
                stage_id,
                "--payload-json",
                payload,
            ],
        )
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        [
            "--event",
            "review_recorded",
            "--stage-id",
            stage_id,
            "--payload-json",
            (
                '{"result":"passed","summary":"CLI review passed",'
                '"development_quality":"passed"}'
            ),
        ],
    )
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        ["--event", "stage_completed", "--stage-id", stage_id],
    )
    run_cli(workspace, task_dir, "harness_exec_check.py", ["--mode", "transition"])


def run_complete_cli(workspace: Path, task_dir: Path, bundle: Any) -> dict[str, Any]:
    run_cli(workspace, task_dir, "harness_task_resolver.py", [])
    run_cli(
        workspace,
        task_dir,
        "harness_attest_plan.py",
        [
            "--mode",
            "write",
            "--approved-by",
            "eval-user",
            "--approval-summary",
            "approved CLI lifecycle",
        ],
    )
    run_cli(workspace, task_dir, "harness_exec_check.py", ["--mode", "preflight"])
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        ["--event", "execution_started"],
    )
    for stage in bundle.contract["stages"]:
        record_stage_cli(workspace, task_dir, stage)
    run_cli(workspace, task_dir, "harness_ledger_append.py", ["--event", "completed"])
    bundle.pointer_path.unlink()
    final = run_cli(workspace, task_dir, "harness_exec_check.py", ["--mode", "final"])
    summary = run_cli(workspace, task_dir, "harness_ledger_summary.py", [])
    return {
        "lifecycle": final["state"]["lifecycle"],
        "event_count": summary["last_event_seq"],
        "completed_stages": len(summary["completed_stage_ids"]),
    }


def run_amendment_cli(
    workspace: Path,
    task_dir: Path,
    bundle: Any,
    factory: Any,
) -> dict[str, Any]:
    run_cli(
        workspace,
        task_dir,
        "harness_attest_plan.py",
        [
            "--mode",
            "write",
            "--approved-by",
            "eval-user",
            "--approval-summary",
            "approve initial revision",
        ],
    )
    run_cli(workspace, task_dir, "harness_exec_check.py", ["--mode", "preflight"])
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        ["--event", "execution_started"],
    )
    record_stage_cli(workspace, task_dir, bundle.contract["stages"][0])
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        [
            "--event",
            "amendment_requested",
            "--payload-json",
            '{"reason":"add second stage"}',
        ],
    )
    run_cli(
        workspace,
        task_dir,
        "harness_attest_plan.py",
        ["--mode", "archive"],
    )

    contract = factory.build_contract(bundle.task_id, "standard")
    contract["plan_revision"] = 2
    factory.write_json(task_dir / "plan-contract.json", contract)
    (task_dir / "execution-plan.md").write_text(
        factory.build_plan(contract),
        encoding="utf-8",
    )
    factory.write_artifacts(
        task_dir,
        contract,
        include_online_source=True,
    )
    run_cli(
        workspace,
        task_dir,
        "harness_attest_plan.py",
        [
            "--mode",
            "write",
            "--approved-by",
            "eval-user",
            "--approval-summary",
            "approve amended revision",
        ],
    )
    run_cli(
        workspace,
        task_dir,
        "harness_attest_plan.py",
        [
            "--mode",
            "activate-amendment",
            "--archive-dir",
            "artifacts/amendments/revision-0001",
            "--carry-stage",
            "STG-01",
        ],
    )
    status = run_cli(
        workspace,
        task_dir,
        "harness_exec_check.py",
        ["--mode", "status"],
    )
    if status["completed_stage_ids"] != ["STG-01"]:
        raise AssertionError(f"amendment carried stages 错误：{status}")
    if status["remaining_stage_ids"] != ["STG-02"]:
        raise AssertionError(f"amendment remaining stages 错误：{status}")
    return {
        "plan_revision": status["plan_revision"],
        "completed_stages": len(status["completed_stage_ids"]),
        "remaining_stages": len(status["remaining_stage_ids"]),
    }
