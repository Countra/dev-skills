"""JSON/Markdown 报告的透明性测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import SCRIPT_ROOT as _SCRIPT_ROOT
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.reports import build_report, render_markdown


FINGERPRINT = "f" * 64
LAB_IDENTITY = {"tree_sha256": "a" * 64, "file_count": 1}
SOURCE_IDENTITY = {
    "candidate": {"tree_sha256": "d" * 64, "file_count": 1},
    "baseline": "none",
}


def record(variant: str, passed: bool) -> dict[str, object]:
    assertion_status = "PASS" if passed else "FAIL"
    return {
        "record_key": f"case:1:{variant}",
        "case_id": "case",
        "mode": "behavior",
        "split": "validation",
        "variant": variant,
        "repetition": 1,
        "pairing": {
            "pair_key": "case:1",
            "prompt_sha256": "b" * 64,
            "inputs": [],
            "model": "model",
            "sandbox": "workspace-write",
            "timeout_seconds": 30,
            "network_access": False,
            "skill_snapshot": variant if variant == "candidate" else "none",
        },
        "deterministic": {
            "passed": passed,
            "status": "PASS" if passed else "FAIL",
            "failure_type": None if passed else "requirement_failure",
            "assertions": {
                "status": assertion_status,
                "counts": {"PASS": int(passed), "FAIL": int(not passed), "ERROR": 0},
                "results": [
                    {
                        "assertion_id": "result",
                        "type": "file_exists",
                        "status": assertion_status,
                        "message": "fixture",
                        "evidence": {},
                    }
                ],
            },
        },
        "usage": {"input_tokens": 4, "output_tokens": 2},
        "duration_seconds": None,
        "provenance": {
            "fingerprint": FINGERPRINT,
            "lab_tree_sha256": "a" * 64,
            "adapter": "fake",
            "cli_version": "fake",
            "model": "model",
            "sandbox": "workspace-write",
            "network_access": False,
            "prompt_sha256": "b" * 64,
            "case_id": "case",
            "attempt": 1,
            "variant": variant,
            **({"skill_tree_sha256": "d" * 64} if variant == "candidate" else {}),
        },
        "human_feedback": None,
        "trigger": None,
    }


def grade_document(
    records: list[dict[str, object]],
    *,
    judge: dict[str, object] | None = None,
    run_state: str = "completed",
    run_status: str = "PASS",
    run_error: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_state": run_state,
        "run_status": run_status,
        "run_error": run_error,
        "suite_id": "suite",
        "run_id": "run",
        "fingerprint": FINGERPRINT,
        "source_identity": SOURCE_IDENTITY,
        "lab_identity": LAB_IDENTITY,
        "grader_identity": {"tree_sha256": "e" * 64, "file_count": 1},
        "gates": {
            "trigger_threshold": 0.8,
            "required_case_pass_rate": 1.0,
            "judge_required": False,
        },
        "records": records,
        "judge": judge or {"status": "disabled", "authority": "none"},
    }


class ReportTests(unittest.TestCase):
    def test_report_exposes_quality_cost_uncertainty_and_failures(self) -> None:
        grade = grade_document(
            [record("candidate", True), record("baseline", False)],
            judge={
                "status": "candidate",
                "authority": "advisory",
                "calibrated": False,
                "translated_winners": ["candidate", "candidate"],
                "mean_confidence": 0.8,
            },
            run_status="FAIL",
        )
        report = build_report(grade)
        markdown = render_markdown(report)
        serialized = json.dumps(report, sort_keys=True)

        self.assertEqual(report["quality"]["candidate"]["n"], 1)
        self.assertEqual(report["paired_delta"]["wins"], 1)
        self.assertEqual(report["failure_taxonomy"], {"requirement_failure": 1})
        self.assertTrue(report["uncertainty"]["small_sample"])
        self.assertTrue(report["uncertainty"]["judge_advisory_only"])
        self.assertFalse(report["uncertainty"]["duration_available"])
        self.assertFalse(report["uncertainty"]["token_usage_complete"])
        self.assertTrue(report["gate_decisions"]["all_required_passed"])
        self.assertEqual(report["case_results"][0]["record_key"], "case:1:candidate")
        self.assertEqual(report["provenance"]["execution_groups"][0]["record_count"], 2)
        self.assertNotIn("overall_score", serialized)
        self.assertIn("Wilson 95% interval", markdown)
        self.assertIn("Quality By Mode", markdown)
        self.assertIn("Human Feedback", markdown)
        self.assertIn("Gate Decisions", markdown)
        self.assertIn("Case Results", markdown)
        self.assertIn("Provenance", markdown)
        self.assertIn("Low information", markdown)
        self.assertIn("requirement_failure: 1", markdown)

    def test_required_judge_fails_closed_without_calibrated_decision(self) -> None:
        grade = grade_document(
            [record("candidate", True), record("baseline", True)],
            judge={
                "status": "candidate",
                "authority": "advisory",
                "calibrated": False,
                "translated_winners": ["candidate", "candidate"],
                "mean_confidence": 0.8,
            },
        )
        grade["gates"]["judge_required"] = True
        report = build_report(grade)
        judge_gate = next(
            item for item in report["gate_decisions"]["decisions"] if item["name"] == "judge_required"
        )
        self.assertFalse(judge_gate["passed"])
        self.assertEqual(judge_gate["reason"], "judge_not_candidate_decision")
        self.assertFalse(report["gate_decisions"]["all_required_passed"])

    def test_invalid_gate_threshold_is_rejected(self) -> None:
        grade = grade_document([record("candidate", True), record("baseline", True)])
        grade["gates"]["trigger_threshold"] = 2
        with self.assertRaisesRegex(SuiteError, "gate threshold"):
            build_report(grade)

    def test_failed_run_can_never_pass_required_gates(self) -> None:
        grade = grade_document(
            [],
            run_state="failed",
            run_status="ERROR",
            run_error={"code": "execution_failed", "message": "runner stopped", "outcome": "unknown"},
        )
        report = build_report(grade)
        markdown = render_markdown(report)
        run_gate = next(
            item for item in report["gate_decisions"]["decisions"] if item["name"] == "run_completed"
        )

        self.assertFalse(run_gate["passed"])
        self.assertFalse(report["gate_decisions"]["all_required_passed"])
        self.assertFalse(report["uncertainty"]["run_completed"])
        self.assertIn("execution_failed", markdown)

    def test_reported_run_status_conflict_fails_required_gate(self) -> None:
        grade = grade_document(
            [record("candidate", True), record("baseline", True)],
            run_status="FAIL",
        )
        report = build_report(grade)
        consistency = next(
            item
            for item in report["gate_decisions"]["decisions"]
            if item["name"] == "run_status_consistent"
        )

        self.assertFalse(consistency["passed"])
        self.assertFalse(report["gate_decisions"]["all_required_passed"])
        self.assertFalse(report["uncertainty"]["run_status_consistent"])

    def test_grade_root_rejects_unknown_fields(self) -> None:
        grade = grade_document([record("candidate", True), record("baseline", True)])
        grade["unexpected"] = True
        with self.assertRaisesRegex(SuiteError, "未知字段"):
            build_report(grade)

    def test_completed_grade_rejects_empty_or_incomplete_behavior_records(self) -> None:
        with self.assertRaisesRegex(SuiteError, "必须包含 records"):
            build_report(grade_document([]))
        with self.assertRaisesRegex(SuiteError, "pair 不完整"):
            build_report(grade_document([record("candidate", True)]))


if __name__ == "__main__":
    unittest.main()
