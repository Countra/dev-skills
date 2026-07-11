from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_state import replay_events  # noqa: E402
from harness_state_io import (  # noqa: E402
    build_event,
    load_state,
    state_differences,
    write_state_atomic,
)
from harness_state_schema import StateError, read_events  # noqa: E402
from harness_task_bundle import TaskBundleError, resolve_task_bundle  # noqa: E402


def contract() -> dict[str, object]:
    return {
        "task_id": "executor-test",
        "plan_revision": 1,
        "stages": [
            {
                "id": "STG-01",
                "depends_on": [],
                "validation_ids": ["VAL-01"],
            }
        ],
        "validations": [{"id": "VAL-01", "required": True}],
    }


class TaskBundleTest(unittest.TestCase):
    def make_workspace(self, pointer_extra: dict[str, object] | None = None) -> tuple[Path, Path]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        workspace = Path(temp.name)
        task_dir = workspace / ".harness" / "tasks" / "task"
        task_dir.mkdir(parents=True)
        (task_dir / "execution-plan.md").write_text("# plan\n", encoding="utf-8")
        (task_dir / "plan-contract.json").write_text(
            json.dumps(contract(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        pointer: dict[str, object] = {
            "task_id": "executor-test",
            "task_dir": ".harness/tasks/task",
            "run_state_path": "run-state.json",
            "updated_at": "2026-07-10T00:00:00+00:00",
        }
        pointer.update(pointer_extra or {})
        (workspace / ".harness" / "active-task.json").write_text(
            json.dumps(pointer, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return workspace, task_dir

    def test_pointer_only_bundle_resolves(self) -> None:
        workspace, task_dir = self.make_workspace()
        bundle = resolve_task_bundle(workspace)
        self.assertEqual(task_dir.resolve(), bundle.task_dir)
        self.assertEqual("executor-test", bundle.task_id)

    def test_pointer_rejects_runtime_state_fields(self) -> None:
        workspace, _ = self.make_workspace({"status": "in_progress"})
        with self.assertRaisesRegex(TaskBundleError, "TASK_POINTER_UNKNOWN_FIELD"):
            resolve_task_bundle(workspace)

    def test_pointer_rejects_invalid_timestamp_and_relative_path(self) -> None:
        workspace, _ = self.make_workspace({"updated_at": "not-a-time"})
        with self.assertRaisesRegex(TaskBundleError, "TASK_POINTER_INVALID_FIELD"):
            resolve_task_bundle(workspace)
        workspace, _ = self.make_workspace(
            {"updated_at": "2026-07-10 00:00:00+00:00"}
        )
        with self.assertRaisesRegex(TaskBundleError, "TASK_POINTER_INVALID_FIELD"):
            resolve_task_bundle(workspace)
        workspace, _ = self.make_workspace({"run_state_path": "../outside.json"})
        with self.assertRaisesRegex(TaskBundleError, "TASK_POINTER_INVALID_FIELD"):
            resolve_task_bundle(workspace)

    def test_explicit_task_dir_does_not_depend_on_active_pointer(self) -> None:
        workspace, task_dir = self.make_workspace({"status": "stale"})
        bundle = resolve_task_bundle(workspace, ".harness/tasks/task")
        self.assertEqual(task_dir.resolve(), bundle.task_dir)
        self.assertIsNone(bundle.pointer)

    def test_missing_contract_is_structural_error(self) -> None:
        workspace, task_dir = self.make_workspace()
        (task_dir / "plan-contract.json").unlink()
        with self.assertRaisesRegex(TaskBundleError, "TASK_CONTRACT_MISSING"):
            resolve_task_bundle(workspace)

    def test_task_path_cannot_escape_workspace(self) -> None:
        workspace, _ = self.make_workspace()
        with self.assertRaisesRegex(TaskBundleError, "TASK_PATH_OUTSIDE_WORKSPACE"):
            resolve_task_bundle(workspace, "..")


class StateReducerTest(unittest.TestCase):
    def event(
        self,
        seq: int,
        event_type: str,
        *,
        stage_id: str | None = None,
        attempt: int | None = None,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return build_event(
            contract(),
            seq,
            event_type,
            stage_id=stage_id,
            attempt=attempt,
            payload=payload,
            occurred_at=f"2026-07-10T00:00:{seq:02d}+00:00",
        )

    def completed_events(self) -> list[dict[str, object]]:
        return [
            self.event(1, "execution_started"),
            self.event(2, "stage_started", stage_id="STG-01", attempt=1),
            self.event(
                3,
                "validation_recorded",
                stage_id="STG-01",
                payload={
                    "validation_id": "VAL-01",
                    "result": "passed",
                    "summary": "unit test passed",
                },
            ),
            self.event(
                4,
                "review_recorded",
                stage_id="STG-01",
                payload={
                    "result": "passed",
                    "summary": "review passed",
                    "development_quality": "passed",
                },
            ),
            self.event(5, "stage_completed", stage_id="STG-01"),
            self.event(6, "completed"),
        ]

    def test_replay_reaches_completed(self) -> None:
        result = replay_events(contract(), self.completed_events())
        self.assertEqual("completed", result.state["lifecycle"])
        self.assertEqual(["STG-01"], result.state["completed_stage_ids"])
        self.assertEqual(6, result.state["last_event_seq"])

    def test_terminal_state_rejects_later_events(self) -> None:
        events = self.completed_events()
        events.append(self.event(7, "heartbeat"))
        with self.assertRaisesRegex(StateError, "RUN_STATE_TERMINAL"):
            replay_events(contract(), events)

    def test_optional_validation_does_not_block_stage_completion(self) -> None:
        optional_contract = contract()
        optional_contract["stages"][0]["validation_ids"].append("VAL-02")
        optional_contract["validations"].append(
            {"id": "VAL-02", "required": False}
        )
        result = replay_events(optional_contract, self.completed_events())
        self.assertEqual("completed", result.state["lifecycle"])

    def test_stage_completion_requires_review(self) -> None:
        events = self.completed_events()
        del events[3]
        for seq, event in enumerate(events, start=1):
            event["seq"] = seq
            event["event_id"] = f"EVT-{seq:06d}"
        with self.assertRaisesRegex(StateError, "RUN_STATE_REVIEW_INCOMPLETE"):
            replay_events(contract(), events)

    def test_failed_validation_revokes_prior_pass_and_review(self) -> None:
        events = self.completed_events()[:4]
        events.extend(
            [
                self.event(
                    5,
                    "validation_recorded",
                    stage_id="STG-01",
                    payload={
                        "validation_id": "VAL-01",
                        "result": "failed",
                        "reason": "regression",
                    },
                ),
                self.event(6, "stage_completed", stage_id="STG-01"),
            ]
        )
        with self.assertRaisesRegex(StateError, "RUN_STATE_VALIDATION_INCOMPLETE"):
            replay_events(contract(), events)

    def test_failed_review_revokes_prior_review(self) -> None:
        events = self.completed_events()[:4]
        events.extend(
            [
                self.event(
                    5,
                    "review_recorded",
                    stage_id="STG-01",
                    payload={"result": "failed", "finding": "blocking issue"},
                ),
                self.event(6, "stage_completed", stage_id="STG-01"),
            ]
        )
        with self.assertRaisesRegex(StateError, "RUN_STATE_REVIEW_INCOMPLETE"):
            replay_events(contract(), events)

    def test_passed_validation_requires_summary(self) -> None:
        events = self.completed_events()
        events[2]["payload"].pop("summary")
        with self.assertRaisesRegex(StateError, "RUN_STATE_EVENT_EVIDENCE_INVALID"):
            replay_events(contract(), events)

    def test_passed_review_requires_development_quality(self) -> None:
        events = self.completed_events()
        events[3]["payload"].pop("development_quality")
        with self.assertRaisesRegex(
            StateError,
            "RUN_STATE_DEVELOPMENT_QUALITY_INCOMPLETE",
        ):
            replay_events(contract(), events)

    def test_attempt_failure_requires_reason_impact_and_next_strategy(self) -> None:
        events = [
            self.event(1, "execution_started"),
            self.event(2, "stage_started", stage_id="STG-01", attempt=1),
            self.event(
                3,
                "attempt_failed",
                stage_id="STG-01",
                attempt=1,
                payload={"reason": "command failed"},
            ),
        ]
        with self.assertRaisesRegex(StateError, "RUN_STATE_EVENT_EVIDENCE_INVALID"):
            replay_events(contract(), events)

    def test_sequence_gap_is_rejected(self) -> None:
        events = [self.event(2, "execution_started")]
        with self.assertRaisesRegex(StateError, "LEDGER_SEQUENCE_GAP"):
            replay_events(contract(), events)

    def test_event_timestamp_requires_rfc3339_separator(self) -> None:
        event = self.event(1, "execution_started")
        event["occurred_at"] = "2026-07-10 00:00:01+00:00"
        with self.assertRaisesRegex(StateError, "LEDGER_INVALID_TIMESTAMP"):
            replay_events(contract(), [event])

    def test_snapshot_atomic_write_and_drift(self) -> None:
        result = replay_events(contract(), self.completed_events())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "run-state.json"
            write_state_atomic(path, result.state)
            snapshot = load_state(path)
            self.assertEqual({}, state_differences(snapshot, result.state))
            assert snapshot is not None
            snapshot["last_event_seq"] = 5
            self.assertIn("last_event_seq", state_differences(snapshot, result.state))

    def test_read_events_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaisesRegex(StateError, "LEDGER_INVALID_JSON"):
                read_events(path)


if __name__ == "__main__":
    unittest.main()
