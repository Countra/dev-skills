"""三平台离线 CI 的静态安全契约测试。"""

from __future__ import annotations

import unittest

from _helpers import REPO_ROOT


class CiContractTests(unittest.TestCase):
    def test_workflow_covers_three_platforms_without_live_calls(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "skill-evaluation-lab.yml").read_text(
            encoding="utf-8"
        )
        for runner in ("windows-latest", "ubuntu-latest", "macos-latest"):
            self.assertIn(runner, workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("--suite inventory", workflow)
        self.assertIn("--suite offline", workflow)
        self.assertNotIn("--authorize-live", workflow)
        self.assertNotIn("se_doctor.py --live", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
