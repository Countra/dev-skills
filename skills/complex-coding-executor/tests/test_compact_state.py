from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import (
    WritableTemporaryDirectory,
    compact_contract,
    write_json,
    write_workspace_bundle,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harness_state.py"
sys.path.insert(0, str(SCRIPT.parent))

from harness_state_store import StateError, write_state  # noqa: E402


class CompactStateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.task_dir = write_workspace_bundle(self.workspace)

    def run_state(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-B", str(SCRIPT), "--workspace", str(self.workspace), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    def approve(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_state(
            "approve",
            "--implementation",
            "--plan-review-mode",
            "same-context",
            "--plan-review-summary",
            "未发现 blocking 或 major 问题",
            *extra,
        )

    def record_stage(self, stage: str = "STG-01", validation: str = "VAL-01") -> None:
        started = self.run_state("start", "--stage", stage)
        self.assertEqual(0, started.returncode, started.stdout + started.stderr)
        validated = self.run_state(
            "validate",
            "--stage",
            stage,
            "--validation",
            validation,
            "--result",
            "passed",
            "--exit-code",
            "0",
            "--duration-ms",
            "10",
            "--summary",
            "目标测试通过",
        )
        self.assertEqual(
            0,
            validated.returncode,
            validated.stdout + validated.stderr,
        )
        reviewed = self.run_state(
            "review",
            "--scope",
            stage,
            "--verdict",
            "passed",
            "--mode",
            "same-context",
            "--summary",
            "未发现 blocking 或 major 问题",
        )
        self.assertEqual(
            0,
            reviewed.returncode,
            reviewed.stdout + reviewed.stderr,
        )
        finished = self.run_state("finish-stage", "--stage", stage)
        self.assertEqual(0, finished.returncode, finished.stdout + finished.stderr)

    def record_final_validation(self) -> None:
        self.assertEqual(
            0,
            self.run_state(
                "validate",
                "--stage",
                "final",
                "--validation",
                "VAL-FINAL",
                "--result",
                "passed",
                "--exit-code",
                "0",
                "--duration-ms",
                "20",
                "--summary",
                "最终集成验证通过",
            ).returncode,
        )

    def record_final_review(self) -> None:
        self.assertEqual(
            0,
            self.run_state(
                "review",
                "--scope",
                "final",
                "--verdict",
                "passed",
                "--mode",
                "same-context",
                "--summary",
                "最终集成未发现 blocking 或 major 问题",
            ).returncode,
        )

    def state(self) -> dict:
        return json.loads((self.task_dir / "run-state.json").read_text(encoding="utf-8"))

    def test_status_before_approval_is_human_and_does_not_create_state(self) -> None:
        completed = self.run_state("status")
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("Lifecycle: planning", completed.stdout)
        self.assertNotIn("{", completed.stdout)
        self.assertFalse((self.task_dir / "run-state.json").exists())

    def test_atomic_state_setup_failure_uses_stable_error(self) -> None:
        with mock.patch(
            "harness_state_store.tempfile.mkstemp",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(StateError) as raised:
                write_state(self.task_dir, {"task_id": "executor-task"})
        self.assertEqual("TASK_STATE_WRITE_FAILED", raised.exception.code)

    def test_approve_records_review_and_separate_authorizations(self) -> None:
        contract = compact_contract()
        contract["permissions_requested"]["commit"] = True
        self.task_dir = write_workspace_bundle(self.workspace, contract)
        completed = self.approve("--commit")
        self.assertEqual(0, completed.returncode, completed.stdout)
        state = self.state()
        self.assertTrue(state["authorizations"]["commit"])
        self.assertFalse(state["authorizations"]["external_write"])
        self.assertEqual("same-context", state["approval"]["plan_review"]["mode"])

    def test_unrequested_permission_requires_plan_update(self) -> None:
        failed = self.approve("--commit")
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("TASK_PERMISSION_NOT_REQUESTED", failed.stdout)

        contract = compact_contract()
        contract["permissions_requested"]["external_write"] = True
        self.task_dir = write_workspace_bundle(self.workspace, contract)
        self.assertEqual(0, self.approve().returncode)
        authorized = self.run_state("authorize", "--external-write")
        self.assertEqual(0, authorized.returncode, authorized.stdout)
        self.assertTrue(self.state()["authorizations"]["external_write"])

    def test_stage_requires_validation_and_review(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        self.assertEqual(0, self.run_state("start", "--stage", "STG-01").returncode)
        failed = self.run_state("finish-stage", "--stage", "STG-01")
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("TASK_VALIDATION_REQUIRED", failed.stdout)

    def test_stage_dependency_cannot_be_skipped(self) -> None:
        contract = compact_contract(two_stages=True)
        self.task_dir = write_workspace_bundle(self.workspace, contract)
        self.assertEqual(0, self.approve().returncode)
        failed = self.run_state("start", "--stage", "STG-02")
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("TASK_STAGE_DEPENDENCY", failed.stdout)

    def test_final_validation_waits_for_all_stages_and_gates_final_review(self) -> None:
        self.task_dir = write_workspace_bundle(
            self.workspace,
            compact_contract(two_stages=True),
        )
        self.assertEqual(0, self.approve().returncode)
        early = self.run_state(
            "validate",
            "--stage",
            "final",
            "--validation",
            "VAL-FINAL",
            "--result",
            "passed",
            "--summary",
            "过早运行",
        )
        self.assertNotEqual(0, early.returncode)
        self.assertIn("TASK_STAGE_REMAINING", early.stdout)

        self.record_stage()
        self.record_stage("STG-02", "VAL-02")
        self.assertEqual("run final integration validation", self.state()["next_action"])
        missing = self.run_state(
            "review",
            "--scope",
            "final",
            "--verdict",
            "passed",
            "--mode",
            "same-context",
            "--summary",
            "尚未执行最终验证",
        )
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("TASK_VALIDATION_REQUIRED", missing.stdout)

        self.record_final_validation()
        self.record_final_review()
        self.assertEqual("complete", self.state()["next_action"])
        self.assertEqual(0, self.run_state("complete").returncode)

    def test_rerun_final_validation_invalidates_final_review(self) -> None:
        self.task_dir = write_workspace_bundle(
            self.workspace,
            compact_contract(two_stages=True),
        )
        self.assertEqual(0, self.approve().returncode)
        self.record_stage()
        self.record_stage("STG-02", "VAL-02")
        self.record_final_validation()
        self.record_final_review()

        self.record_final_validation()
        failed = self.run_state("complete")
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("TASK_REVIEW_REQUIRED", failed.stdout)

    def test_reapproval_discards_final_validation_and_review(self) -> None:
        self.task_dir = write_workspace_bundle(
            self.workspace,
            compact_contract(two_stages=True),
        )
        self.assertEqual(0, self.approve().returncode)
        self.record_stage()
        self.record_stage("STG-02", "VAL-02")
        self.record_final_validation()
        self.record_final_review()

        result = self.run_state("reapproval", "--reason", "最终集成范围发生变化")
        self.assertEqual(0, result.returncode, result.stdout)
        state = self.state()
        self.assertNotIn("VAL-FINAL", state["validations"])
        self.assertNotIn("final", state["reviews"])

    def test_repeated_approve_cannot_reset_active_revision(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        repeated = self.approve()
        self.assertNotEqual(0, repeated.returncode)
        self.assertIn("TASK_ALREADY_APPROVED", repeated.stdout)

    def test_corrupt_stage_reference_fails_closed(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        state = self.state()
        state["completed_stage_ids"] = ["STG-99"]
        (self.task_dir / "run-state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        completed = self.run_state("status")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("TASK_STATE_INVALID", completed.stdout)

    def test_corrupt_stage_type_fails_with_stable_error(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        state = self.state()
        state["completed_stage_ids"] = [{"id": "STG-01"}]
        write_json(self.task_dir / "run-state.json", state)
        completed = self.run_state("status")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("TASK_STATE_INVALID", completed.stdout)

    def test_completed_stage_requires_its_validation_evidence(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        self.record_stage()
        state = self.state()
        state["validations"] = {}
        write_json(self.task_dir / "run-state.json", state)
        completed = self.run_state("status")
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("TASK_STATE_INVALID", completed.stdout)
        self.assertIn("VAL-01", completed.stdout)

    def test_validation_invalidates_previous_review(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        self.assertEqual(0, self.run_state("start", "--stage", "STG-01").returncode)
        validation = (
            "validate",
            "--stage",
            "STG-01",
            "--validation",
            "VAL-01",
            "--result",
            "passed",
            "--summary",
            "通过",
        )
        self.assertEqual(0, self.run_state(*validation).returncode)
        self.assertEqual(
            0,
            self.run_state(
                "review",
                "--scope",
                "STG-01",
                "--verdict",
                "passed",
                "--mode",
                "same-context",
                "--summary",
                "通过",
            ).returncode,
        )
        self.assertEqual(0, self.run_state(*validation).returncode)
        failed = self.run_state("finish-stage", "--stage", "STG-01")
        self.assertIn("TASK_REVIEW_REQUIRED", failed.stdout)

    def test_plan_drift_reports_awaiting_reapproval(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        plan = self.task_dir / "execution-plan.md"
        plan.write_text(plan.read_text(encoding="utf-8") + "\n补充范围内说明。\n", encoding="utf-8")
        completed = self.run_state("status")
        self.assertEqual(1, completed.returncode)
        self.assertIn("Lifecycle: awaiting_reapproval", completed.stdout)
        self.assertIn("Approval current: no", completed.stdout)

    def test_reapproval_moves_to_new_revision_and_can_carry_completed_stage(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        contract = compact_contract(two_stages=True)
        contract["permissions_requested"]["commit"] = True
        self.task_dir = write_workspace_bundle(self.workspace, contract)
        self.assertEqual(0, self.approve("--commit").returncode)
        self.record_stage()
        self.assertEqual(
            0,
            self.run_state("reapproval", "--reason", "公共范围发生变化").returncode,
        )

        contract["plan_revision"] = 2
        write_json(self.task_dir / "plan-contract.json", contract)
        plan = self.task_dir / "execution-plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8") + "\n已批准 revision 2。\n",
            encoding="utf-8",
        )
        waiting = self.run_state("status")
        self.assertEqual(1, waiting.returncode)
        self.assertIn("Lifecycle: awaiting_reapproval", waiting.stdout)

        approved = self.approve("--carry-completed", "STG-01")
        self.assertEqual(0, approved.returncode, approved.stdout)
        state = self.state()
        self.assertEqual(2, state["plan_revision"])
        self.assertEqual(["STG-01"], state["completed_stage_ids"])
        self.assertFalse(state["authorizations"]["commit"])
        self.assertEqual("start STG-02", state["next_action"])

    def test_reapproval_discards_incomplete_stage_evidence(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        self.assertEqual(0, self.run_state("start", "--stage", "STG-01").returncode)
        self.assertEqual(
            0,
            self.run_state(
                "validate",
                "--stage",
                "STG-01",
                "--validation",
                "VAL-01",
                "--result",
                "passed",
                "--summary",
                "阶段验证通过",
            ).returncode,
        )
        result = self.run_state("reapproval", "--reason", "阶段范围发生变化")
        self.assertEqual(0, result.returncode, result.stdout)
        state = self.state()
        self.assertEqual("awaiting_reapproval", state["lifecycle"])
        self.assertIsNone(state["current_stage_id"])
        self.assertEqual({}, state["validations"])

    def test_reapproval_cannot_carry_stage_with_changed_validation_contract(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        contract = compact_contract(two_stages=True)
        self.task_dir = write_workspace_bundle(self.workspace, contract)
        self.assertEqual(0, self.approve().returncode)
        self.record_stage()
        self.assertEqual(
            0,
            self.run_state("reapproval", "--reason", "验证契约发生变化").returncode,
        )

        contract["plan_revision"] = 2
        contract["validations"][0]["command"] = "python -m unittest changed"
        write_json(self.task_dir / "plan-contract.json", contract)
        failed = self.approve("--carry-completed", "STG-01")
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("TASK_STAGE_CARRY_INVALID", failed.stdout)
        self.assertEqual(1, self.state()["plan_revision"])

    def test_new_revision_cannot_replace_task_identity(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        contract_path = self.task_dir / "plan-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["task_id"] = "different-task"
        contract["plan_revision"] = 2
        write_json(contract_path, contract)
        pointer_path = self.workspace / ".harness" / "active-task.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        pointer["task_id"] = "different-task"
        write_json(pointer_path, pointer)
        failed = self.approve()
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("TASK_ID_MISMATCH", failed.stdout)

    def test_block_and_resume_keep_one_current_reason(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        self.assertEqual(
            0,
            self.run_state(
                "block",
                "--reason",
                "缺少必要环境",
                "--next-action",
                "准备环境后恢复",
            ).returncode,
        )
        self.assertEqual("blocked", self.state()["lifecycle"])
        self.assertEqual(
            0,
            self.run_state("resume", "--next-action", "继续 STG-01").returncode,
        )
        self.assertIsNone(self.state()["blocker"])

    def test_high_risk_requires_independent_review(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.task_dir = write_workspace_bundle(
            self.workspace,
            compact_contract(task_id="high-risk", risk="high"),
        )
        failed = self.approve()
        self.assertIn("TASK_REVIEW_REQUIRED", failed.stdout)
        passed = self.run_state(
            "approve",
            "--implementation",
            "--plan-review-mode",
            "independent",
            "--plan-review-summary",
            "独立审查未发现 blocking 或 major 问题",
        )
        self.assertEqual(0, passed.returncode, passed.stdout)

        self.assertEqual(0, self.run_state("start", "--stage", "STG-01").returncode)
        self.assertEqual(
            0,
            self.run_state(
                "validate",
                "--stage",
                "STG-01",
                "--validation",
                "VAL-01",
                "--result",
                "passed",
                "--summary",
                "目标验证通过",
            ).returncode,
        )
        rejected = self.run_state(
            "review",
            "--scope",
            "STG-01",
            "--verdict",
            "passed",
            "--mode",
            "same-context",
            "--summary",
            "当前上下文未发现问题",
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("TASK_REVIEW_REQUIRED", rejected.stdout)
        self.assertEqual(
            0,
            self.run_state(
                "review",
                "--scope",
                "STG-01",
                "--verdict",
                "passed",
                "--mode",
                "independent",
                "--summary",
                "独立审查通过",
            ).returncode,
        )
        self.assertEqual(0, self.run_state("finish-stage", "--stage", "STG-01").returncode)
        final_rejected = self.run_state(
            "review",
            "--scope",
            "final",
            "--verdict",
            "passed",
            "--mode",
            "same-context",
            "--summary",
            "当前上下文最终审查通过",
        )
        self.assertNotEqual(0, final_rejected.returncode)
        self.assertIn("TASK_REVIEW_REQUIRED", final_rejected.stdout)

    def test_complete_lifecycle_uses_one_mutable_state_file(self) -> None:
        self.assertEqual(0, self.approve().returncode)
        self.record_stage()
        self.assertEqual(
            0,
            self.run_state(
                "review",
                "--scope",
                "final",
                "--verdict",
                "passed",
                "--mode",
                "same-context",
                "--summary",
                "最终集成未发现 blocking 或 major 问题",
            ).returncode,
        )
        self.assertEqual(0, self.run_state("complete").returncode)
        self.assertEqual("completed", self.state()["lifecycle"])
        self.assertFalse((self.task_dir / "ledger.jsonl").exists())
        self.assertFalse((self.task_dir / "attestation.json").exists())
        self.assertFalse((self.task_dir / "artifacts").exists())

    def test_planned_commit_can_be_authorized_after_completion(self) -> None:
        contract = compact_contract()
        contract["permissions_requested"]["commit"] = True
        self.task_dir = write_workspace_bundle(self.workspace, contract)
        self.assertEqual(0, self.approve().returncode)
        self.record_stage()
        self.assertEqual(
            0,
            self.run_state(
                "review",
                "--scope",
                "final",
                "--verdict",
                "passed",
                "--mode",
                "same-context",
                "--summary",
                "最终集成未发现 blocking 或 major 问题",
            ).returncode,
        )
        self.assertEqual(0, self.run_state("complete").returncode)
        authorized = self.run_state("authorize", "--commit")
        self.assertEqual(0, authorized.returncode, authorized.stdout)
        state = self.state()
        self.assertEqual("completed", state["lifecycle"])
        self.assertTrue(state["authorizations"]["commit"])


if __name__ == "__main__":
    unittest.main()
