"""只读 inventory 的 metadata 与 coverage 测试。"""

from __future__ import annotations

import unittest

from _helpers import REPO_ROOT, temporary_workspace, write_skill
from skill_evaluation_lab.inventory import scan_repository


EXPECTED_PUBLIC_SCRIPTS = [
    "se_check.py",
    "se_import.py",
    "se_inventory.py",
    "se_prepare.py",
    "se_report.py",
    "se_validate.py",
]


class InventoryTests(unittest.TestCase):
    def test_scans_temporary_repository_without_importing_skill_code(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            marker = workspace / "import-marker.txt"
            (source / "scripts" / "check.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n",
                encoding="utf-8",
            )
            inventory = scan_repository(workspace)
            self.assertEqual(inventory["skill_count"], 1)
            self.assertEqual(inventory["valid_skill_count"], 1)
            self.assertEqual(inventory["checker"]["agent_calls"], 0)
            self.assertEqual(inventory["checker"]["network_calls"], 0)
            self.assertFalse(marker.exists())

    def test_current_lab_exposes_exact_current_cli_and_validation_assets(self) -> None:
        inventory = scan_repository(REPO_ROOT)
        lab = next(item for item in inventory["skills"] if item["name"] == "skill-evaluation-lab")
        self.assertTrue(lab["valid"], lab["issues"])
        self.assertEqual(lab["public_scripts"], EXPECTED_PUBLIC_SCRIPTS)
        self.assertTrue(lab["test_files"])
        self.assertTrue(lab["has_eval_dir"])
        self.assertTrue(lab["ci_referenced"])


if __name__ == "__main__":
    unittest.main()
