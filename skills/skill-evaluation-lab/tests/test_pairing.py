"""Candidate/baseline 成对工作区与 oracle 隔离测试。"""

from __future__ import annotations

import unittest

from _helpers import temporary_workspace
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.isolation import create_case_workspace, create_run_layout
from skill_evaluation_lab.snapshots import build_tree_manifest


class PairingIsolationTests(unittest.TestCase):
    def test_pair_differs_only_by_agent_visible_skill(self) -> None:
        with temporary_workspace() as root:
            suite_root = root / "suite"
            inputs = suite_root / "inputs"
            inputs.mkdir(parents=True)
            (inputs / "checklist.txt").write_text("tests: pass\n", encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "SKILL.md").write_text(
                "---\nname: paired-skill\ndescription: Evaluate a checklist.\n---\n\n# Paired Skill\n",
                encoding="utf-8",
            )
            source_manifest = build_tree_manifest(candidate)
            layout = create_run_layout(root / "runs", "pair-suite", "a" * 64)

            candidate_case = create_case_workspace(
                layout,
                case_id="paired-case",
                variant="candidate",
                repetition=1,
                suite_root=suite_root,
                inputs=["inputs/checklist.txt"],
                agent_skill=candidate,
                agent_skill_name="paired-skill",
            )
            baseline_case = create_case_workspace(
                layout,
                case_id="paired-case",
                variant="baseline",
                repetition=1,
                suite_root=suite_root,
                inputs=["inputs/checklist.txt"],
            )

            self.assertEqual(
                (candidate_case.root / "inputs" / "checklist.txt").read_bytes(),
                (baseline_case.root / "inputs" / "checklist.txt").read_bytes(),
            )
            self.assertTrue(candidate_case.agent_skill)
            self.assertTrue((candidate_case.root / ".agents" / "skills" / "paired-skill" / "SKILL.md").is_file())
            self.assertFalse((baseline_case.root / ".agents").exists())
            self.assertEqual(build_tree_manifest(candidate), source_manifest)

    def test_oracle_is_unlisted_and_rejected_when_declared_as_input(self) -> None:
        with temporary_workspace() as root:
            suite_root = root / "suite"
            (suite_root / "inputs").mkdir(parents=True)
            (suite_root / "inputs" / "request.txt").write_text("request\n", encoding="utf-8")
            (suite_root / "oracle").mkdir()
            (suite_root / "oracle" / "expected.json").write_text("{}\n", encoding="utf-8")
            layout = create_run_layout(root / "runs", "oracle-suite", "b" * 64)

            clean_case = create_case_workspace(
                layout,
                case_id="clean-case",
                variant="baseline",
                repetition=1,
                suite_root=suite_root,
                inputs=["inputs/request.txt"],
            )
            self.assertFalse((clean_case.root / "oracle").exists())

            with self.assertRaisesRegex(SuiteError, "grader-only"):
                create_case_workspace(
                    layout,
                    case_id="leaky-case",
                    variant="candidate",
                    repetition=1,
                    suite_root=suite_root,
                    inputs=["oracle/expected.json"],
                )


if __name__ == "__main__":
    unittest.main()
