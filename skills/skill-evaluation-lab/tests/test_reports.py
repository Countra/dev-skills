"""JSON/Markdown 报告的透明性测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import SCRIPT_ROOT as _SCRIPT_ROOT
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.reports import build_report, render_markdown


def record(variant: str, passed: bool) -> dict[str, object]:
    return {
        "record_key": f"case:1:{variant}",
        "case_id": "case",
        "mode": "behavior",
        "variant": variant,
        "repetition": 1,
        "pairing": {
            "pair_key": "case:1",
            "prompt_sha256": "prompt",
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
        },
        "usage": {"input_tokens": 4, "output_tokens": 2},
        "duration_seconds": None,
        "provenance": {
            "fingerprint": "fp",
            "lab_tree_sha256": "a" * 64,
            "adapter": "fake",
            "model": "model",
            "sandbox": "workspace-write",
            "network_access": False,
        },
        "human_feedback": None,
    }


class ReportTests(unittest.TestCase):
    def test_report_exposes_quality_cost_uncertainty_and_failures(self) -> None:
        grade = {
            "suite_id": "suite",
            "run_id": "run",
            "fingerprint": "fp",
            "source_identity": {"candidate": {"tree_sha256": "hash"}, "baseline": "none"},
            "gates": {
                "trigger_threshold": 0.8,
                "required_case_pass_rate": 1.0,
                "judge_required": False,
            },
            "records": [record("candidate", True), record("baseline", False)],
            "judge": {"status": "candidate", "authority": "advisory"},
        }
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
        grade = {
            "suite_id": "suite",
            "run_id": "run",
            "fingerprint": "fp",
            "source_identity": {},
            "gates": {
                "trigger_threshold": 0.8,
                "required_case_pass_rate": 1.0,
                "judge_required": True,
            },
            "records": [record("candidate", True), record("baseline", True)],
            "judge": {"status": "candidate", "authority": "advisory"},
        }
        report = build_report(grade)
        judge_gate = next(
            item for item in report["gate_decisions"]["decisions"] if item["name"] == "judge_required"
        )
        self.assertFalse(judge_gate["passed"])
        self.assertEqual(judge_gate["reason"], "judge_not_candidate_decision")
        self.assertFalse(report["gate_decisions"]["all_required_passed"])

    def test_invalid_gate_threshold_is_rejected(self) -> None:
        grade = {
            "gates": {
                "trigger_threshold": 2,
                "required_case_pass_rate": 1.0,
                "judge_required": False,
            },
            "records": [record("candidate", True)],
        }
        with self.assertRaisesRegex(SuiteError, "gate threshold"):
            build_report(grade)


if __name__ == "__main__":
    unittest.main()
