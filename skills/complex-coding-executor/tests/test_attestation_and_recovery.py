from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import WritableTemporaryDirectory


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_attestation import (  # noqa: E402
    AttestationError,
    build_attestation,
    validate_attestation,
    write_attestation,
)
from harness_event_writer import EventWriteError, append_event_and_update  # noqa: E402
from harness_review import ReviewGateError  # noqa: E402
from harness_execution import (  # noqa: E402
    ExecutionError,
    reconcile_snapshot,
    run_planner_approval_check,
)
from harness_state_io import load_state  # noqa: E402
from harness_state_schema import StateError, read_events  # noqa: E402
from harness_task_bundle import resolve_task_bundle  # noqa: E402


def task_contract() -> dict[str, object]:
    return {
        "task_id": "recovery-test",
        "plan_revision": 1,
        "artifacts": [],
        "stages": [
            {
                "id": "STG-01",
                "depends_on": [],
                "validation_ids": ["VAL-01"],
                "commit_expectation": "final",
            }
        ],
        "validations": [{"id": "VAL-01", "required": True}],
    }


def stage_review_payload() -> dict[str, object]:
    return {
        "result": "passed",
        "review_id": "REV-CODE-RECOVERY-001",
        "profile": "code-review",
        "scope": {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        "target_digest": "b" * 64,
        "verdict": "passed",
        "report_ref": "artifacts/reviews/stage-01.json",
        "open_counts": {
            "blocking": 0,
            "major": 0,
            "minor": 0,
            "advisory": 0,
            "total": 0,
        },
        "summary": "review passed",
    }


class RecoveryTest(unittest.TestCase):
    def make_bundle(self, *, commit_authorized: bool = True):
        temp = WritableTemporaryDirectory()
        self.addCleanup(temp.cleanup)
        workspace = Path(temp.name)
        task_dir = workspace / ".harness" / "tasks" / "task"
        task_dir.mkdir(parents=True)
        (task_dir / "execution-plan.md").write_text("# approved plan\n", encoding="utf-8")
        (task_dir / "plan-contract.json").write_text(
            json.dumps(task_contract(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        bundle = resolve_task_bundle(workspace, ".harness/tasks/task")
        payload = build_attestation(
            bundle,
            approved_by="user",
            approval_summary="approve implementation",
            commit_authorized=commit_authorized,
            approved_at="2026-07-10T00:00:00+00:00",
        )
        write_attestation(bundle.attestation_path, payload)
        return bundle

    def test_attestation_excludes_runtime_files(self) -> None:
        bundle = self.make_bundle()
        (bundle.ledger_path).write_text("", encoding="utf-8")
        (bundle.run_state_path).write_text("{}\n", encoding="utf-8")
        payload = validate_attestation(bundle)
        paths = {item["path"] for item in payload["immutable_files"]}
        self.assertEqual({"execution-plan.md", "plan-contract.json"}, paths)

    def test_attestation_detects_plan_mutation(self) -> None:
        bundle = self.make_bundle()
        bundle.plan_path.write_text("# changed plan\n", encoding="utf-8")
        with self.assertRaisesRegex(AttestationError, "ATTESTATION_HASH_MISMATCH"):
            validate_attestation(bundle)

    def test_event_append_updates_snapshot(self) -> None:
        bundle = self.make_bundle()
        result = append_event_and_update(
            bundle,
            "execution_started",
            occurred_at="2026-07-10T00:00:01+00:00",
        )
        self.assertEqual("in_progress", result["state"]["lifecycle"])
        self.assertEqual(1, load_state(bundle.run_state_path)["last_event_seq"])

    def test_snapshot_loss_is_reconciled_from_ledger(self) -> None:
        bundle = self.make_bundle()
        append_event_and_update(
            bundle,
            "execution_started",
            occurred_at="2026-07-10T00:00:01+00:00",
        )
        bundle.run_state_path.unlink()
        result = reconcile_snapshot(bundle)
        self.assertTrue(result["reconciled"])
        self.assertEqual(1, load_state(bundle.run_state_path)["last_event_seq"])

    def test_snapshot_write_failure_keeps_replayable_ledger(self) -> None:
        bundle = self.make_bundle()
        failure = StateError("RUN_STATE_WRITE_FAILED", "simulated")
        with mock.patch("harness_event_writer.write_state_atomic", side_effect=failure):
            with self.assertRaisesRegex(EventWriteError, "RUN_STATE_WRITE_FAILED"):
                append_event_and_update(
                    bundle,
                    "execution_started",
                    occurred_at="2026-07-10T00:00:01+00:00",
                )
        self.assertEqual(1, len(read_events(bundle.ledger_path)))
        result = reconcile_snapshot(bundle)
        self.assertTrue(result["reconciled"])

    def test_append_rejects_snapshot_drift_until_reconcile(self) -> None:
        bundle = self.make_bundle()
        append_event_and_update(
            bundle,
            "execution_started",
            occurred_at="2026-07-10T00:00:01+00:00",
        )
        state = load_state(bundle.run_state_path)
        state["last_event_seq"] = 0
        bundle.run_state_path.write_text(
            json.dumps(state, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EventWriteError, "RUN_STATE_DRIFT"):
            append_event_and_update(bundle, "note", payload={"summary": "blocked"})

    def test_append_rejects_unauthorized_commit_evidence(self) -> None:
        bundle = self.make_bundle(commit_authorized=False)
        with self.assertRaisesRegex(EventWriteError, "ATTESTATION_COMMIT_DENIED"):
            append_event_and_update(
                bundle,
                "commit_recorded",
                payload={
                    "commit": "0123456789abcdef",
                    "repository": "test-workspace",
                },
            )

    def test_commit_event_requires_hash_before_completion(self) -> None:
        bundle = self.make_bundle()
        append_event_and_update(bundle, "execution_started")
        with self.assertRaisesRegex(
            EventWriteError,
            "RUN_STATE_COMMIT_EVIDENCE_INVALID",
        ):
            append_event_and_update(bundle, "commit_recorded", payload={})

    def test_completed_rejects_missing_authorized_commit_evidence(self) -> None:
        bundle = self.make_bundle()
        review = stage_review_payload()
        report = bundle.task_dir / str(review["report_ref"])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}\n", encoding="utf-8")
        append_event_and_update(bundle, "execution_started")
        append_event_and_update(
            bundle,
            "stage_started",
            stage_id="STG-01",
            attempt=1,
        )
        append_event_and_update(
            bundle,
            "validation_recorded",
            stage_id="STG-01",
            payload={
                "validation_id": "VAL-01",
                "result": "passed",
                "summary": "validation passed",
            },
        )
        with mock.patch(
            "harness_event_writer.validate_review_gate",
            return_value=review,
        ):
            append_event_and_update(
                bundle,
                "review_recorded",
                stage_id="STG-01",
                attempt=1,
                payload=review,
                evidence_refs=[str(review["report_ref"])],
            )
            append_event_and_update(bundle, "stage_completed", stage_id="STG-01")
        with self.assertRaisesRegex(
            EventWriteError,
            "RUN_STATE_COMMIT_EVIDENCE_MISSING",
        ):
            append_event_and_update(bundle, "completed")

    def test_amendment_approved_requires_archive_activation(self) -> None:
        bundle = self.make_bundle()
        with self.assertRaisesRegex(
            EventWriteError,
            "AMENDMENT_EVENT_REQUIRES_ACTIVATION",
        ):
            append_event_and_update(
                bundle,
                "amendment_approved",
                payload={
                    "previous_revision": 0,
                    "previous_archive": "artifacts/amendments/revision-0000",
                    "previous_ledger_sha256": "0" * 64,
                    "carried_completed_stage_ids": [],
                },
            )

    def test_append_rejects_missing_evidence_file(self) -> None:
        bundle = self.make_bundle()
        with self.assertRaisesRegex(EventWriteError, "LEDGER_EVIDENCE_MISSING"):
            append_event_and_update(
                bundle,
                "execution_started",
                evidence_refs=["artifacts/validation/missing.md"],
            )

    def test_review_event_requires_report_ref_evidence(self) -> None:
        bundle = self.make_bundle()
        append_event_and_update(bundle, "execution_started")
        append_event_and_update(
            bundle,
            "stage_started",
            stage_id="STG-01",
            attempt=1,
        )
        with self.assertRaisesRegex(
            EventWriteError,
            "RUN_STATE_REVIEW_EVIDENCE_MISSING",
        ):
            append_event_and_update(
                bundle,
                "review_recorded",
                stage_id="STG-01",
                attempt=1,
                payload=stage_review_payload(),
            )

    def test_stage_completion_revalidates_current_receipt(self) -> None:
        bundle = self.make_bundle()
        review = stage_review_payload()
        report = bundle.task_dir / str(review["report_ref"])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}\n", encoding="utf-8")
        append_event_and_update(bundle, "execution_started")
        append_event_and_update(
            bundle,
            "stage_started",
            stage_id="STG-01",
            attempt=1,
        )
        append_event_and_update(
            bundle,
            "validation_recorded",
            stage_id="STG-01",
            payload={
                "validation_id": "VAL-01",
                "result": "passed",
                "summary": "validation passed",
            },
        )
        with mock.patch(
            "harness_event_writer.validate_review_gate",
            return_value=review,
        ):
            append_event_and_update(
                bundle,
                "review_recorded",
                stage_id="STG-01",
                attempt=1,
                payload=review,
                evidence_refs=[str(review["report_ref"])],
            )
        with mock.patch(
            "harness_event_writer.validate_review_gate",
            side_effect=ReviewGateError(
                "REVIEW_TARGET_STALE",
                "target changed",
            ),
        ):
            with self.assertRaisesRegex(EventWriteError, "REVIEW_TARGET_STALE"):
                append_event_and_update(
                    bundle,
                    "stage_completed",
                    stage_id="STG-01",
                )

    def test_planner_checker_requires_valid_json_result(self) -> None:
        bundle = self.make_bundle()
        completed = mock.Mock(returncode=0, stdout="not-json", stderr="")
        with mock.patch("harness_execution.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(
                ExecutionError,
                "TASK_PLANNER_CHECK_INVALID_OUTPUT",
            ):
                run_planner_approval_check(bundle)


if __name__ == "__main__":
    unittest.main()
