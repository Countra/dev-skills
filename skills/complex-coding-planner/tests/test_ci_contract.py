"""Planner/Executor 三平台 CI 契约测试。"""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class CiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = REPO_ROOT / ".github" / "workflows" / "planner-executor.yml"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()

    def test_runs_for_push_and_pull_request_on_all_branches(self) -> None:
        self.assertIn("  push:\n", self.text)
        self.assertIn("  pull_request:\n", self.text)
        self.assertIn("  workflow_dispatch:\n", self.text)
        branch_lines = [
            line.strip()
            for line in self.text.splitlines()
            if line.strip().startswith("branches:")
        ]
        self.assertEqual(['branches: ["**"]', 'branches: ["**"]'], branch_lines)

    def test_uses_three_platforms_and_python_312(self) -> None:
        for platform in ("windows-latest", "ubuntu-latest", "macos-latest"):
            self.assertIn(platform, self.text)
        self.assertIn('python-version: "3.12"', self.text)
        self.assertIn("fail-fast: false", self.text)

    def test_runs_four_required_offline_commands(self) -> None:
        required = (
            "unittest discover -s skills/complex-coding-planner/tests",
            "evals/complex-coding-planner/run_evals.py --output",
            "unittest discover -s skills/complex-coding-executor/tests",
            "evals/complex-coding-executor/run_evals.py --output",
        )
        for command in required:
            self.assertEqual(1, self.text.count(command), command)
        for forbidden in ("secrets.", "pip install", "codex exec", "npm install"):
            self.assertNotIn(forbidden, self.lower)

    def test_permissions_and_evidence_are_bounded(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertIn("planner-evals.json", self.text)
        self.assertIn("executor-evals.json", self.text)
        self.assertIn("if-no-files-found: error", self.text)


if __name__ == "__main__":
    unittest.main()
