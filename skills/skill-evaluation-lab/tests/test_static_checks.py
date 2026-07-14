"""静态检查、能力信号和 baseline delta 测试。"""

from __future__ import annotations

import unittest

from _helpers import temporary_workspace, write_skill
from skill_evaluation_lab.errors import SkillError
from skill_evaluation_lab.static_checks import evaluate_skill


def by_id(evidence: dict[str, object], check_id: str) -> dict[str, object]:
    checks = evidence["checks"]
    assert isinstance(checks, list)
    return next(item for item in checks if isinstance(item, dict) and item["id"] == check_id)


class StaticCheckTests(unittest.TestCase):
    def test_valid_skill_produces_source_bound_static_evidence(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            evidence = evaluate_skill(workspace, source, evaluation_id="valid-evaluation")
            self.assertEqual(evidence["evaluation_id"], "valid-evaluation")
            self.assertEqual(evidence["checker"]["agent_calls"], 0)
            self.assertEqual(evidence["checker"]["network_calls"], 0)
            self.assertEqual(by_id(evidence, "skill.metadata")["status"], "pass")
            self.assertEqual(by_id(evidence, "skill.syntax")["status"], "pass")
            self.assertEqual(by_id(evidence, "skill.validation_assets")["status"], "pass")
            self.assertEqual(by_id(evidence, "skill.baseline_delta")["status"], "not_applicable")

    def test_invalid_metadata_reference_and_syntax_are_failures(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            (source / "SKILL.md").write_text(
                "---\nname: Wrong_Name\ndescription:\n---\n\n[缺失](references/missing.md)\n",
                encoding="utf-8",
            )
            (source / "scripts" / "check.py").write_text("def broken(:\n", encoding="utf-8")
            evidence = evaluate_skill(workspace, source)
            self.assertEqual(by_id(evidence, "skill.metadata")["status"], "fail")
            self.assertEqual(by_id(evidence, "skill.references")["status"], "fail")
            self.assertEqual(by_id(evidence, "skill.syntax")["status"], "fail")

    def test_capabilities_are_reported_as_signals_without_execution_claim(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            marker = workspace / "must-not-exist.txt"
            (source / "scripts" / "check.py").write_text(
                "import os\nimport socket\nimport subprocess\nfrom pathlib import Path\n\n"
                f"Path({str(marker)!r}).write_text('executed')\n"
                "token = os.getenv('TOKEN')\nsubprocess.run(['tool'])\n",
                encoding="utf-8",
            )
            evidence = evaluate_skill(workspace, source)
            kinds = {item["kind"] for item in evidence["capabilities"]}
            self.assertTrue({"process", "network", "environment_read", "file_write"} <= kinds)
            capability_check = by_id(evidence, "skill.capabilities")
            self.assertEqual(capability_check["status"], "warn")
            self.assertIn("静态", capability_check["guidance"])
            self.assertFalse(marker.exists())

    def test_baseline_delta_reports_files_checks_and_capabilities(self) -> None:
        with temporary_workspace() as workspace:
            candidate = write_skill(workspace, "candidate-skill")
            baseline = write_skill(workspace, "baseline-skill")
            (candidate / "assets").mkdir()
            (candidate / "assets" / "example.txt").write_text("candidate", encoding="utf-8")
            (baseline / "SKILL.md").write_text(
                "---\nname: bad-name\ndescription:\n---\n\n# Baseline\n",
                encoding="utf-8",
            )
            evidence = evaluate_skill(workspace, candidate, baseline=baseline)
            self.assertEqual(by_id(evidence, "skill.baseline_delta")["status"], "pass")
            self.assertIn("assets/example.txt", evidence["delta"]["added_files"])
            changed = {item["id"] for item in evidence["delta"]["check_status_changes"]}
            self.assertIn("skill.metadata", changed)

    def test_rejects_identical_candidate_and_baseline(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            with self.assertRaisesRegex(SkillError, "同一目录"):
                evaluate_skill(workspace, source, baseline=source)


if __name__ == "__main__":
    unittest.main()
