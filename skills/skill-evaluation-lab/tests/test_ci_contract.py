"""Skill Evaluation Lab 三平台静态 CI 契约测试。"""

from __future__ import annotations

import unittest

from _helpers import REPO_ROOT


class CiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = REPO_ROOT / ".github" / "workflows" / "skill-evaluation-lab.yml"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.text.lower()

    def test_runs_for_all_branches_on_three_platforms(self) -> None:
        self.assertIn('branches: ["**"]', self.text)
        self.assertIn("workflow_dispatch:", self.text)
        for platform in ("windows-latest", "ubuntu-latest", "macos-latest"):
            self.assertIn(platform, self.text)
        self.assertIn('python-version: "3.12"', self.text)

    def test_uses_read_only_permissions_and_no_secret_or_install_step(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.text)
        for forbidden in ("secrets.", "pip install", "poetry install", "npm install", "network eval"):
            self.assertNotIn(forbidden, self.lower)

    def test_runs_only_unit_inventory_and_static_workflows(self) -> None:
        self.assertIn("unittest discover", self.text)
        self.assertIn("--suite inventory", self.text)
        self.assertIn("--suite static", self.text)
        for forbidden in ("--suite offline", "--live", "--model", "--authorize", "se_run.py"):
            self.assertNotIn(forbidden, self.lower)

    def test_keeps_generated_evidence_ephemeral(self) -> None:
        self.assertIn(
            "--work-dir .ci-artifacts/skill-evaluation-lab/inventory",
            self.text,
        )
        self.assertIn(
            "--work-dir .ci-artifacts/skill-evaluation-lab/static",
            self.text,
        )
        for forbidden in (
            "actions/upload-artifact",
            "actions/download-artifact",
            "actions/cache",
            "cache:",
            "retention-days:",
        ):
            self.assertNotIn(forbidden, self.lower)


if __name__ == "__main__":
    unittest.main()
