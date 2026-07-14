"""七维语义 review 与三层 evidence report 测试。"""

from __future__ import annotations

import unittest

from _helpers import temporary_workspace, valid_semantic_review, valid_suite, write_skill
from skill_evaluation_lab.errors import ReportError
from skill_evaluation_lab.observations import import_observations
from skill_evaluation_lab.packets import build_packet
from skill_evaluation_lab.reports import build_report, render_markdown, verify_current_sources
from skill_evaluation_lab.static_checks import evaluate_skill


def user_bundle(packet: dict[str, object], *, complete: bool) -> dict[str, object]:
    cases = packet["cases"]
    assert isinstance(cases, list)
    selected = cases if complete else cases[:1]
    return {
        "schema_version": 1,
        "packet_fingerprint": packet["packet_fingerprint"],
        "declared_by": "user",
        "sessions": [
            {
                "case_id": item["case_id"],
                "variant": item["variant"],
                "session_ref": f"session-{index + 1}",
                "status": "pass",
                "notes": "用户声明观察符合预期。",
                "artifacts": [],
            }
            for index, item in enumerate(selected)
        ],
    }


class ReportTests(unittest.TestCase):
    def test_static_and_semantic_report_is_ready_without_runtime_claims(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            static = evaluate_skill(workspace, source, evaluation_id="report-evaluation")
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            report = build_report(static, review)
            self.assertEqual(report["evidence_coverage"]["observed"]["status"], "not_requested")
            self.assertFalse(report["runtime_claims_allowed"])
            self.assertTrue(report["completion"]["ready_for_agent_conclusion"])
            self.assertEqual(report["completion"]["conclusion_owner"], "current_agent")
            self.assertNotIn("overall_score", report)

    def test_requested_but_missing_observation_is_not_observed(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            static = evaluate_skill(workspace, source)
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            review["observation_decision"] = "requested"
            report = build_report(static, review)
            self.assertEqual(report["evidence_coverage"]["observed"]["status"], "not_observed")
            self.assertIn("不得声明", report["claim_boundaries"][-1])

    def test_partial_and_complete_observations_control_runtime_claim_boundary(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            static = evaluate_skill(workspace, source)
            packet, _ = build_packet(workspace, valid_suite())
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            review["observation_decision"] = "provided"
            partial = import_observations(workspace, packet, user_bundle(packet, complete=False))
            partial_report = build_report(static, review, partial)
            self.assertEqual(partial_report["evidence_coverage"]["observed"]["status"], "partial")
            self.assertFalse(partial_report["runtime_claims_allowed"])
            complete = import_observations(workspace, packet, user_bundle(packet, complete=True))
            complete_report = build_report(static, review, complete)
            self.assertEqual(complete_report["evidence_coverage"]["observed"]["status"], "complete")
            self.assertTrue(complete_report["runtime_claims_allowed"])

    def test_rejects_review_id_hash_evidence_and_observation_decision_drift(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            static = evaluate_skill(workspace, source)
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            review["evaluation_id"] = "other-evaluation"
            with self.assertRaisesRegex(ReportError, "evaluation_id"):
                build_report(static, review)
            review = valid_semantic_review(static["evaluation_id"], "e" * 64)
            with self.assertRaisesRegex(ReportError, "source hash"):
                build_report(static, review)
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            review["dimensions"][0]["evidence"][0]["path"] = "missing.md"
            with self.assertRaisesRegex(ReportError, "不属于"):
                build_report(static, review)
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            review["observation_decision"] = "provided"
            with self.assertRaisesRegex(ReportError, "未提供"):
                build_report(static, review)

    def test_report_entry_rejects_current_source_drift(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            static = evaluate_skill(workspace, source)
            self.assertEqual(verify_current_sources(workspace, static), (source,))
            (source / "SKILL.md").write_text(
                (source / "SKILL.md").read_text(encoding="utf-8") + "\nsource drift\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ReportError, "已变化"):
                verify_current_sources(workspace, static)

    def test_report_rejects_observation_baseline_hash_drift(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            baseline = write_skill(workspace, "baseline-skill")
            static = evaluate_skill(workspace, source, baseline=baseline)
            packet, _ = build_packet(
                workspace,
                valid_suite(baseline=baseline.relative_to(workspace).as_posix()),
            )
            imported = import_observations(workspace, packet, user_bundle(packet, complete=True))
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            review["observation_decision"] = "provided"
            imported["baseline_tree_sha256"] = "0" * 64
            with self.assertRaisesRegex(ReportError, "baseline"):
                build_report(static, review, imported)

    def test_markdown_keeps_layers_and_current_agent_ownership(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            static = evaluate_skill(workspace, source)
            review = valid_semantic_review(
                static["evaluation_id"],
                static["candidate"]["tree_sha256"],
            )
            markdown = render_markdown(build_report(static, review))
            self.assertIn("## 已证明", markdown)
            self.assertIn("## 审查判断", markdown)
            self.assertIn("## 用户观察", markdown)
            self.assertIn("## 假设与限制", markdown)
            self.assertIn("未导入用户独立会话观察", markdown)
            self.assertIn("## 当前 Agent 后续动作", markdown)
            self.assertNotIn("overall score", markdown.lower())


if __name__ == "__main__":
    unittest.main()
