from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_plan_check import validate_task  # noqa: E402


def valid_contract() -> dict[str, object]:
    return {
        "task_id": "test-task",
        "plan_revision": 1,
        "lifecycle_route": "managed",
        "plan_profile": "lite",
        "goal": {"id": "GOAL-01", "summary": "交付可观察结果"},
        "requirements": [{"id": "REQ-01", "priority": "must", "summary": "实现需求"}],
        "acceptance_criteria": [
            {"id": "AC-01", "requirement_ids": ["REQ-01"], "summary": "Given 输入 When 执行 Then 成功"}
        ],
        "nonfunctional_requirements": [{"id": "NFR-01", "summary": "保持可维护性"}],
        "artifacts": [],
        "stages": [
            {
                "id": "STG-01",
                "title": "实现并验证",
                "depends_on": [],
                "requirement_ids": ["REQ-01"],
                "acceptance_ids": ["AC-01"],
                "nonfunctional_ids": ["NFR-01"],
                "validation_ids": ["VAL-01"],
                "allowed_changes": ["src/"],
                "forbidden_changes": ["unrelated/"],
                "entry_conditions": ["plan approved"],
                "exit_conditions": ["tests pass"],
                "risk": "low",
                "commit_expectation": "final",
            }
        ],
        "validations": [
            {
                "id": "VAL-01",
                "kind": "test",
                "required": True,
                "covers": ["AC-01", "NFR-01"],
                "command": "python -m unittest",
                "evidence_path": "artifacts/validation/tests.md",
            }
        ],
        "research": {"mode": "local-only", "evidence_artifact_ids": [], "unresolved": []},
        "approval_policy": {
            "implementation_requires_user_approval": True,
            "commit_requires_explicit_authorization": True,
            "external_write_requires_explicit_authorization": True,
            "elevated_tool_requires_explicit_authorization": True,
        },
        "reapproval_triggers": ["scope changes"],
        "stop_conditions": ["user requests pause"],
    }


def valid_plan(extra: str = "") -> str:
    headings = [
        "规划摘要",
        "问题定义",
        "需求与验收",
        "调研门禁",
        "规范发现门禁",
        "开发质量门禁",
        "上下文",
        "候选方案",
        "决策",
        "影响面矩阵",
        "实施计划",
        "环境",
        "Git 上下文",
        "工具",
        "长期进程管理",
        "验证",
        "文档",
        "文件写入策略",
        "方案质量门禁",
        "规划自查",
        "就绪门禁",
        "方案批准",
        "方案变更门禁",
        "Artifact Index",
        "Executor Handoff",
    ]
    sections: list[str] = ["# Test Plan"]
    for heading in headings:
        body = "complete"
        if heading == "规划摘要":
            body = (
                "Task ID: test-task\n\n"
                "Plan revision: 1\n\n"
                "Lifecycle route: managed\n\n"
                "Plan profile: lite"
            )
        elif heading == "问题定义":
            body = "GOAL-01"
        elif heading == "需求与验收":
            body = "REQ-01 AC-01 NFR-01"
        elif heading == "候选方案":
            body = "### 方案 A\n最小改动\n\n### 方案 B\n结构化改动"
        elif heading == "实施计划":
            body = (
                "### STG-01：实现并验证\n"
                "REQ-01 AC-01 NFR-01 VAL-01 src/ unrelated/"
            )
        sections.append(f"## {heading}\n\n{body}")
    sections.append(extra)
    return "\n\n".join(sections) + "\n"


