"""盲化、位置交换与人工校准协议测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import SCRIPT_ROOT as _SCRIPT_ROOT
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.grading import build_blind_swap_tasks, resolve_blind_swap


class BlindJudgeProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = build_blind_swap_tasks(
            pair_id="candidate-baseline-pair",
            candidate_output={"path": "candidate/output.txt", "result": "complete"},
            baseline_output={"path": "baseline/output.txt", "result": "partial"},
            rubric="Compare candidate and baseline only against the stated requirements.",
            seed=11,
        )

    def _judgments(self, preferred: str) -> list[dict[str, object]]:
        result = []
        for task in self.bundle["public_tasks"]:
            mapping = self.bundle["private_mappings"][task["task_id"]]
            winner = next(label for label, variant in mapping.items() if variant == preferred)
            result.append(
                {
                    "task_id": task["task_id"],
                    "winner": winner,
                    "confidence": 0.9,
                    "rationale": "The requirements are satisfied more completely.",
                }
            )
        return result

    def test_public_tasks_hide_variant_identity(self) -> None:
        public = json.dumps(self.bundle["public_tasks"], ensure_ascii=False).lower()
        self.assertNotIn("candidate", public)
        self.assertNotIn("baseline", public)

    def test_consistent_swap_is_advisory_without_calibration(self) -> None:
        result = resolve_blind_swap(self._judgments("candidate"), self.bundle["private_mappings"])
        self.assertEqual((result["status"], result["authority"]), ("candidate", "advisory"))

    def test_position_conflict_is_inconclusive(self) -> None:
        judgments = self._judgments("candidate")
        second = judgments[1]
        mapping = self.bundle["private_mappings"][second["task_id"]]
        second["winner"] = next(label for label, variant in mapping.items() if variant == "baseline")
        result = resolve_blind_swap(
            judgments,
            self.bundle["private_mappings"],
            calibration={"sample_count": 20, "agreement_rate": 0.95},
        )
        self.assertEqual((result["status"], result["authority"]), ("inconclusive", "advisory"))

    def test_duplicate_task_id_fails_closed(self) -> None:
        judgments = self._judgments("candidate")
        judgments[1]["task_id"] = judgments[0]["task_id"]
        with self.assertRaisesRegex(SuiteError, "task_id 重复"):
            resolve_blind_swap(judgments, self.bundle["private_mappings"])


if __name__ == "__main__":
    unittest.main()
