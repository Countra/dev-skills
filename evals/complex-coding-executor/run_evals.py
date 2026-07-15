#!/usr/bin/env python3
"""执行 planner→executor conformance、恢复与回归评测。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from cli_scenarios import run_amendment_cli, run_complete_cli


REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTOR_SCRIPTS = REPO_ROOT / "skills" / "complex-coding-executor" / "scripts"
sys.path.insert(0, str(EXECUTOR_SCRIPTS))

from harness_attestation import build_attestation, write_attestation  # noqa: E402
from harness_dependency_evaluation import (  # noqa: E402
    evaluate_dependency_preflight,
    evaluate_dependency_stage,
)
from harness_event_writer import append_event_and_update  # noqa: E402
from harness_execution import (  # noqa: E402
    check_final,
    check_preflight,
    check_transition,
    reconcile_snapshot,
    run_planner_approval_check,
    status_payload,
)
from harness_task_bundle import resolve_task_bundle  # noqa: E402


EVAL_TODAY = date(2026, 7, 15)
DEPENDENCY_RUNTIME_PATH = "artifacts/execution/dependency-runtime.json"


def load_planner_factory() -> ModuleType:
    path = REPO_ROOT / "evals" / "complex-coding-planner" / "run_evals.py"
    spec = importlib.util.spec_from_file_location("planner_eval_factory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 planner fixture factory：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_pointer(workspace: Path, task_dir: Path, task_id: str) -> None:
    pointer = {
        "task_id": task_id,
        "task_dir": task_dir.relative_to(workspace).as_posix(),
        "run_state_path": "run-state.json",
        "updated_at": "2026-07-10T00:00:00+00:00",
    }
    path = workspace / ".harness" / "active-task.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_workspace(
    root: Path,
    case: dict[str, Any],
    factory: ModuleType,
) -> tuple[Path, Path]:
    workspace = root / case["id"]
    task_dir = workspace / ".harness" / "tasks" / case["id"]
    task_dir.mkdir(parents=True)
    contract = factory.build_contract(case["id"], case["profile"])
    if case.get("commit_expectation"):
        for stage in contract["stages"]:
            stage["commit_expectation"] = case["commit_expectation"]
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
    write_pointer(workspace, task_dir, case["id"])
    return workspace, task_dir


def approve(bundle: Any, *, commit_authorized: bool = False) -> None:
    payload = build_attestation(
        bundle,
        approved_by="eval-user",
        approval_summary="approved for deterministic evaluation",
        commit_authorized=commit_authorized,
        approved_at="2026-07-10T00:00:00+00:00",
    )
    write_attestation(bundle.attestation_path, payload)


def complete_lifecycle(bundle: Any, *, commit_authorized: bool) -> None:
    check_preflight(bundle)
    append_event_and_update(bundle, "execution_started")
    for stage in bundle.contract["stages"]:
        stage_id = stage["id"]
        append_event_and_update(
            bundle,
            "stage_started",
            stage_id=stage_id,
            attempt=1,
        )
        for validation_id in stage["validation_ids"]:
            append_event_and_update(
                bundle,
                "validation_recorded",
                stage_id=stage_id,
                payload={
                    "validation_id": validation_id,
                    "result": "passed",
                    "summary": "deterministic validation passed",
                },
            )
        append_event_and_update(
            bundle,
            "review_recorded",
            stage_id=stage_id,
            payload={
                "result": "passed",
                "summary": "stage review passed",
                "development_quality": "passed",
            },
        )
        append_event_and_update(bundle, "stage_completed", stage_id=stage_id)
        if commit_authorized and stage["commit_expectation"] == "stage":
            append_event_and_update(
                bundle,
                "commit_recorded",
                stage_id=stage_id,
                payload={
                    "commit": f"{len(stage_id):040x}",
                    "repository": "eval-workspace",
                },
            )
        check_transition(bundle)
    if commit_authorized and any(
        stage["commit_expectation"] == "final"
        for stage in bundle.contract["stages"]
    ):
        append_event_and_update(
            bundle,
            "commit_recorded",
            payload={
                "commit": "0123456789abcdef",
                "repository": "eval-workspace",
            },
        )
    append_event_and_update(bundle, "completed")


def expect_error(expected_code: str, action: Callable[[], Any]) -> str:
    try:
        action()
    except Exception as exc:  # noqa: BLE001 - 评测必须捕获所有公开错误类型
        code = getattr(exc, "code", type(exc).__name__)
        if code != expected_code:
            raise AssertionError(f"期望 {expected_code}，实际 {code}: {exc}") from exc
        return str(code)
    raise AssertionError(f"期望错误 {expected_code}，但操作成功。")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def configure_dependency_case(
    bundle: Any,
    *,
    approved_observed_at: str = "2026-07-10",
    runtime_overrides: dict[str, Any] | None = None,
    hard_gate_overrides: dict[str, str] | None = None,
) -> str:
    artifact_id = "ART-DEP-01"
    artifact_path = "artifacts/dependencies/dependency-selection.json"
    decision = {
        "id": "DEP-01",
        "action": "add",
        "criticality": "runtime",
        "package": "github.com/gin-gonic/gin",
        "source_repository": "https://github.com/gin-gonic/gin",
        "selection_class": "ecosystem-mainstream",
        "selected_version": "v1.10.1",
        "version_policy": "pin exact v1.10.1",
        "manifest_paths": ["go.mod", "go.sum"],
        "freshness_max_age_days": 60,
        "evidence_artifact_id": artifact_id,
        "validation_ids": ["VAL-01"],
    }
    bundle.contract["dependency_selection"] = {
        "mode": "change",
        "decisions": [decision],
    }
    bundle.contract["artifacts"] = [
        *bundle.contract.get("artifacts", []),
        {"id": artifact_id, "path": artifact_path},
    ]
    allowed_changes = bundle.contract["stages"][0]["allowed_changes"]
    for manifest_path in decision["manifest_paths"]:
        if manifest_path not in allowed_changes:
            allowed_changes.append(manifest_path)
    write_json(
        bundle.task_dir / artifact_path,
        {
            "observed_at": approved_observed_at,
            "decisions": [
                {
                    "decision_id": "DEP-01",
                    "candidates": [
                        {
                            "disposition": "selected",
                            "trust_signals": {
                                "stable_version": {"as_of": approved_observed_at},
                                "adoption_scale": {"as_of": approved_observed_at},
                            },
                        }
                    ],
                }
            ],
        },
    )
    hard_gates = {
        "authenticity": "unchanged",
        "compatibility": "unchanged",
        "stable_support": "unchanged",
        "lifecycle": "unchanged",
        "security": "unchanged",
        "license": "unchanged",
        "reproducibility": "unchanged",
    }
    hard_gates.update(hard_gate_overrides or {})
    runtime_decision = {
        "decision_id": "DEP-01",
        "package": "github.com/gin-gonic/gin",
        "source_repository": "https://github.com/gin-gonic/gin",
        "selection_class": "ecosystem-mainstream",
        "approved_selected_version": "v1.10.1",
        "approved_version_policy": "pin exact v1.10.1",
        "resolved_version": "v1.10.1",
        "manifest_paths": ["go.mod", "go.sum"],
        "version_policy_result": "passed",
        "manifest_result": "passed",
        "lock_result": "passed",
        "hard_gate_checks": hard_gates,
        "evidence_urls": ["https://github.com/gin-gonic/gin/releases"],
        "summary": "Native manifest and approved dependency checks passed.",
    }
    runtime_decision.update(runtime_overrides or {})
    write_json(
        bundle.task_dir / DEPENDENCY_RUNTIME_PATH,
        {
            "observed_at": EVAL_TODAY.isoformat(),
            "decisions": [runtime_decision],
        },
    )
    return DEPENDENCY_RUNTIME_PATH


def run_complete(bundle: Any, case: dict[str, Any]) -> dict[str, Any]:
    authorized = case["commit_authorized"]
    approve(bundle, commit_authorized=authorized)
    run_planner_approval_check(bundle)
    complete_lifecycle(bundle, commit_authorized=authorized)
    bundle.pointer_path.unlink()
    check_final(bundle)
    status = status_payload(bundle)
    return {
        "lifecycle": status["lifecycle"],
        "event_count": status["last_event_seq"],
        "completed_stages": len(status["completed_stage_ids"]),
    }


def run_snapshot_reconcile(bundle: Any) -> dict[str, Any]:
    approve(bundle)
    append_event_and_update(bundle, "execution_started")
    bundle.run_state_path.unlink()
    before = status_payload(bundle)
    result = reconcile_snapshot(bundle)
    after = status_payload(bundle)
    if not before["snapshot_drift"] or not result["reconciled"]:
        raise AssertionError("snapshot 丢失未触发 reconcile。")
    if after["snapshot_drift"]:
        raise AssertionError("reconcile 后仍存在 snapshot drift。")
    return {"reconciled": True, "event_count": after["last_event_seq"]}


def run_regression(bundle: Any, case: dict[str, Any]) -> dict[str, Any]:
    scenario = case["scenario"]
    if scenario == "dependency-none-fast":
        result = evaluate_dependency_preflight(bundle, today=EVAL_TODAY)
        if (result["mode"], result["result"]) != ("none", "not-applicable"):
            raise AssertionError(f"none 快路径返回异常：{result}")
        return {"mode": result["mode"], "result": result["result"]}
    if scenario == "dependency-stale-recheck":
        runtime_path = configure_dependency_case(
            bundle,
            approved_observed_at="2026-01-01",
        )
        result = evaluate_dependency_preflight(
            bundle,
            runtime_path,
            today=EVAL_TODAY,
        )
        return {
            "result": result["result"],
            "stale_decision_ids": result["stale_approved_decision_ids"],
            "runtime_recheck": result["runtime_recheck"] is not None,
        }
    expected = case["expected_code"]
    if scenario == "dependency-unapproved-package":
        runtime_path = configure_dependency_case(
            bundle,
            runtime_overrides={"package": "github.com/example/substitute"},
        )
        code = expect_error(
            expected,
            lambda: evaluate_dependency_preflight(
                bundle,
                runtime_path,
                today=EVAL_TODAY,
            ),
        )
    elif scenario == "dependency-version-out-of-policy":
        runtime_path = configure_dependency_case(
            bundle,
            runtime_overrides={"version_policy_result": "failed"},
        )
        stage_id = bundle.contract["stages"][0]["id"]
        code = expect_error(
            expected,
            lambda: evaluate_dependency_stage(
                bundle,
                stage_id,
                runtime_path,
                today=EVAL_TODAY,
            ),
        )
    elif scenario == "dependency-stale-without-recheck":
        configure_dependency_case(bundle, approved_observed_at="2026-01-01")
        code = expect_error(
            expected,
            lambda: evaluate_dependency_preflight(bundle, today=EVAL_TODAY),
        )
    elif scenario == "dependency-advisory-drift":
        runtime_path = configure_dependency_case(
            bundle,
            hard_gate_overrides={"security": "changed"},
        )
        code = expect_error(
            expected,
            lambda: evaluate_dependency_preflight(
                bundle,
                runtime_path,
                today=EVAL_TODAY,
            ),
        )
    elif scenario == "missing-attestation":
        code = expect_error(expected, lambda: check_preflight(bundle))
    elif scenario == "tampered-plan":
        approve(bundle)
        bundle.plan_path.write_text(
            bundle.plan_path.read_text(encoding="utf-8") + "\nTampered.\n",
            encoding="utf-8",
        )
        code = expect_error(expected, lambda: check_preflight(bundle))
    elif scenario == "illegal-stage-completion":
        approve(bundle)
        append_event_and_update(bundle, "execution_started")
        stage_id = bundle.contract["stages"][0]["id"]
        append_event_and_update(
            bundle,
            "stage_started",
            stage_id=stage_id,
            attempt=1,
        )
        code = expect_error(
            expected,
            lambda: append_event_and_update(
                bundle,
                "stage_completed",
                stage_id=stage_id,
            ),
        )
    elif scenario == "active-pointer-not-closed":
        approve(bundle)
        complete_lifecycle(bundle, commit_authorized=False)
        code = expect_error(expected, lambda: check_final(bundle))
    elif scenario == "missing-stage-commit":
        approve(bundle, commit_authorized=True)
        code = expect_error(
            expected,
            lambda: complete_lifecycle(bundle, commit_authorized=False),
        )
    else:
        raise ValueError(f"未知 regression scenario：{scenario}")
    return {"actual_code": code}


def evaluate_case(
    root: Path,
    suite: str,
    case: dict[str, Any],
    factory: ModuleType,
) -> dict[str, Any]:
    workspace, task_dir = build_workspace(root, case, factory)
    try:
        if case["scenario"] == "missing-contract":
            (task_dir / "plan-contract.json").unlink()
            actual_code = expect_error(
                case["expected_code"],
                lambda: resolve_task_bundle(workspace, task_dir),
            )
            details = {"actual_code": actual_code}
        else:
            bundle = resolve_task_bundle(workspace, task_dir)
            if case["scenario"] == "complete":
                details = run_complete(bundle, case)
            elif case["scenario"] == "complete-cli":
                details = run_complete_cli(workspace, task_dir, bundle)
            elif case["scenario"] == "amendment-cli":
                details = run_amendment_cli(
                    workspace,
                    task_dir,
                    bundle,
                    factory,
                )
            elif case["scenario"] == "snapshot-loss-reconcile":
                details = run_snapshot_reconcile(bundle)
            else:
                details = run_regression(bundle, case)
        passed = True
        error = None
    except Exception as exc:  # noqa: BLE001 - 单个 case 失败不能中断整套评测
        details = {"actual_code": getattr(exc, "code", type(exc).__name__)}
        passed = False
        error = str(exc)
    return {
        "id": case["id"],
        "suite": suite,
        "profile": case["profile"],
        "scenario": case["scenario"],
        "passed": passed,
        "error": error,
        "details": details,
    }


def load_cases(path: Path) -> list[tuple[str, dict[str, Any]]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    result: list[tuple[str, dict[str, Any]]] = []
    for suite in ("capability", "regression"):
        cases = manifest.get(suite)
        if not isinstance(cases, list):
            raise ValueError(f"manifest.{suite} 必须是数组。")
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError(f"manifest.{suite} case 必须是 object。")
            result.append((suite, case))
    return result


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(item["passed"] for item in results)
    complete_results = [
        item
        for item in results
        if item["scenario"] in {"complete", "complete-cli"} and item["passed"]
    ]
    complete_total = sum(
        item["scenario"] in {"complete", "complete-cli"} for item in results
    )
    return {
        "suite": "complex-coding-executor",
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "metrics": {
            "consumer_acceptance_rate": round(
                len(complete_results) / complete_total,
                3,
            )
            if complete_total
            else 0,
            "completed_stage_count": sum(
                item["details"].get("completed_stages", 0)
                for item in complete_results
            ),
            "recovery_cases": sum(
                item["scenario"] == "snapshot-loss-reconcile" for item in results
            ),
            "amendment_cases": sum(
                item["scenario"] == "amendment-cli" for item in results
            ),
            "regression_cases": sum(item["suite"] == "regression" for item in results),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 planner→executor 联合评测")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("manifest.json"),
    )
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)

    factory = load_planner_factory()
    with tempfile.TemporaryDirectory(dir=args.work_dir) as temporary:
        root = Path(temporary)
        results = [
            evaluate_case(root, suite, case, factory)
            for suite, case in load_cases(args.manifest.resolve())
        ]
    report = build_report(results)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
