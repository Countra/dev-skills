"""Wilson、paired delta、provenance 与成本统计测试。"""

from __future__ import annotations

import unittest

from _helpers import SCRIPT_ROOT as _SCRIPT_ROOT
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.metrics import (
    cost_metrics,
    paired_delta_metrics,
    require_compatible_documents,
    summarize_numeric,
    trigger_metrics,
    wilson_interval,
)


def graded_record(
    pair: str,
    variant: str,
    passed: bool,
    *,
    fingerprint: str = "fp",
    duration: float | None = None,
) -> dict[str, object]:
    return {
        "case_id": pair,
        "mode": "behavior",
        "variant": variant,
        "repetition": 1,
        "pairing": {
            "pair_key": pair,
            "prompt_sha256": f"prompt-{pair}",
            "inputs": [f"{pair}.txt"],
            "model": "model",
            "sandbox": "workspace-write",
            "timeout_seconds": 30,
            "network_access": False,
            "skill_snapshot": variant if variant == "candidate" else "none",
        },
        "deterministic": {"passed": passed, "failure_type": None if passed else "requirement_failure"},
        "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2},
        "duration_seconds": duration,
        "provenance": {
            "fingerprint": fingerprint,
            "lab_tree_sha256": "a" * 64,
            "adapter": "codex-cli",
            "cli_version": "1.0",
            "model": "model",
            "sandbox": "workspace-write",
            "network_access": False,
        },
    }


class IntervalTests(unittest.TestCase):
    def test_wilson_handles_empty_and_single_samples(self) -> None:
        empty = wilson_interval(0, 0)
        failed = wilson_interval(0, 1)
        passed = wilson_interval(1, 1)
        self.assertFalse(empty["available"])
        self.assertEqual((empty["low"], empty["high"]), (None, None))
        self.assertEqual(failed["low"], 0.0)
        self.assertLess(failed["high"], 1.0)
        self.assertGreater(passed["low"], 0.0)
        self.assertEqual(passed["high"], 1.0)

    def test_small_numeric_sample_does_not_invent_variance(self) -> None:
        summary = summarize_numeric([3.0])
        self.assertEqual(summary["mean"], 3.0)
        self.assertIsNone(summary["sample_stdev"])


class PairingMetricTests(unittest.TestCase):
    def test_trigger_confusion_matrix_keeps_positive_and_negative_truth(self) -> None:
        records = [
            {
                "record_key": "positive:1:candidate",
                "case_id": "positive",
                "mode": "trigger",
                "variant": "candidate",
                "trigger": {"expected": True, "observed": True},
            },
            {
                "record_key": "near-miss:1:candidate",
                "case_id": "near-miss",
                "mode": "trigger",
                "variant": "candidate",
                "trigger": {"expected": False, "observed": True},
            },
        ]
        result = trigger_metrics(records)
        self.assertEqual(result["confusion_matrix"]["true_positive"], 1)
        self.assertEqual(result["confusion_matrix"]["false_positive"], 1)
        self.assertEqual(result["activation_rate"], 1.0)
        self.assertEqual(result["true_negative_rate"], 0.0)

    def test_paired_delta_counts_wins_and_low_information(self) -> None:
        records = [graded_record("one", "candidate", True), graded_record("one", "baseline", False)]
        result = paired_delta_metrics(records)
        self.assertEqual((result["n_pairs"], result["wins"], result["losses"]), (1, 1, 0))
        self.assertEqual(result["delta"]["mean"], 1.0)
        self.assertTrue(result["low_information"])

    def test_incompatible_provenance_is_excluded(self) -> None:
        records = [
            graded_record("one", "candidate", True, fingerprint="new"),
            graded_record("one", "baseline", False, fingerprint="old"),
        ]
        result = paired_delta_metrics(records)
        self.assertEqual(result["n_pairs"], 0)
        self.assertEqual(result["excluded_pairs"][0]["reasons"], ["provenance"])

    def test_missing_provenance_is_excluded(self) -> None:
        records = [graded_record("one", "candidate", True), graded_record("one", "baseline", False)]
        records[1]["provenance"].pop("fingerprint")
        result = paired_delta_metrics(records)
        self.assertEqual(result["n_pairs"], 0)
        self.assertEqual(result["excluded_pairs"][0]["reasons"], ["missing_provenance"])

    def test_duplicate_pair_member_is_not_overwritten(self) -> None:
        records = [
            graded_record("one", "candidate", True),
            graded_record("one", "candidate", False),
            graded_record("one", "baseline", False),
        ]
        result = paired_delta_metrics(records)
        self.assertEqual(result["n_pairs"], 0)
        self.assertEqual(result["excluded_pairs"][0]["reasons"], ["duplicate_pair_member"])

    def test_cross_fingerprint_documents_are_rejected(self) -> None:
        with self.assertRaisesRegex(SuiteError, "不同 fingerprint"):
            require_compatible_documents([{"fingerprint": "one"}, {"fingerprint": "two"}])
        with self.assertRaisesRegex(SuiteError, "缺少 fingerprint"):
            require_compatible_documents([{}])

    def test_cost_reports_tokens_and_duration_availability(self) -> None:
        records = [
            graded_record("one", "candidate", True, duration=1.5),
            graded_record("one", "baseline", False),
        ]
        result = cost_metrics(records)
        self.assertEqual(result["tokens"]["input_tokens"], 20)
        self.assertTrue(result["token_availability"]["input_tokens"]["complete"])
        self.assertFalse(result["token_availability"]["reasoning_output_tokens"]["complete"])
        self.assertEqual(result["duration_seconds"]["count"], 1)
        self.assertIsNone(result["duration_seconds"]["sample_stdev"])


if __name__ == "__main__":
    unittest.main()
