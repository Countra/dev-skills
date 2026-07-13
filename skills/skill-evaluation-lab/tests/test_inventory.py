"""仓库 inventory 的文件与 CI coverage 测试。"""

from __future__ import annotations

import unittest

from _helpers import temporary_workspace
from skill_evaluation_lab.inventory import scan_repository


class InventoryTests(unittest.TestCase):
    def test_counts_only_eval_files_and_reads_yaml_workflows(self) -> None:
        with temporary_workspace() as root:
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Sample.\n---\n\n# Sample\n",
                encoding="utf-8",
            )
            fixture = root / "evals" / "sample-skill" / "fixtures" / "case.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("{}\n", encoding="utf-8")
            workflow = root / ".github" / "workflows" / "sample.yaml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: sample-skill\n", encoding="utf-8")

            inventory = scan_repository(root)

        self.assertEqual(inventory["skill_count"], 1)
        self.assertEqual(inventory["skills"][0]["eval_file_count"], 1)
        self.assertTrue(inventory["skills"][0]["ci_referenced"])


if __name__ == "__main__":
    unittest.main()
