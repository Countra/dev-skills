from __future__ import annotations

import sys
import unittest
from pathlib import Path

from helpers import (
    WritableTemporaryDirectory,
    compact_contract,
    write_bundle,
    write_json,
)


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from harness_contract import validate_contract  # noqa: E402
from harness_plan_check import validate_task  # noqa: E402


class CompactPlanCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.task_dir = Path(temporary.name) / "task"

    @staticmethod
    def codes(issues) -> set[str]:
        return {issue.code for issue in issues if issue.severity == "error"}

    @staticmethod
    def add_second_stage(contract: dict) -> None:
        contract["stages"].append(
            {
                "id": "STG-02",
                "title": "完成集成",
                "depends_on": ["STG-01"],
                "scope": ["skills/example"],
                "risk": "medium",
                "validation_ids": ["VAL-02"],
                "review": "same-context",
            }
        )
        contract["validations"].append(
            {
                "id": "VAL-02",
                "stage_id": "STG-02",
                "command": "python -m unittest integration",
                "required": True,
                "timeout_seconds": 300,
            }
        )

    def test_valid_contract_and_flexible_plan_pass(self) -> None:
        write_bundle(self.task_dir)
        self.assertEqual(set(), self.codes(validate_task(self.task_dir, "approval")))

    def test_old_heavy_contract_is_rejected(self) -> None:
        contract = compact_contract()
        contract["requirements"] = []
        issues = validate_contract(contract)
        self.assertIn("PLAN_CONTRACT_UNSUPPORTED", self.codes(issues))

    def test_cycle_and_unknown_dependency_fail(self) -> None:
        contract = compact_contract()
        contract["stages"][0]["depends_on"] = ["STG-01", "STG-99"]
        codes = self.codes(validate_contract(contract))
        self.assertIn("PLAN_STAGE_CYCLE", codes)
        self.assertIn("PLAN_STAGE_DEPENDENCY_UNKNOWN", codes)

    def test_stage_scope_must_stay_inside_approved_scope(self) -> None:
        contract = compact_contract()
        contract["stages"][0]["scope"] = ["skills/unapproved"]
        self.assertIn(
            "PLAN_STAGE_SCOPE_OUTSIDE",
            self.codes(validate_contract(contract)),
        )

    def test_stage_scope_can_use_approved_child_path(self) -> None:
        contract = compact_contract()
        contract["stages"][0]["scope"] = ["skills/example/scripts"]
        self.assertEqual(set(), self.codes(validate_contract(contract)))

    def test_scope_rejects_traversal_and_supports_workspace_root(self) -> None:
        contract = compact_contract()
        contract["stages"][0]["scope"] = ["skills/example/../outside"]
        self.assertIn("PLAN_SCOPE_INVALID", self.codes(validate_contract(contract)))

        contract = compact_contract()
        contract["scope"] = ["C:relative"]
        self.assertIn("PLAN_SCOPE_INVALID", self.codes(validate_contract(contract)))

        contract = compact_contract()
        contract["scope"] = ["."]
        contract["stages"][0]["scope"] = ["skills/example/scripts"]
        self.assertEqual(set(), self.codes(validate_contract(contract)))

    def test_malformed_collection_does_not_crash_plan_check(self) -> None:
        contract = compact_contract()
        contract["stages"] = None
        self.task_dir.mkdir(parents=True)
        write_json(self.task_dir / "plan-contract.json", contract)
        self.task_dir.joinpath("execution-plan.md").write_text(
            "# Invalid contract\n",
            encoding="utf-8",
        )
        self.assertIn(
            "PLAN_STAGE_INVALID",
            self.codes(validate_task(self.task_dir, "draft")),
        )

    def test_validation_must_match_owning_stage(self) -> None:
        contract = compact_contract()
        contract["validations"][0]["stage_id"] = "STG-99"
        codes = self.codes(validate_contract(contract))
        self.assertIn("PLAN_VALIDATION_STAGE_UNKNOWN", codes)
        self.assertIn("PLAN_VALIDATION_STAGE_MISMATCH", codes)

    def test_multistage_contract_requires_final_validation(self) -> None:
        contract = compact_contract()
        self.add_second_stage(contract)
        self.assertIn(
            "PLAN_FINAL_VALIDATION_REQUIRED",
            self.codes(validate_contract(contract)),
        )

        contract["validations"].append(
            {
                "id": "VAL-FINAL",
                "stage_id": "final",
                "command": "python -m unittest full-suite",
                "required": True,
                "timeout_seconds": 900,
            }
        )
        contract["final_validation_ids"] = ["VAL-FINAL"]
        self.assertEqual(set(), self.codes(validate_contract(contract)))

    def test_final_validation_must_use_final_owner(self) -> None:
        contract = compact_contract()
        self.add_second_stage(contract)
        contract["final_validation_ids"] = ["VAL-02"]
        self.assertIn(
            "PLAN_VALIDATION_STAGE_MISMATCH",
            self.codes(validate_contract(contract)),
        )

    def test_single_stage_contract_can_omit_final_validation_list(self) -> None:
        contract = compact_contract()
        contract.pop("final_validation_ids")
        self.assertEqual(set(), self.codes(validate_contract(contract)))

    def test_required_validation_must_be_referenced_by_stage(self) -> None:
        contract = compact_contract()
        contract["stages"][0]["validation_ids"] = ["VAL-02"]
        contract["validations"].append(
            {
                "id": "VAL-02",
                "stage_id": "STG-01",
                "command": "python -m unittest focused",
                "required": False,
                "timeout_seconds": 300,
            }
        )
        self.assertIn(
            "PLAN_VALIDATION_UNREFERENCED",
            self.codes(validate_contract(contract)),
        )

    def test_validation_timeout_must_be_finite_and_bounded(self) -> None:
        for timeout in (float("nan"), float("inf"), 0, 86_401):
            with self.subTest(timeout=timeout):
                contract = compact_contract()
                contract["validations"][0]["timeout_seconds"] = timeout
                self.assertIn(
                    "PLAN_VALIDATION_TIMEOUT_INVALID",
                    self.codes(validate_contract(contract)),
                )

    def test_high_risk_requires_independent_review(self) -> None:
        contract = compact_contract(risk="high")
        contract["stages"][0]["review"] = "same-context"
        contract["final_review"] = "same-context"
        self.assertIn("PLAN_REVIEW_REQUIRED", self.codes(validate_contract(contract)))

    def test_task_risk_cannot_be_lower_than_stage_risk(self) -> None:
        contract = compact_contract(risk="medium")
        contract["stages"][0]["risk"] = "high"
        contract["stages"][0]["review"] = "independent"
        self.assertIn("PLAN_RISK_UNDERSCOPED", self.codes(validate_contract(contract)))

    def test_plan_must_reference_stages_and_validations(self) -> None:
        contract = compact_contract()
        self.task_dir.mkdir(parents=True)
        write_json(self.task_dir / "plan-contract.json", contract)
        self.task_dir.joinpath("execution-plan.md").write_text(
            "# Missing references\n",
            encoding="utf-8",
        )
        self.assertIn(
            "PLAN_DOCUMENT_REFERENCE_MISSING",
            self.codes(validate_task(self.task_dir, "draft")),
        )

    def test_approval_rejects_placeholders_without_fixed_sections(self) -> None:
        write_bundle(self.task_dir)
        path = self.task_dir / "execution-plan.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n<任务名称>\n", encoding="utf-8")
        self.assertIn(
            "PLAN_DOCUMENT_PLACEHOLDER",
            self.codes(validate_task(self.task_dir, "approval")),
        )


if __name__ == "__main__":
    unittest.main()
