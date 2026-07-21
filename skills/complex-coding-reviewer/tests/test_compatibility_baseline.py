from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "e996fa5"
    / "policies.json"
)
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from helpers import create_file_target, receipt_for_target, writable_tempdir  # noqa: E402
from complex_coding_reviewer.contract import validate_receipt  # noqa: E402


class ReviewerCompatibilityBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_old_external_agent_receipts_remain_accepted(self) -> None:
        self.assertEqual("e996fa5", self.fixture["baseline_commit"])
        for expected in self.fixture["accepted_receipts"]:
            with self.subTest(policy=expected["policy"]), writable_tempdir() as temp:
                root = Path(temp)
                receipt = receipt_for_target(
                    create_file_target(root),
                    root=root,
                    policy=expected["policy"],
                    delegated=True,
                )
                result = validate_receipt(
                    receipt,
                    review_root=root / "reviews",
                    workspace=root,
                    expected_dispatch_policy=expected["policy"],
                )
                self.assertEqual(expected["reviewer_mode"], result["reviewer_mode"])
                self.assertEqual(
                    expected["independence_claim"],
                    result["independence_claim"],
                )


if __name__ == "__main__":
    unittest.main()
