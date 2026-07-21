from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_execution import (  # noqa: E402
    check_preflight_status,
    check_transition_status,
)


def replayed_state(*, lifecycle: str = "in_progress") -> SimpleNamespace:
    return SimpleNamespace(
        state={
            "lifecycle": lifecycle,
            "current_stage_id": None,
            "completed_stage_ids": [],
            "remaining_stage_ids": ["STG-01"],
            "stop_condition": None,
            "next_action": "执行 STG-01。",
            "reapproval_required": False,
            "last_event_seq": 1,
        },
        stage_reviews={},
        carried_stage_ids=set(),
        final_review=None,
    )


class ExecutionEfficiencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = SimpleNamespace(
            task_id="efficiency-test",
            plan_revision=1,
            contract={
                "validations": [
                    {"id": "VAL-01", "kind": "test"},
                    {"id": "VAL-02", "kind": "build"},
                ]
            },
        )
        self.attestation = {"authorizations": {"commit": False}}

    def test_preflight_cli_context_replays_once(self) -> None:
        replayed = replayed_state()
        with (
            mock.patch(
                "harness_execution.replay_bundle",
                return_value=(replayed, self.attestation),
            ) as replay,
            mock.patch("harness_execution.evaluate_dependency_preflight"),
            mock.patch(
                "harness_execution.load_snapshot",
                return_value=replayed.state,
            ) as snapshot,
        ):
            attestation, status = check_preflight_status(self.bundle)
        replay.assert_called_once_with(self.bundle)
        snapshot.assert_called_once_with(self.bundle)
        self.assertIs(self.attestation, attestation)
        self.assertEqual({"VAL-01": 300, "VAL-02": 900}, status["validation_timeouts"])

    def test_transition_cli_context_replays_once(self) -> None:
        replayed = replayed_state()
        with (
            mock.patch(
                "harness_execution.replay_bundle",
                return_value=(replayed, self.attestation),
            ) as replay,
            mock.patch("harness_execution.evaluate_dependency_preflight"),
            mock.patch(
                "harness_execution.load_snapshot",
                return_value=replayed.state,
            ) as snapshot,
        ):
            _, status = check_transition_status(self.bundle)
        replay.assert_called_once_with(self.bundle)
        snapshot.assert_called_once_with(self.bundle)
        self.assertEqual("in_progress", status["lifecycle"])


if __name__ == "__main__":
    unittest.main()
