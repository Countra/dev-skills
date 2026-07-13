"""Runner 请求门禁和 fake adapter 测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from _helpers import temporary_workspace
from skill_evaluation_lab.budgets import RunBudget
from skill_evaluation_lab.errors import AuthorizationError, InconclusiveError, SuiteError
from skill_evaluation_lab.runners import FakeRunner, RunRequest, validate_live_request


def request(root: Path, **overrides: object) -> RunRequest:
    values = {
        "run_id": "run-1",
        "case_id": "case-1",
        "attempt": 1,
        "prompt": "Evaluate this task.",
        "workspace": root,
        "artifact_dir": root / "artifact",
        "model": "fake",
        "sandbox": "read-only",
        "timeout_seconds": 30,
        "fingerprint": "a" * 64,
        "lab_tree_sha256": "b" * 64,
        "approved_fingerprint": "a" * 64,
        "live_authorized": True,
    }
    values.update(overrides)
    return RunRequest(**values)


class RunnerGuardTests(unittest.TestCase):
    def test_rejects_missing_live_authorization(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(AuthorizationError, "显式授权"):
                validate_live_request(request(root, live_authorized=False))

    def test_rejects_fingerprint_drift(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(AuthorizationError, "fingerprint"):
                validate_live_request(request(root, approved_fingerprint="b" * 64))

    def test_rejects_unknown_previous_outcome(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(InconclusiveError, "禁止隐式重试"):
                validate_live_request(request(root, previous_outcome="unknown"))

    def test_rejects_network_and_dangerous_sandbox(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaises(SuiteError):
                validate_live_request(request(root, network_access=True))
            with self.assertRaises(SuiteError):
                validate_live_request(request(root, sandbox="danger-full-access"))

    def test_fake_runner_consumes_one_budget_slot(self) -> None:
        with temporary_workspace() as root:
            budget = RunBudget(1, 1, 60)
            result = FakeRunner({"case-1": {"final": {"ok": True}}}).run(request(root), budget)
            self.assertEqual(result.outcome, "passed")
            self.assertEqual(result.final, {"ok": True})
            self.assertEqual(budget.agent_runs, 1)
            self.assertEqual(result.provenance["fingerprint"], "a" * 64)
            self.assertEqual(result.provenance["lab_tree_sha256"], "b" * 64)
            self.assertEqual(result.provenance["sandbox"], "read-only")
            self.assertFalse(result.provenance["network_access"])
            self.assertEqual(result.provenance["variant"], "candidate")
            self.assertIsNotNone(result.duration_seconds)
            self.assertGreaterEqual(result.duration_seconds, 0)


if __name__ == "__main__":
    unittest.main()
