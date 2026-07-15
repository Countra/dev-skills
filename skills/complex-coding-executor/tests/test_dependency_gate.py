from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_dependency_evaluation import (  # noqa: E402
    evaluate_dependency_preflight,
    evaluate_dependency_stage,
)
from harness_dependency_gate import DependencyGateError  # noqa: E402
from harness_execution import ExecutionError, run_planner_approval_check  # noqa: E402
from harness_task_bundle import TaskBundle  # noqa: E402


TODAY = date(2026, 7, 15)
RUNTIME_PATH = "artifacts/execution/dependency-runtime.json"


def dependency_decision() -> dict[str, object]:
    return {
        "id": "DEP-01",
        "action": "add",
        "criticality": "runtime",
        "package": "github.com/example/mainstream",
        "source_repository": "https://example.com/mainstream",
        "selection_class": "ecosystem-mainstream",
        "selected_version": "v1.2.3",
        "version_policy": "pin exact v1.2.3",
        "manifest_paths": ["go.mod", "go.sum"],
        "freshness_max_age_days": 60,
        "evidence_artifact_id": "ART-01",
        "validation_ids": ["VAL-01"],
    }


def approved_artifact(observed_at: str) -> dict[str, object]:
    return {
        "observed_at": observed_at,
        "decisions": [
            {
                "decision_id": "DEP-01",
                "candidates": [
                    {
                        "disposition": "selected",
                        "trust_signals": {
                            "stable_version": {"as_of": observed_at},
                            "adoption_scale": {"as_of": observed_at},
                        },
                    }
                ],
            }
        ],
    }


def runtime_receipt() -> dict[str, object]:
    return {
        "observed_at": TODAY.isoformat(),
        "decisions": [
            {
                "decision_id": "DEP-01",
                "package": "github.com/example/mainstream",
                "source_repository": "https://example.com/mainstream",
                "selection_class": "ecosystem-mainstream",
                "approved_selected_version": "v1.2.3",
                "approved_version_policy": "pin exact v1.2.3",
                "resolved_version": "v1.2.3",
                "manifest_paths": ["go.mod", "go.sum"],
                "version_policy_result": "passed",
                "manifest_result": "passed",
                "lock_result": "passed",
                "hard_gate_checks": {
                    "authenticity": "unchanged",
                    "compatibility": "unchanged",
                    "stable_support": "unchanged",
                    "lifecycle": "unchanged",
                    "security": "unchanged",
                    "license": "unchanged",
                    "reproducibility": "unchanged",
                },
                "evidence_urls": ["https://example.com/official/release"],
                "summary": "Native package-manager and online checks passed.",
            }
        ],
    }


class DependencyGateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.task_dir = self.workspace / ".harness" / "tasks" / "dependency"
        self.artifact_path = (
            self.task_dir / "artifacts" / "dependencies" / "dependency-selection.json"
        )
        self.runtime_path = self.task_dir / RUNTIME_PATH
        self.contract: dict[str, object] = {
            "task_id": "dependency-test",
            "plan_revision": 1,
            "stages": [
                {
                    "id": "STG-01",
                    "allowed_changes": ["go.mod", "go.sum"],
                    "validation_ids": ["VAL-01"],
                }
            ],
            "artifacts": [
                {
                    "id": "ART-01",
                    "path": "artifacts/dependencies/dependency-selection.json",
                }
            ],
            "dependency_selection": {
                "mode": "change",
                "decisions": [dependency_decision()],
            },
        }
        self.write_json(self.artifact_path, approved_artifact(TODAY.isoformat()))
        self.write_json(self.runtime_path, runtime_receipt())

    def write_json(self, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def bundle(
        self,
        contract: dict[str, object] | None = None,
        *,
        task_dir: Path | None = None,
    ) -> TaskBundle:
        selected_task_dir = task_dir or self.task_dir
        return TaskBundle(
            workspace=self.workspace,
            pointer_path=self.workspace / ".harness" / "active-task.json",
            task_dir=selected_task_dir,
            plan_path=selected_task_dir / "execution-plan.md",
            contract_path=selected_task_dir / "plan-contract.json",
            attestation_path=selected_task_dir / "attestation.json",
            run_state_path=selected_task_dir / "run-state.json",
            ledger_path=selected_task_dir / "ledger.jsonl",
            pointer=None,
            contract=contract or self.contract,
        )

    def assert_code(self, code: str, operation: object) -> None:
        with self.assertRaises(DependencyGateError) as raised:
            operation()
        self.assertEqual(code, raised.exception.code)

    def mutate_runtime(self, operation: object) -> None:
        receipt = runtime_receipt()
        operation(receipt["decisions"][0])
        self.write_json(self.runtime_path, receipt)

    def test_none_mode_is_constant_time_not_applicable(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["dependency_selection"] = {"mode": "none", "decisions": []}
        result = evaluate_dependency_preflight(self.bundle(contract), today=TODAY)
        self.assertEqual(("none", "not-applicable"), (result["mode"], result["result"]))

    def test_fresh_preflight_and_stage_native_validation_pass(self) -> None:
        preflight = evaluate_dependency_preflight(self.bundle(), today=TODAY)
        self.assertEqual([], preflight["stale_approved_decision_ids"])
        stage = evaluate_dependency_stage(
            self.bundle(),
            "STG-01",
            RUNTIME_PATH,
            today=TODAY,
        )
        self.assertEqual("passed", stage["result"])

    def test_equivalent_task_root_alias_passes_both_dependency_gates(self) -> None:
        aliased_task_dir = self.task_dir.parent / "unused" / ".." / self.task_dir.name
        bundle = self.bundle(task_dir=aliased_task_dir)

        preflight = evaluate_dependency_preflight(bundle, today=TODAY)
        stage = evaluate_dependency_stage(
            bundle,
            "STG-01",
            RUNTIME_PATH,
            today=TODAY,
        )

        self.assertEqual("passed", preflight["result"])
        self.assertEqual("passed", stage["result"])
        self.assertEqual(RUNTIME_PATH, stage["runtime_receipt"]["path"])

    def test_stale_approval_requires_complete_runtime_recheck(self) -> None:
        self.write_json(self.artifact_path, approved_artifact("2026-01-01"))
        self.assert_code(
            "EXEC_DEPENDENCY_EVIDENCE_STALE",
            lambda: evaluate_dependency_preflight(self.bundle(), today=TODAY),
        )
        result = evaluate_dependency_preflight(
            self.bundle(),
            RUNTIME_PATH,
            today=TODAY,
        )
        self.assertEqual(["DEP-01"], result["stale_approved_decision_ids"])

    def test_unapproved_package_and_manifest_are_rejected(self) -> None:
        self.mutate_runtime(
            lambda item: item.update({"package": "github.com/example/substitute"})
        )
        self.assert_code(
            "EXEC_DEPENDENCY_APPROVAL_DRIFT",
            lambda: evaluate_dependency_preflight(self.bundle(), RUNTIME_PATH, today=TODAY),
        )
        self.mutate_runtime(lambda item: item.update({"manifest_paths": ["vendor.lock"]}))
        self.assert_code(
            "EXEC_DEPENDENCY_APPROVAL_DRIFT",
            lambda: evaluate_dependency_preflight(self.bundle(), RUNTIME_PATH, today=TODAY),
        )

    def test_version_policy_failure_is_implementation_drift(self) -> None:
        self.mutate_runtime(lambda item: item.update({"version_policy_result": "failed"}))
        self.assert_code(
            "EXEC_DEPENDENCY_IMPLEMENTATION_DRIFT",
            lambda: evaluate_dependency_stage(
                self.bundle(), "STG-01", RUNTIME_PATH, today=TODAY
            ),
        )

    def test_security_or_lifecycle_change_is_research_drift(self) -> None:
        def change_security(item: dict[str, object]) -> None:
            item["hard_gate_checks"]["security"] = "changed"

        self.mutate_runtime(change_security)
        self.assert_code(
            "EXEC_DEPENDENCY_RESEARCH_DRIFT",
            lambda: evaluate_dependency_preflight(self.bundle(), RUNTIME_PATH, today=TODAY),
        )

    def test_blocked_recheck_and_secret_url_fail_closed(self) -> None:
        def block_lifecycle(item: dict[str, object]) -> None:
            item["hard_gate_checks"]["lifecycle"] = "blocked-by-access"

        self.mutate_runtime(block_lifecycle)
        self.assert_code(
            "EXEC_DEPENDENCY_RECHECK_BLOCKED",
            lambda: evaluate_dependency_preflight(self.bundle(), RUNTIME_PATH, today=TODAY),
        )
        self.mutate_runtime(
            lambda item: item.update(
                {"evidence_urls": ["https://example.com/release?token=secret"]}
            )
        )
        self.assert_code(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            lambda: evaluate_dependency_preflight(self.bundle(), RUNTIME_PATH, today=TODAY),
        )

    def test_change_manifest_must_map_to_approved_stage(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["dependency_selection"]["decisions"][0]["manifest_paths"] = ["vendor.lock"]
        self.assert_code(
            "EXEC_DEPENDENCY_STAGE_UNMAPPED",
            lambda: evaluate_dependency_preflight(self.bundle(contract), today=TODAY),
        )

    def test_planner_stale_only_diagnostic_requires_explicit_allowance(self) -> None:
        stale = json.dumps(
            {
                "valid": False,
                "issues": [{"code": "TASK_DEPENDENCY_EVIDENCE_STALE"}],
            }
        )
        with mock.patch(
            "harness_execution.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=stale, stderr=""),
        ):
            run_planner_approval_check(self.bundle(), allow_dependency_stale=True)
            with self.assertRaises(ExecutionError):
                run_planner_approval_check(self.bundle(), allow_dependency_stale=False)

    def test_planner_stale_allowance_never_hides_other_errors(self) -> None:
        mixed = json.dumps(
            {
                "valid": False,
                "issues": [
                    {"code": "TASK_DEPENDENCY_EVIDENCE_STALE"},
                    {"code": "TASK_PLAN_GATE_EMPTY"},
                ],
            }
        )
        with mock.patch(
            "harness_execution.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=mixed, stderr=""),
        ):
            with self.assertRaises(ExecutionError):
                run_planner_approval_check(self.bundle(), allow_dependency_stale=True)


if __name__ == "__main__":
    unittest.main()
