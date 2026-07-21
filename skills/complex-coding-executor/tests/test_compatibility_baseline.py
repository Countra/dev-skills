from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "e996fa5"
    / "runtime-replay.json"
)
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_state import replay_events  # noqa: E402
from harness_attestation import validate_attestation  # noqa: E402
from harness_task_bundle import resolve_task_bundle  # noqa: E402
from harness_validation_schema import validate_validation_record  # noqa: E402


class CompatibilityBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_is_anchored_to_compatibility_commit(self) -> None:
        self.assertEqual("e996fa5", self.fixture["baseline"]["commit"])
        self.assertEqual(113, self.fixture["baseline"]["skill_file_count"])
        self.assertEqual(25180, self.fixture["baseline"]["skill_line_count"])

    def test_legacy_validation_payload_remains_valid(self) -> None:
        payload = self.fixture["events"][2]["payload"]
        self.assertNotIn("duration_ms", payload)
        self.assertNotIn("termination", payload)
        self.assertNotIn("cleanup_verified", payload)
        result = validate_validation_record(payload, attempt=1)
        self.assertEqual("passed", result["result"])

    def test_legacy_attestation_validates_without_rewrite(self) -> None:
        fixture_root = FIXTURE_PATH.parent
        bundle = resolve_task_bundle(fixture_root, "task-bundle")
        before = bundle.attestation_path.read_bytes()
        attestation = validate_attestation(bundle)
        self.assertEqual("compat-e996fa5", attestation["task_id"])
        self.assertEqual(before, bundle.attestation_path.read_bytes())

    def test_legacy_ledger_replays_to_golden_state(self) -> None:
        result = replay_events(
            self.fixture["contract"],
            self.fixture["events"],
        )
        self.assertEqual(self.fixture["expected_state"], result.state)
        self.assertEqual(
            "external-agent",
            result.stage_reviews["STG-01"]["reviewer_mode"],
        )
        self.assertTrue(result.stage_reviews["STG-01"]["independence_claim"])
        self.assertEqual(
            "REV-CODE-COMPAT-FINAL-001",
            result.final_review["review_id"],
        )

    def test_legacy_amendment_requests_reapproval(self) -> None:
        result = replay_events(
            self.fixture["contract"],
            self.fixture["amendment_events"],
        )
        self.assertEqual("blocked", result.state["lifecycle"])
        self.assertTrue(result.state["reapproval_required"])
        self.assertEqual(
            "公共范围发生变化。",
            result.state["stop_condition"],
        )


if __name__ == "__main__":
    unittest.main()
