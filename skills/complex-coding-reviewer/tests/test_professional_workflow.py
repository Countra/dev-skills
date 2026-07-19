from __future__ import annotations

import hashlib
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

    def test_agent_wait_is_bounded_observable_and_does_not_reset_budget(self) -> None:
        dispatch = self.read("references/review-dispatch.md")
        troubleshooting = self.read("references/troubleshooting.md")
        self.assertIn("单次 `wait_agent` 不超过 60 秒", dispatch)
        self.assertIn("轮询不重置总等待预算", dispatch)
        self.assertIn("`not_found`", troubleshooting)
        self.assertIn("REVIEW_DISPATCH_AGENT_UNCLOSED", troubleshooting)

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
                            "declared_by": "current-executor",
                            "independence_claim": False,
                            "agent_calls": 0,
                            "network_calls": 0,
                            "target_executions": 0,
                            "reviewer_receipts": [],
                        },
                        "cases": [],
                    }
                ),
                encoding="utf-8",
            )
            code, payload = self.run_json("run_semantic_oracle.py", "--input", str(input_path))
            self.assertEqual(2, code, payload)
            self.assertEqual("ORACLE_EMPTY_SUITE", payload["error"]["code"])

    def test_semantic_oracle_rejects_stale_observed_receipt(self) -> None:
        from helpers import writable_tempdir

        with writable_tempdir() as temp:
            workspace = Path(temp)
            receipt_path = workspace / "receipt.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "review_id": "REV-ORACLE-TEST",
                        "profile": "code-review",
                        "reviewer": {
                            "mode": "same-context",
                            "independence_claim": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            payload = {
                "suite": "stale-receipt",
                "provenance": {
                    "mode": "same-context",
                    "declared_by": "current-executor",
                    "independence_claim": False,
                    "agent_calls": 0,
                    "network_calls": 0,
                    "target_executions": 0,
                    "reviewer_receipts": [
                        {
                            "profile": "code-review",
                            "review_id": "REV-ORACLE-TEST",
                            "path": "receipt.json",
                            "sha256": digest,
                        }
                    ],
                },
                "cases": [
                    {
                        "id": "case-one",
                        "profile": "code-review",
                        "category": "known-defect",
                        "expected_findings": [
                            {
                                "id": "EXP-01",
                                "severity": "major",
                                "locator_required": True,
                                "evidence_required": True,
                            }
                        ],
                        "forbidden_finding_ids": [],
                        "expected_gap_ids": [],
                        "actual": {
                            "matched_findings": [
                                {
                                    "expectation_id": "EXP-01",
                                    "severity": "major",
                                    "locator_present": True,
                                    "evidence_refs": ["receipt.json#FIND-001"],
                                }
                            ],
                            "unmatched_finding_ids": [],
                            "triggered_forbidden_ids": [],
                            "gap_ids": [],
                        },
                    }
                ],
            }
            input_path = workspace / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            receipt_path.write_text("{}", encoding="utf-8")
            code, result = self.run_json(
                "run_semantic_oracle.py",
                "--input",
                str(input_path),
                "--workspace",
                str(workspace),
            )
            self.assertEqual(2, code, result)
            self.assertEqual("ORACLE_RECEIPT_STALE", result["error"]["code"])

    def test_semantic_oracle_returns_closed_error_for_wrong_enum_type(self) -> None:
        from helpers import writable_tempdir

        with writable_tempdir() as temp:
            input_path = Path(temp) / "wrong-type.json"
            input_path.write_text(
                json.dumps(
                    {
                        "suite": "wrong-type",
                        "provenance": {
                            "mode": "deterministic-fixture",
                            "declared_by": "deterministic-harness",
                            "independence_claim": False,
                            "agent_calls": 0,
                            "network_calls": 0,
                            "target_executions": 0,
                            "reviewer_receipts": [],
                        },
                        "cases": [
                            {
                                "id": "wrong-profile",
                                "profile": [],
                                "category": "clean",
                                "expected_findings": [],
                                "forbidden_finding_ids": [],
                                "expected_gap_ids": [],
                                "actual": {
                                    "matched_findings": [],
                                    "unmatched_finding_ids": [],
                                    "triggered_forbidden_ids": [],
                                    "gap_ids": [],
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code, payload = self.run_json("run_semantic_oracle.py", "--input", str(input_path))
            self.assertEqual(2, code, payload)
            self.assertEqual("ORACLE_INVALID_TYPE", payload["error"]["code"])

    def test_semantic_corpus_covers_profiles_controls_and_evidence(self) -> None:
        code, payload = self.run_json("run_semantic_oracle.py", "--self-test")
        self.assertEqual(0, code, payload)
        self.assertEqual(19, payload["corpus"]["case_total"])
        self.assertEqual(8, payload["corpus"]["profile_case_counts"]["plan-review"])
        self.assertEqual(11, payload["corpus"]["profile_case_counts"]["code-review"])
        self.assertEqual(1.0, payload["positive"]["metrics"]["evidence_present_rate"])
        self.assertFalse(payload["negative_probes"]["missing_evidence"]["passed"])
        self.assertFalse(payload["negative_probes"]["false_positive"]["passed"])

    def test_observation_packet_validation_is_non_executable_and_unobserved(self) -> None:
        code, payload = self.run_json("run_observation_packet.py", "--validate-only")
        self.assertEqual(0, code, payload)
        self.assertTrue(payload["passed"])
        self.assertEqual("user_operated_independent_session", payload["packet"]["execution_mode"])
        self.assertEqual("not_observed", payload["evidence_layers"]["fresh_context_semantic"])
        self.assertEqual(0, payload["claim_boundaries"]["agent_calls"])
        self.assertEqual(0, payload["claim_boundaries"]["network_calls"])
        self.assertEqual(0, payload["claim_boundaries"]["target_executions"])
        delegated = payload["delegated_review_contract"]
        self.assertEqual(1, delegated["formal_review_agent_count"])
        self.assertFalse(delegated["fork_context"])
        self.assertFalse(delegated["recursive_delegation_allowed"])
        self.assertEqual("closed", delegated["agent_close_status"])
        self.assertEqual(60, delegated["max_wait_slice_seconds"])
        self.assertFalse(delegated["wait_budget_reset_allowed"])
        self.assertTrue(delegated["progress_reporting_required"])

    def test_observation_packet_prepare_only_writes_user_bundle(self) -> None:
        from helpers import writable_tempdir

        with writable_tempdir() as temp:
            packet_dir = Path(temp) / "packet"
            code, payload = self.run_json(
                "run_observation_packet.py",
                "--prepare-dir",
                str(packet_dir),
            )
            self.assertEqual(0, code, payload)
            self.assertEqual(
                [
                    "INSTRUCTIONS.md",
                    "REVIEWER-DISPATCH-CHECKLIST.md",
                    "observation-template.json",
                    "packet.json",
                ],
                sorted(path.name for path in packet_dir.iterdir()),
            )
            instructions = (packet_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
            self.assertIn("不得自动启动", instructions)
            checklist = (
                packet_dir / "REVIEWER-DISPATCH-CHECKLIST.md"
            ).read_text(encoding="utf-8")
            self.assertIn("只创建一个 Reviewer 子 Agent", checklist)
            self.assertIn("fork_context=false", checklist)
            self.assertIn("单次窗口不超过 60 秒", checklist)
            self.assertIn("总 timeout 未因轮询重置", checklist)
            self.assertIn("close_agent", checklist)
            self.assertEqual(
                "stop_and_wait_for_user_operated_independent_sessions",
                payload["prepared_packet"]["next_action"],
            )

    def test_observation_report_cannot_write_into_custom_candidate(self) -> None:
        from helpers import writable_tempdir

        with writable_tempdir() as temp:
            root = Path(temp)
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "SKILL.md").write_text("# Candidate\n", encoding="utf-8")
            suite = {
                "schema_version": 1,
                "suite_id": "custom-source-boundary",
                "candidate": candidate.relative_to(REPO_ROOT).as_posix(),
                "baseline": None,
                "decision_question": "输出是否保持在被评估 source 之外？",
                "observation_policy": {
                    "required_variants": ["candidate"],
                    "require_independent_session": True,
                },
                "cases": [
                    {
                        "id": "positive",
                        "kind": "trigger-positive",
                        "prompt": "执行正例观察。",
                        "expected_observation": "应进入候选工作流。",
                        "inputs": [],
                    },
                    {
                        "id": "near-miss",
                        "kind": "trigger-near-miss",
                        "prompt": "执行近似项观察。",
                        "expected_observation": "不应误触发。",
                        "inputs": [],
                    },
                    {
                        "id": "behavior",
                        "kind": "behavior",
                        "prompt": "执行行为观察。",
                        "expected_observation": "应保持证据边界。",
                        "inputs": [],
                    },
                ],
            }
            suite_path = root / "suite.json"
            suite_path.write_text(json.dumps(suite), encoding="utf-8")
            forbidden_output = candidate / "observation.json"
            code, payload = self.run_json(
                "run_observation_packet.py",
                "--suite",
                str(suite_path),
                "--validate-only",
                "--output",
                str(forbidden_output),
            )
            self.assertEqual(2, code, payload)
            self.assertFalse(forbidden_output.exists())
            self.assertIn("candidate/baseline source", payload["error"]["message"])

    def test_static_contract_mode_reports_no_semantic_claim(self) -> None:
        code, payload = self.run_json("run_evals.py", "--static-contract-only")
        self.assertEqual(0, code, payload)
        self.assertEqual(0, payload["failed"])
        self.assertFalse(payload["claim_boundaries"]["semantic_review_quality_observed"])
        self.assertEqual(0, payload["claim_boundaries"]["agent_calls"])
        checks = {item["id"]: item for item in payload["checks"]}
        self.assertTrue(checks["semantic-runtime-negative-probes"]["passed"])
        self.assertTrue(checks["repository-ci-contract"]["passed"])
        self.assertTrue(checks["public-capability-boundaries"]["passed"])
        self.assertTrue(checks["current-only-review-contract"]["passed"])
        self.assertTrue(checks["current-only-scanner-probes"]["passed"])


if __name__ == "__main__":
    unittest.main()
