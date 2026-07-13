"""确定性 grading、人工反馈与 blind judge 测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import SCRIPT_ROOT as _SCRIPT_ROOT
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.grading import build_blind_swap_tasks, grade_manifest, resolve_blind_swap


GATES = {"trigger_threshold": 0.8, "required_case_pass_rate": 1.0, "judge_required": False}
LAB_IDENTITY = {"tree_sha256": "a" * 64, "file_count": 1}
FINGERPRINT = "f" * 64


def raw_record(variant: str, *, errors: int = 0, failures: int = 0) -> dict[str, object]:
    passed = errors == 0 and failures == 0
    def result(status: str, suffix: str) -> dict[str, object]:
        return {
            "assertion_id": f"assertion-{suffix}",
            "type": "file_exists",
            "status": status,
            "message": "fixture",
            "evidence": {},
        }

    results = [result("PASS", "pass")]
    results.extend(result("FAIL", f"fail-{index}") for index in range(failures))
    results.extend(result("ERROR", f"error-{index}") for index in range(errors))
    return {
        "case_id": "behavior-case",
        "mode": "behavior",
        "split": "validation",
        "variant": variant,
        "repetition": 1,
        "status": "PASS" if passed else "FAIL",
        "workspace": f"cases/behavior-case/{variant}-1",
        "baseline_commit": "c" * 40,
        "pairing": {
            "pair_key": "behavior-case:1",
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
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "provenance": {
                "fingerprint": FINGERPRINT,
                "lab_tree_sha256": LAB_IDENTITY["tree_sha256"],
                "adapter": "fake",
                "cli_version": "fake",
                "model": "test-model",
                "sandbox": "workspace-write",
                "network_access": False,
                "prompt_sha256": "b" * 64,
                "case_id": "behavior-case",
                "attempt": 1,
                "variant": variant,
                **({"skill_tree_sha256": "d" * 64} if variant == "candidate" else {}),
            },
            "observation": {},
        },
        "assertions": {
            "status": "ERROR" if errors else "PASS" if passed else "FAIL",
            "counts": {"PASS": 1, "FAIL": failures, "ERROR": errors},
            "results": results,
        },
    }


def run_manifest(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "state": "completed",
        "status": "PASS" if all(record["status"] == "PASS" for record in records) else "FAIL",
        "suite_id": "suite",
        "fingerprint": FINGERPRINT,
        "run_id": "run",
        "execution_order": "serial-paired-alternating",
        "requested_concurrency": 1,
        "effective_concurrency": 1,
        "gates": GATES,
        "lab_identity": LAB_IDENTITY,
        "source_identity": {
            "candidate": {"tree_sha256": "d" * 64, "file_count": 1},
            "baseline": "none",
        },
        "records": records,
        "budget": {"agent_runs": len(records), "judge_runs": 0, "remaining_seconds": 60.0},
    }


class DeterministicGradingTests(unittest.TestCase):
    def test_grade_keeps_deterministic_and_human_results_separate(self) -> None:
        manifest = run_manifest([raw_record("candidate"), raw_record("baseline", errors=1)])
        grade = grade_manifest(
            manifest,
            human_feedback=[
                {
                    "record_key": "behavior-case:1:candidate",
                    "label": "pass",
                    "notes": "calibration sample",
                }
            ],
        )

        self.assertTrue(grade["records"][0]["deterministic"]["passed"])
        self.assertEqual((grade["run_state"], grade["run_status"]), ("completed", "FAIL"))
        self.assertIsNone(grade["run_error"])
        self.assertEqual(grade["records"][0]["human_feedback"]["label"], "pass")
        self.assertEqual(grade["records"][1]["deterministic"]["failure_type"], "assertion_error")
        self.assertIsNone(grade["records"][1]["human_feedback"])

    def test_unknown_human_record_is_rejected(self) -> None:
        manifest = run_manifest([raw_record("candidate"), raw_record("baseline")])
        with self.assertRaisesRegex(SuiteError, "未知 record"):
            grade_manifest(
                manifest,
                human_feedback=[{"record_key": "missing:1:x", "label": "fail", "notes": "not found"}],
            )

    def test_duplicate_run_record_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(SuiteError, "record key 重复"):
            grade_manifest(
                run_manifest(
                    [raw_record("candidate"), raw_record("candidate"), raw_record("baseline")]
                )
            )

    def test_missing_fingerprint_is_rejected(self) -> None:
        manifest = run_manifest([raw_record("candidate")])
        manifest.pop("fingerprint")
        with self.assertRaisesRegex(SuiteError, "fingerprint"):
            grade_manifest(manifest)

    def test_record_fingerprint_mismatch_is_rejected(self) -> None:
        record = raw_record("candidate")
        record["runner"]["provenance"]["fingerprint"] = "e" * 64
        with self.assertRaisesRegex(SuiteError, "fingerprint"):
            grade_manifest(run_manifest([record]))

    def test_missing_gate_contract_is_rejected(self) -> None:
        manifest = run_manifest([raw_record("candidate")])
        manifest.pop("gates")
        with self.assertRaisesRegex(SuiteError, "gates"):
            grade_manifest(manifest)

    def test_record_lab_identity_mismatch_is_rejected(self) -> None:
        record = raw_record("candidate")
        record["runner"]["provenance"]["lab_tree_sha256"] = "b" * 64
        with self.assertRaisesRegex(SuiteError, "lab identity"):
            grade_manifest(run_manifest([record]))

    def test_trigger_status_cannot_override_observation_truth(self) -> None:
        record = raw_record("candidate")
        record.update(
            {
                "case_id": "trigger-case",
                "mode": "trigger",
                "status": "PASS",
                "expected_trigger": False,
                "observed_trigger": True,
                "assertions": None,
            }
        )
        record["workspace"] = "cases/trigger-case/candidate-1"
        record["pairing"].update(
            {"pair_key": "trigger-case:1", "sandbox": "read-only", "skill_snapshot": "none"}
        )
        record["runner"]["provenance"].update(
            {"case_id": "trigger-case", "sandbox": "read-only"}
        )
        record["runner"]["observation"] = {"activation_receipt_exact": True}
        grade = grade_manifest(
            run_manifest([record])
        )
        self.assertFalse(grade["records"][0]["deterministic"]["passed"])
        self.assertEqual(grade["records"][0]["deterministic"]["failure_type"], "trigger_mismatch")

    def test_grade_rejects_judge_authority_inconsistent_with_calibration(self) -> None:
        manifest = run_manifest([raw_record("candidate"), raw_record("baseline")])
        with self.assertRaisesRegex(SuiteError, "swap/calibration"):
            grade_manifest(
                manifest,
                judge_result={
                    "status": "candidate",
                    "authority": "advisory",
                    "calibrated": True,
                    "translated_winners": ["candidate", "candidate"],
                    "mean_confidence": 0.9,
                },
            )


class BlindJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = build_blind_swap_tasks(
            pair_id="candidate-vs-baseline",
            candidate_output={"candidate_path": "runs/candidate-1/out.txt", "value": "better"},
            baseline_output={"baseline_path": "runs/baseline-1/out.txt", "value": "worse"},
            rubric="Prefer the candidate only when evidence beats baseline.",
            seed=7,
        )

    def _judgments_for(self, variant: str) -> list[dict[str, object]]:
        judgments = []
        for task in self.bundle["public_tasks"]:
            mapping = self.bundle["private_mappings"][task["task_id"]]
            winner = next(label for label, mapped in mapping.items() if mapped == variant)
            judgments.append(
                {"task_id": task["task_id"], "winner": winner, "confidence": 0.8, "rationale": "rubric evidence"}
            )
        return judgments

    def test_public_tasks_are_deidentified_and_mapping_is_private(self) -> None:
        public_text = json.dumps(self.bundle["public_tasks"], ensure_ascii=False).lower()
        self.assertNotIn("candidate", public_text)
        self.assertNotIn("baseline", public_text)
        self.assertIn("candidate", json.dumps(self.bundle["private_mappings"]))

    def test_deidentification_collision_fails_closed(self) -> None:
        with self.assertRaisesRegex(SuiteError, "字段冲突"):
            build_blind_swap_tasks(
                pair_id="pair",
                candidate_output={"candidate_path": "a", "baseline_path": "b"},
                baseline_output={},
                rubric="quality",
                seed=1,
            )

    def test_consistent_swap_is_advisory_until_calibrated(self) -> None:
        judgments = self._judgments_for("candidate")
        advisory = resolve_blind_swap(judgments, self.bundle["private_mappings"])
        calibrated = resolve_blind_swap(
            judgments,
            self.bundle["private_mappings"],
            calibration={"sample_count": 5, "agreement_rate": 0.8},
        )
        self.assertEqual((advisory["status"], advisory["authority"]), ("candidate", "advisory"))
        self.assertEqual((calibrated["status"], calibrated["authority"]), ("candidate", "decision"))

    def test_swap_conflict_is_inconclusive_even_when_calibrated(self) -> None:
        judgments = self._judgments_for("candidate")
        second = judgments[1]
        mapping = self.bundle["private_mappings"][second["task_id"]]
        second["winner"] = next(label for label, mapped in mapping.items() if mapped == "baseline")
        result = resolve_blind_swap(
            judgments,
            self.bundle["private_mappings"],
            calibration={"sample_count": 20, "agreement_rate": 0.95},
        )
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["authority"], "advisory")

    def test_invalid_calibration_is_not_silently_downgraded(self) -> None:
        with self.assertRaisesRegex(SuiteError, "agreement_rate"):
            resolve_blind_swap(
                self._judgments_for("candidate"),
                self.bundle["private_mappings"],
                calibration={"sample_count": 5, "agreement_rate": 2},
            )

    def test_duplicate_judgment_task_id_is_rejected(self) -> None:
        judgments = self._judgments_for("candidate")
        judgments[1]["task_id"] = judgments[0]["task_id"]
        with self.assertRaisesRegex(SuiteError, "task_id 重复"):
            resolve_blind_swap(judgments, self.bundle["private_mappings"])


if __name__ == "__main__":
    unittest.main()