class PlannerBundleTest(unittest.TestCase):
    def make_task(self, contract: dict[str, object] | None = None, plan: str | None = None) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        task_dir = Path(temp.name)
        (task_dir / "plan-contract.json").write_text(
            json.dumps(contract or valid_contract(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (task_dir / "execution-plan.md").write_text(plan or valid_plan(), encoding="utf-8")
        return task_dir

    def error_codes(self, task_dir: Path, mode: str = "approval") -> set[str]:
        return {issue.code for issue in validate_task(task_dir, mode) if issue.level == "error"}

    def test_valid_bundle_passes_approval(self) -> None:
        self.assertEqual(set(), self.error_codes(self.make_task()))

    def test_unknown_field_is_rejected(self) -> None:
        contract = valid_contract()
        contract["unknown_field"] = "not allowed"
        self.assertIn("TASK_CONTRACT_UNKNOWN_FIELD", self.error_codes(self.make_task(contract)))

    def test_stage_cycle_and_broken_reference_are_rejected(self) -> None:
        contract = valid_contract()
        stage = contract["stages"][0]
        stage["depends_on"] = ["STG-01", "STG-99"]
        codes = self.error_codes(self.make_task(contract))
        self.assertIn("TASK_CONTRACT_STAGE_CYCLE", codes)
        self.assertIn("TASK_CONTRACT_BROKEN_REFERENCE", codes)

    def test_required_artifact_must_exist(self) -> None:
        contract = valid_contract()
        contract["artifacts"] = [
            {
                "id": "ART-01",
                "kind": "architecture",
                "path": "artifacts/architecture/change-map.md",
                "required": True,
                "approval_included": True,
            }
        ]
        plan = valid_plan().replace("## Artifact Index\n\ncomplete", "## Artifact Index\n\nART-01")
        self.assertIn("TASK_ARTIFACT_MISSING", self.error_codes(self.make_task(contract, plan)))

    def test_required_artifact_must_be_attested_and_nonempty(self) -> None:
        contract = valid_contract()
        contract["artifacts"] = [
            {
                "id": "ART-01",
                "kind": "architecture",
                "path": "artifacts/architecture/change-map.md",
                "required": True,
                "approval_included": False,
            }
        ]
        plan = valid_plan().replace("## Artifact Index\n\ncomplete", "## Artifact Index\n\nART-01")
        task_dir = self.make_task(contract, plan)
        artifact = task_dir / "artifacts" / "architecture" / "change-map.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("", encoding="utf-8")
        codes = self.error_codes(task_dir)
        self.assertIn("TASK_CONTRACT_ARTIFACT_NOT_ATTESTED", codes)
        self.assertIn("TASK_ARTIFACT_EMPTY", codes)

    def test_plan_contract_id_drift_is_rejected(self) -> None:
        plan = valid_plan().replace("REQ-01 AC-01 NFR-01", "REQ-99 AC-01 NFR-01")
        codes = self.error_codes(self.make_task(plan=plan))
        self.assertIn("TASK_PLAN_MISSING_ID", codes)
        self.assertIn("TASK_PLAN_EXTRA_ID", codes)

    def test_stage_contract_drift_is_rejected(self) -> None:
        plan = valid_plan().replace("VAL-01 src/ unrelated/", "VAL-01 unrelated/")
        self.assertIn("TASK_PLAN_STAGE_DRIFT", self.error_codes(self.make_task(plan=plan)))

    def test_duplicate_stage_heading_is_rejected(self) -> None:
        duplicate = "### STG-01：实现并验证\nREQ-01 AC-01 NFR-01 VAL-01 src/ unrelated/"
        plan = valid_plan().replace("## 环境", f"{duplicate}\n\n## 环境")
        self.assertIn("TASK_PLAN_STAGE_DUPLICATE", self.error_codes(self.make_task(plan=plan)))

    def test_summary_revision_drift_is_rejected(self) -> None:
        plan = valid_plan().replace("Plan revision: 1", "Plan revision: 2")
        self.assertIn("TASK_PLAN_CONTRACT_DRIFT", self.error_codes(self.make_task(plan=plan)))

    def test_mutable_execution_section_is_rejected(self) -> None:
        plan = valid_plan("## 实施进度\n\ncurrent stage")
        self.assertIn("TASK_PLAN_MUTABLE_SECTION", self.error_codes(self.make_task(plan=plan)))

    def test_code_angle_brackets_are_not_template_placeholders(self) -> None:
        plan = valid_plan().replace(
            "## 上下文\n\ncomplete",
            "## 上下文\n\nList<T> 与 <video> 是被规划对象。",
        )
        self.assertNotIn(
            "TASK_PLAN_PLACEHOLDER",
            self.error_codes(self.make_task(plan=plan)),
        )

    def test_known_template_placeholder_is_rejected(self) -> None:
        plan = valid_plan().replace(
            "## 上下文\n\ncomplete",
            "## 上下文\n\n仍有 <task-id> 未替换。",
        )
        self.assertIn(
            "TASK_PLAN_PLACEHOLDER",
            self.error_codes(self.make_task(plan=plan)),
        )

    def test_stage_traceability_covers_acceptance_nfr_and_required_validation(self) -> None:
        contract = valid_contract()
        stage = contract["stages"][0]
        stage["acceptance_ids"] = []
        stage["nonfunctional_ids"] = []
        stage["validation_ids"] = []
        codes = self.error_codes(self.make_task(contract))
        self.assertIn("TASK_CONTRACT_UNCOVERED_STAGE_TRACE", codes)
        self.assertIn("TASK_CONTRACT_UNASSIGNED_VALIDATION", codes)

    def test_explicit_approval_policy_cannot_be_weakened(self) -> None:
        contract = valid_contract()
        policy = contract["approval_policy"]
        policy["commit_requires_explicit_authorization"] = False
        self.assertIn(
            "TASK_CONTRACT_APPROVAL_POLICY_WEAK",
            self.error_codes(self.make_task(contract)),
        )

    def test_high_risk_stage_requires_full_profile(self) -> None:
        contract = valid_contract()
        contract["stages"][0]["risk"] = "high"
        self.assertIn(
            "TASK_CONTRACT_PROFILE_UNDERSCOPED",
            self.error_codes(self.make_task(contract)),
        )

    def test_online_research_does_not_read_outside_task_dir(self) -> None:
        contract = valid_contract()
        contract["research"] = {
            "mode": "online-required",
            "evidence_artifact_ids": ["ART-01"],
            "unresolved": [],
        }
        contract["artifacts"] = [
            {
                "id": "ART-01",
                "kind": "research",
                "path": "../outside-research.md",
                "required": False,
                "approval_included": False,
            }
        ]
        plan = valid_plan().replace(
            "## Artifact Index\n\ncomplete",
            "## Artifact Index\n\nART-01",
        )
        task_dir = self.make_task(contract, plan)
        outside = task_dir.parent / "outside-research.md"
        outside.write_text("Source: https://example.com\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)

        codes = self.error_codes(task_dir)
        self.assertIn("TASK_CONTRACT_UNSAFE_PATH", codes)
        self.assertIn("TASK_PLAN_RESEARCH_SOURCE_MISSING", codes)

    def test_draft_allows_pending_gate_and_open_decision(self) -> None:
        task_dir = self.make_task(plan=valid_plan().replace("## 调研门禁\n\ncomplete", "## 调研门禁\n\npending"))
        (task_dir / "pending-decisions.md").write_text("状态: open\n", encoding="utf-8")
        self.assertNotIn("TASK_PLAN_GATE_PENDING", self.error_codes(task_dir, mode="draft"))
        self.assertNotIn("TASK_PLAN_OPEN_DECISION", self.error_codes(task_dir, mode="draft"))


if __name__ == "__main__":
    unittest.main()
