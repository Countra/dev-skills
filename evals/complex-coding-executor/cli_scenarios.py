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
REVIEWER_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "complex-coding-reviewer"
    / "scripts"
)
if str(REVIEWER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REVIEWER_SCRIPTS))

from complex_coding_reviewer.context import RISK_IDS, build_context_target  # noqa: E402
from complex_coding_reviewer.contract import CODE_LENSES  # noqa: E402


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_validation_evidence(
    task_dir: Path,
    stage_id: str,
    validation_id: str,
) -> str:
    filename = f"{stage_id.lower()}-{validation_id.lower()}.txt"
    ref = f"artifacts/validation/{filename}"
    path = task_dir / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("deterministic validation passed\n", encoding="utf-8")
    return ref


def run_git(workspace: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return result.stdout.strip()


def initialize_review_repository(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    run_git(workspace, ["init", "--quiet"])
    source = workspace / "src" / "eval_fixture.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("fixture = 'executor-eval'\n", encoding="utf-8")
    run_git(workspace, ["add", "src/eval_fixture.py"])
    run_git(
        workspace,
        [
            "-c",
            "user.name=Executor Eval",
            "-c",
            "user.email=executor-eval@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initialize evaluator fixture",
        ],
    )


def run_reviewer_target(
    workspace: Path,
    *,
    stage_id: str | None,
    attempt: int | None,
    commit_range: bool = False,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        "-B",
        str(REVIEWER_SCRIPTS / "review_target.py"),
    ]
    if commit_range:
        command.extend(
            [
                "commit-range",
                "--repository",
                str(workspace),
                "--baseline",
                "HEAD",
                "--head",
                "HEAD",
                "--path",
                "src",
            ]
        )
    else:
        command.extend(
            [
                "working-tree",
                "--repository",
                str(workspace),
                "--baseline",
                "HEAD",
                "--path",
                "src",
            ]
        )
    if not commit_range and stage_id is not None and attempt is not None:
        command.extend(["--stage-id", stage_id, "--attempt", str(attempt)])
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=120,
    )
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"review_target.py 未返回 JSON：{result.stdout!r} {result.stderr!r}"
        ) from exc
    if result.returncode != 0 or envelope.get("ok") is not True:
        raise AssertionError(f"review_target.py 失败：{envelope}")
    envelope_result = envelope.get("result")
    target = envelope_result.get("target") if isinstance(envelope_result, dict) else None
    if not isinstance(target, dict):
        raise AssertionError(f"review_target.py 缺少 target：{envelope}")
    return target


