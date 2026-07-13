"""运行预算和实验 fingerprint 测试。"""

from __future__ import annotations

import unittest
from unittest import mock

from _helpers import temporary_workspace, valid_suite, write_json
from skill_evaluation_lab.budgets import RunBudget, build_experiment_plan
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.errors import SuiteError


class BudgetTests(unittest.TestCase):
    def test_agent_and_judge_limits_fail_closed(self) -> None:
        budget = RunBudget(1, 1, 60)
        budget.reserve_agent()
        budget.reserve_judge()
        with self.assertRaisesRegex(SuiteError, "agent run"):
            budget.reserve_agent()
        with self.assertRaisesRegex(SuiteError, "judge run"):
            budget.reserve_judge()

    def test_wall_clock_limit_fails_closed(self) -> None:
        now = [100.0]
        budget = RunBudget(1, 1, 5, clock=lambda: now[0])
        now[0] = 106.0
        with self.assertRaisesRegex(SuiteError, "墙钟"):
            budget.reserve_agent()

    def test_nested_skill_change_updates_fingerprint(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            nested = root / "candidate" / "scripts" / "worker.py"
            nested.parent.mkdir()
            nested.write_text("VALUE = 1\n", encoding="utf-8")
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            before = build_experiment_plan(load_suite(suite_path))["fingerprint"]
            nested.write_text("VALUE = 2\n", encoding="utf-8")
            after = build_experiment_plan(load_suite(suite_path))["fingerprint"]
            self.assertNotEqual(before, after)

    def test_material_matrix_change_updates_fingerprint(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            before = build_experiment_plan(load_suite(suite_path))["fingerprint"]
            value["cases"][0]["prompt"] = "A materially different prompt."
            write_json(suite_path, value)
            after = build_experiment_plan(load_suite(suite_path))["fingerprint"]
            self.assertNotEqual(before, after)

    def test_lab_implementation_change_updates_fingerprint(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            identities = [
                {"path": "lab", "tree_sha256": "a" * 64, "file_count": 1},
                {"path": "lab", "tree_sha256": "b" * 64, "file_count": 1},
            ]
            fingerprints = []
            for identity in identities:
                with mock.patch(
                    "skill_evaluation_lab.budgets.implementation_identity",
                    return_value=identity,
                ):
                    fingerprints.append(build_experiment_plan(load_suite(suite_path))["fingerprint"])
            self.assertNotEqual(fingerprints[0], fingerprints[1])

    def test_behavior_pair_order_alternates_by_repetition(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][1]["repetitions"] = 2
            value["budgets"]["max_agent_runs"] = 5
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            plan = build_experiment_plan(load_suite(suite_path))
            behavior = [entry for entry in plan["matrix"] if entry["mode"] == "behavior"]
            self.assertEqual(
                [entry["variant"] for entry in behavior],
                ["candidate", "baseline", "baseline", "candidate"],
            )
            self.assertEqual(plan["execution_order"], "serial-paired-alternating")
            self.assertEqual(plan["effective_concurrency"], 1)


if __name__ == "__main__":
    unittest.main()
