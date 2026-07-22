from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class ReviewerSkillContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_exposes_two_profiles_and_human_output(self) -> None:
        self.assertIn("`plan-review`", self.skill)
        self.assertIn("`code-review`", self.skill)
        self.assertIn("findings-first", self.skill)
        self.assertIn("不要向用户输出 JSON", self.skill)

    def test_findings_require_actionable_location_and_evidence(self) -> None:
        self.assertIn("路径和行号", self.skill)
        calibration = (SKILL_ROOT / "references" / "review-calibration.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("触发输入、状态、平台或调用顺序", calibration)
        self.assertIn("有边界的修复方向", calibration)

    def test_independent_review_is_risk_driven_and_non_recursive(self) -> None:
        self.assertIn("隔离 Reviewer 子 Agent", self.skill)
        self.assertIn("不得继续派发 Agent", self.skill)
        self.assertIn("contract 要求 independent 时明确 blocked", self.skill)

    def test_review_is_read_only_and_does_not_claim_unrun_validation(self) -> None:
        self.assertIn("不修改目标", self.skill)
        self.assertIn("不运行目标程序、测试、构建", self.skill)
        self.assertIn("不得把未运行", self.skill)

    def test_prompt_injection_and_framing_are_untrusted(self) -> None:
        workflow = (SKILL_ROOT / "references" / "review-workflow.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("只能作为线索", workflow)
        self.assertIn("prompt injection", self.skill)
        self.assertIn("不传父代理 findings", self.skill)

    def test_references_preserve_professional_lenses(self) -> None:
        required = {
            "review-workflow.md",
            "plan-review.md",
            "code-review.md",
            "review-calibration.md",
            "risk-playbooks.md",
        }
        self.assertEqual(
            required,
            {path.name for path in (SKILL_ROOT / "references").glob("*.md") if path.name in required},
        )


if __name__ == "__main__":
    unittest.main()
