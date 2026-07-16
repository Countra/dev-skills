from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / "skills" / "complex-coding-reviewer"
EVAL_ROOT = REPO_ROOT / "evals" / "complex-coding-reviewer"


class ProfessionalWorkflowTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (SKILL_ROOT / relative).read_text(encoding="utf-8")

    def run_json(self, script: str, *arguments: str) -> tuple[int, dict[str, object]]:
        completed = subprocess.run(
            [
                sys.executable,
                "-u",
                "-X",
                "utf8",
                "-B",
                str(EVAL_ROOT / script),
                *arguments,
            ],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"评估脚本未返回 JSON：stdout={completed.stdout!r}; "
                f"stderr={completed.stderr!r}; error={exc}"
            )
        return completed.returncode, payload

    def test_skill_uses_progressive_professional_references(self) -> None:
        skill = self.read("SKILL.md")
        for reference in (
            "references/plan-review.md",
            "references/code-review.md",
            "references/review-workflow.md",
            "references/review-calibration.md",
            "references/risk-playbooks.md",
            "references/review-contract.md",
        ):
            self.assertIn(reference, skill)
        self.assertLess(len(skill.splitlines()), 120)

    def test_profiles_prioritize_spec_and_truthful_clean_review(self) -> None:
        plan = self.read("references/plan-review.md")
        code = self.read("references/code-review.md")
        self.assertIn("需求符合性", plan)
        self.assertIn("plan-mandated", plan)
        self.assertIn("Spec compliance first", code)
        for value in ("missing", "extra", "misunderstood", "cannot-verify"):
            self.assertIn(value, code)
        self.assertIn("clean review", plan.lower())
        self.assertIn("clean review", code.lower())

    def test_risk_screen_has_exactly_six_conditional_domains(self) -> None:
        risks = self.read("references/risk-playbooks.md")
        actual = set(re.findall(r"`(RISK-[A-Z0-9-]+)`", risks))
        self.assertEqual(
            {
                "RISK-SECURITY-PRIVACY",
                "RISK-CONCURRENCY-INTEGRITY",
                "RISK-PERFORMANCE-RESOURCES",
                "RISK-API-DATA-COMPATIBILITY",
                "RISK-UI-ACCESSIBILITY-I18N",
                "RISK-REMOVAL-DEPENDENCIES",
            },
            actual,
        )
        self.assertIn("不得默认全量运行", risks)

    def test_semantic_oracle_self_test_has_zero_execution(self) -> None:
        code, payload = self.run_json("run_semantic_oracle.py", "--self-test")
        self.assertEqual(0, code, payload)
        self.assertTrue(payload["passed"])
        boundaries = payload["positive"]["claim_boundaries"]
        self.assertEqual(0, boundaries["agent_calls"])
        self.assertEqual(0, boundaries["network_calls"])
        self.assertEqual(0, boundaries["target_executions"])

    def test_semantic_oracle_rejects_empty_suite(self) -> None:
        from helpers import writable_tempdir

        with writable_tempdir() as temp:
            input_path = Path(temp) / "empty.json"
            input_path.write_text(
                json.dumps(
                    {
                        "suite": "empty",
                        "provenance": {
                            "mode": "same-context",
                            "agent_calls": 0,
                            "network_calls": 0,
                            "target_executions": 0,
                        },
                        "cases": [],
                    }
                ),
                encoding="utf-8",
            )
            code, payload = self.run_json("run_semantic_oracle.py", "--input", str(input_path))
            self.assertEqual(2, code, payload)
            self.assertEqual("ORACLE_EMPTY_SUITE", payload["error"]["code"])

    def test_static_contract_mode_reports_no_semantic_claim(self) -> None:
        code, payload = self.run_json("run_evals.py", "--static-contract-only")
        self.assertEqual(0, code, payload)
        self.assertEqual(0, payload["failed"])
        self.assertFalse(payload["claim_boundaries"]["semantic_review_quality_observed"])
        self.assertEqual(0, payload["claim_boundaries"]["agent_calls"])


if __name__ == "__main__":
    unittest.main()
