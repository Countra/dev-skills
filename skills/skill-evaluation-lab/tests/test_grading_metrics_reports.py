"""评分、指标与报告的集成契约测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import SCRIPT_ROOT as _SCRIPT_ROOT
from skill_evaluation_lab.grading import grade_manifest
from skill_evaluation_lab.reports import build_report, render_markdown


FINGERPRINT = "f" * 64


def _record(variant: str, *, passed: bool) -> dict[str, object]:
    failure_count = 0 if passed else 1
    return {
        "case_id": "paired-case",
        "mode": "behavior",
        "split": "validation",
        "variant": variant,
        "repetition": 1,
        "status": "PASS" if passed else "FAIL",
        "workspace": f"cases/paired-case/{variant}-1",
        "baseline_commit": "c" * 40,
        "pairing": {
            "pair_key": "paired-case:1",
            "prompt_sha256": "b" * 64,
            "inputs": ["input.txt"],
            "model": "test-model",
            "sandbox": "workspace-write",
            "timeout_seconds": 30,
            "network_access": False,
            "skill_snapshot": variant if variant == "candidate" else "none",
        },
        "expected_trigger": None,
        "observed_trigger": None,
        "runner": {
            "outcome": "passed",
            "return_code": 0,
            "final": {},
            "trace_path": None,
            "stderr_path": None,
            "duration_seconds": 0.1,
            "usage": {"input_tokens": 8, "output_tokens": 2},
            "provenance": {
                "fingerprint": FINGERPRINT,
                "lab_tree_sha256": "a" * 64,
                "adapter": "fake",
                "cli_version": "test",
                "model": "test-model",
                "sandbox": "workspace-write",
                "network_access": False,
                "prompt_sha256": "b" * 64,
                "case_id": "paired-case",
                "attempt": 1,
                "variant": variant,
            },
            "observation": {},
        },
        "assertions": {
            "status": "PASS" if passed else "FAIL",
            "counts": {"PASS": int(passed), "FAIL": failure_count, "ERROR": 0},
            "results": [
                {
                    "assertion_id": "result",
                    "type": "file_exists",
                    "status": "PASS" if passed else "FAIL",
                    "message": "fixture",
                    "evidence": {},
                }
            ],
        },
    }


class GradingMetricsReportContractTests(unittest.TestCase):
    def test_deterministic_grade_flows_into_transparent_report(self) -> None:
        grade = grade_manifest(
            {
                "suite_id": "suite",
                "run_id": "run",
                "schema_version": 1,
                "state": "completed",
                "status": "FAIL",
                "fingerprint": FINGERPRINT,
                "execution_order": "serial-paired-alternating",
                "requested_concurrency": 1,
                "effective_concurrency": 1,
                "source_identity": {
                    "candidate": {"tree_sha256": "d" * 64, "file_count": 1},
                    "baseline": "none",
                },
                "lab_identity": {"tree_sha256": "a" * 64, "file_count": 1},
                "gates": {
                    "trigger_threshold": 0.8,
                    "required_case_pass_rate": 1.0,
                    "judge_required": False,
                },
                "records": [_record("candidate", passed=True), _record("baseline", passed=False)],
                "budget": {"agent_runs": 2, "judge_runs": 0, "remaining_seconds": 60.0},
            }
        )
        report = build_report(grade)
        markdown = render_markdown(report)

        self.assertEqual(report["quality"]["candidate"]["passed"], 1)
        self.assertEqual(report["quality"]["candidate"]["by_mode"]["behavior"]["n"], 1)
        self.assertEqual(report["paired_delta"]["wins"], 1)
        self.assertEqual(report["failure_taxonomy"], {"requirement_failure": 1})
        self.assertTrue(report["gate_decisions"]["all_required_passed"])
        self.assertEqual(report["gate_decisions"]["required_gate_count"], 1)
        self.assertTrue(report["uncertainty"]["small_sample"])
        self.assertNotIn("overall_score", json.dumps(report, sort_keys=True))
        self.assertIn("Wilson 95% interval", markdown)
        self.assertIn("Quality By Mode", markdown)
        self.assertIn("Gate Decisions", markdown)


if __name__ == "__main__":
    unittest.main()