def create_review_evidence(
    workspace: Path,
    task_dir: Path,
    *,
    scope: dict[str, Any],
    review_id: str,
    final_commit_recorded: bool = False,
    target: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    stage_id = scope.get("stage_id")
    attempt = scope.get("attempt")
    target = target or run_reviewer_target(
        workspace,
        stage_id=str(stage_id) if stage_id is not None else None,
        attempt=int(attempt) if attempt is not None else None,
        commit_range=scope.get("kind") == "final-integration" and final_commit_recorded,
    )
    contract = json.loads((task_dir / "plan-contract.json").read_text(encoding="utf-8"))
    stages = {item["id"]: item for item in contract["stages"]}
    if scope["kind"] == "stage-delta":
        stage = stages[scope["stage_id"]]
        requirement_refs = sorted(
            {
                item
                for field in (
                    "requirement_ids",
                    "acceptance_ids",
                    "nonfunctional_ids",
                )
                for item in stage.get(field, [])
            }
        ) or [scope["stage_id"]]
        constraint_refs = sorted(
            {scope["stage_id"], *stage.get("validation_ids", [])}
        )
    else:
        requirement_refs = []
        goal = contract.get("goal")
        if isinstance(goal, dict) and isinstance(goal.get("id"), str):
            requirement_refs.append(goal["id"])
        for field in ("requirements", "acceptance_criteria", "nonfunctional_requirements"):
            requirement_refs.extend(item["id"] for item in contract.get(field, []))
        requirement_refs = sorted(set(requirement_refs)) or sorted(stages)
        constraint_refs = sorted(
            {
                *stages,
                *(item["id"] for item in contract.get("validations", [])),
            }
        )
    effective_validations: dict[tuple[str, str], dict[str, Any]] = {}
    ledger = task_dir / "ledger.jsonl"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("type") != "validation_recorded":
                continue
            if scope["kind"] == "stage-delta" and (
                event.get("stage_id") != stage_id or event.get("attempt") != attempt
            ):
                continue
            payload = event.get("payload", {})
            key = (str(event.get("stage_id")), str(payload.get("validation_id")))
            if payload.get("result") == "passed":
                effective_validations[key] = event
            else:
                effective_validations.pop(key, None)
    task_relative = task_dir.relative_to(workspace).as_posix()
    validation_paths = sorted(
        f"{task_relative}/{ref}"
        for event in effective_validations.values()
        for ref in event.get("evidence_refs", [])
    )
    filename = review_id.lower().replace("_", "-")
    brief_relative = f"{task_relative}/artifacts/reviews/{filename}-brief.json"
    brief = {
        "profile": "code-review",
        "scope": scope,
        "summary": "验证 deterministic executor lifecycle target。",
        "requirement_refs": requirement_refs,
        "constraint_refs": constraint_refs,
        "claim_refs": validation_paths,
        "requested_risk_focus": [],
        "created_at": "2026-07-16T00:00:00+00:00",
    }
    write_json(workspace / brief_relative, brief)
    plan_relative = (task_dir / "execution-plan.md").relative_to(workspace).as_posix()
    contract_relative = (task_dir / "plan-contract.json").relative_to(workspace).as_posix()
    context_entries = [
        (brief_relative, "brief"),
        (plan_relative, "requirement"),
        (contract_relative, "requirement"),
    ]
    context_entries.extend((path, "validation") for path in validation_paths)
    for artifact in contract.get("artifacts", []):
        if artifact.get("kind") == "standards":
            context_entries.append(
                (f"{task_relative}/{artifact['path']}", "standard")
            )
    context = build_context_target(
        workspace,
        root_kind="workspace",
        label=f"{filename}-context",
        entries=context_entries,
    )
    target_paths = [str(item["path"]) for item in target["manifest"]]
    receipt = {
        "review_id": review_id,
        "profile": "code-review",
        "scope": scope,
        "target": target,
        "context": context,
        "reviewer": {
            "mode": "same-context",
            "identity": "deterministic-executor-eval",
            "independence_claim": False,
            "capability_limits": ["未执行目标代码或调用 Agent。"],
        },
        "standards": [
            {
                "id": "STD-01",
                "title": "Executor evaluation contract",
                "source": "evals/complex-coding-executor/README.md",
                "applicability": "约束确定性生命周期 fixture。",
            }
        ],
        "coverage": {
            "target_paths": [
                {
                    "path": path,
                    "status": "reviewed",
                    "reason": "deterministic lifecycle fixture 已覆盖该路径。",
                    "gap_ids": [],
                }
                for path in target_paths
            ],
            "requirement_checks": [
                {
                    "id": requirement_ref,
                    "status": "satisfied",
                    "evidence_refs": [brief_relative],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "当前 fixture 提供了直接证据。",
                }
                for requirement_ref in requirement_refs
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
        "lenses": [
            {
                "id": lens,
                "status": "reviewed",
                "evidence_refs": [brief_relative],
                "summary": f"{lens} 已基于确定性 fixture 审查。",
            }
            for lens in CODE_LENSES
        ],
        "strengths": [],
        "findings": [],
        "verification_gaps": [],
        "verdict": "passed",
        "open_counts": {
            "blocking": 0,
            "major": 0,
            "minor": 0,
            "advisory": 0,
            "total": 0,
        },
        "summary": "确定性 fixture 的当前目标通过 code-review 契约。",
        "limitations": ["该回执只验证生命周期集成，不冒充人工语义审查。"],
        "supersedes_review_id": None,
        "reviewed_at": "2026-07-16T00:00:00+00:00",
    }
    report_ref = f"artifacts/reviews/{filename}.json"
    report = task_dir / report_ref
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    compact = {
        "result": "passed",
        "review_id": review_id,
        "profile": "code-review",
        "scope": scope,
        "target_digest": target["digest"],
        "context_digest": context["digest"],
        "verdict": "passed",
        "report_ref": report_ref,
        "open_counts": receipt["open_counts"],
        "gap_counts": {"blocking": 0, "major": 0, "minor": 0, "total": 0},
        "coverage_summary": {
            "target_paths": len(target_paths),
            "requirements": len(requirement_refs),
            "risks": len(RISK_IDS),
            "context_expansions": 0,
        },
        "lineage_summary": {
            "predecessor_review_id": None,
            "accounted_finding_count": 0,
        },
        "strength_count": 0,
        "summary": receipt["summary"],
    }
    return compact, report_ref


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
    target = run_reviewer_target(
        workspace,
        stage_id=stage_id,
        attempt=1,
    )
    for validation_id in stage["validation_ids"]:
        evidence_ref = write_validation_evidence(task_dir, stage_id, validation_id)
        payload = json.dumps(
            {
                "validation_id": validation_id,
                "result": "passed",
                "command": f"deterministic-eval::{validation_id}",
                "claim_source": "observed",
                "stage_attempt": 1,
                "target_digest": target["digest"],
                "exit_code": 0,
                "summary": "CLI validation passed",
                "claim_boundary": "只证明当前 stage target 的 deterministic fixture。",
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
                "--attempt",
                "1",
                "--payload-json",
                payload,
                "--evidence-ref",
                evidence_ref,
            ],
        )
    review, report_ref = create_review_evidence(
        workspace,
        task_dir,
        scope={"kind": "stage-delta", "stage_id": stage_id, "attempt": 1},
        review_id=f"REV-CODE-{stage_id}-A1",
        target=target,
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
            "--attempt",
            "1",
            "--payload-json",
            json.dumps(review, ensure_ascii=False),
            "--evidence-ref",
            report_ref,
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
    final_review, report_ref = create_review_evidence(
        workspace,
        task_dir,
        scope={"kind": "final-integration"},
        review_id="REV-CODE-FINAL-CLI-001",
    )
    run_cli(
        workspace,
        task_dir,
        "harness_ledger_append.py",
        [
            "--event",
            "review_recorded",
            "--payload-json",
            json.dumps(final_review, ensure_ascii=False),
            "--evidence-ref",
            report_ref,
        ],
    )
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
    for stage in contract["stages"]:
        stage["allowed_changes"] = ["src/**"]
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
    factory.write_current_review(task_dir, contract, "none")
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
