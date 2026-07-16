"""Planner、Reviewer、Executor 三平台 CI 契约测试。"""

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

    def test_runs_all_required_offline_commands(self) -> None:
        required = (
            "unittest discover -s skills/complex-coding-planner/tests",
            "evals/complex-coding-planner/run_evals.py --output",
            "unittest discover -s skills/complex-coding-reviewer/tests",
            "evals/complex-coding-reviewer/run_evals.py --output",
            "evals/complex-coding-reviewer/run_semantic_oracle.py --self-test",
            "evals/complex-coding-reviewer/run_evals.py --static-contract-only",
            "evals/complex-coding-reviewer/run_observation_packet.py --validate-only",
            "skills/skill-evaluation-lab/scripts/se_check.py",
            "unittest discover -s skills/complex-coding-executor/tests",
            "evals/complex-coding-executor/run_evals.py --output",
            "evals/complex-coding-executor/cross_skill_regression.py --include-reviewer",
        )
        for command in required:
            self.assertEqual(1, self.text.count(command), command)
        for forbidden in (
            "secrets.",
            "pip install",
            "codex exec",
            "npm install",
            "run_semantic_oracle.py --input",
            "--prepare-dir",
            "continue-on-error: true",
        ):
            self.assertNotIn(forbidden, self.lower)

    def test_permissions_and_evidence_are_bounded(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.text)
        self.assertIn("planner-evals.json", self.text)
        self.assertIn("reviewer-evals.json", self.text)
        self.assertIn("reviewer-oracle-self-test.json", self.text)
        self.assertIn("reviewer-static-contract.json", self.text)
        self.assertIn("observation-packet-validation.json", self.text)
        self.assertIn("reviewer-static.json", self.text)
        self.assertIn("executor-evals.json", self.text)
        self.assertIn("cross-review.json", self.text)
        self.assertIn("planner-reviewer-executor-evidence", self.text)
        self.assertIn("if-no-files-found: error", self.text)

    def test_installer_auto_discovers_reviewer(self) -> None:
        installer = (REPO_ROOT / "skill.sh").read_text(encoding="utf-8")
        reviewer = REPO_ROOT / "skills" / "complex-coding-reviewer"
        self.assertIn("for src_dir in skills/*; do", installer)
        self.assertIn('if [ ! -f "$src_dir/SKILL.md" ]; then', installer)
        self.assertTrue((reviewer / "SKILL.md").is_file())
        self.assertTrue((reviewer / "agents" / "openai.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
