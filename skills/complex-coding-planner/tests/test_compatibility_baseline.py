from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "e996fa5"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_plan_check import validate_plan  # noqa: E402


class PlannerCompatibilityBaselineTest(unittest.TestCase):
    def test_legacy_twenty_five_section_plan_remains_valid(self) -> None:
        contract = json.loads(
            (FIXTURE_DIR / "legacy-plan-contract.json").read_text(encoding="utf-8")
        )
        issues = validate_plan(FIXTURE_DIR, contract, "draft")
        errors = [issue for issue in issues if issue.level == "error"]
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
