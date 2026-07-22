from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import WritableTemporaryDirectory, compact_contract, write_bundle, write_json


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from harness_active_task import (  # noqa: E402
    ActiveTaskError,
    _write_atomic,
    activate,
    classify,
    clear,
)


class ActiveTaskTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()

    def task_dir(self, name: str) -> Path:
        return self.workspace / ".harness" / "tasks" / "2026-07-22" / "feature" / name

    def test_missing_pointer_reports_none(self) -> None:
        self.assertEqual("none", classify(self.workspace)["status"])

    def test_atomic_pointer_setup_failure_uses_stable_error(self) -> None:
        with mock.patch(
            "harness_active_task.tempfile.mkstemp",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(ActiveTaskError) as raised:
                _write_atomic(
                    self.workspace / ".harness" / "active-task.json",
                    {"task_id": "one"},
                )
        self.assertEqual("ACTIVE_TASK_WRITE_FAILED", raised.exception.code)

    def test_activate_writes_only_compact_pointer(self) -> None:
        task_dir = self.task_dir("one")
        write_bundle(task_dir, compact_contract(task_id="one"))
        result = activate(
            self.workspace,
            str(task_dir),
            allow_switch=False,
            expected_task_id=None,
        )
        self.assertEqual("planning", result["task"]["lifecycle"])
        pointer = json.loads(
            (self.workspace / ".harness" / "active-task.json").read_text(encoding="utf-8")
        )
        self.assertEqual({"task_id", "task_dir", "updated_at"}, set(pointer))

    def test_switch_requires_current_identity(self) -> None:
        first = self.task_dir("first")
        second = self.task_dir("second")
        write_bundle(first, compact_contract(task_id="first"))
        write_bundle(second, compact_contract(task_id="second"))
        activate(self.workspace, str(first), allow_switch=False, expected_task_id=None)
        with self.assertRaisesRegex(ActiveTaskError, "--switch"):
            activate(self.workspace, str(second), allow_switch=False, expected_task_id=None)
        with self.assertRaisesRegex(ActiveTaskError, "expect-task-id"):
            activate(self.workspace, str(second), allow_switch=True, expected_task_id="other")
        result = activate(
            self.workspace,
            str(second),
            allow_switch=True,
            expected_task_id="first",
        )
        self.assertEqual("second", result["task"]["task_id"])

    def test_same_task_id_in_different_directory_still_requires_switch(self) -> None:
        first = self.task_dir("first-location")
        second = self.task_dir("second-location")
        write_bundle(first, compact_contract(task_id="shared-id"))
        write_bundle(second, compact_contract(task_id="shared-id"))
        activate(self.workspace, str(first), allow_switch=False, expected_task_id=None)
        with self.assertRaisesRegex(ActiveTaskError, "--switch"):
            activate(
                self.workspace,
                str(second),
                allow_switch=False,
                expected_task_id=None,
            )
        result = activate(
            self.workspace,
            str(second),
            allow_switch=True,
            expected_task_id="shared-id",
        )
        self.assertEqual(second, self.workspace / result["task"]["task_dir"])

    def test_pointer_escape_fails_closed(self) -> None:
        write_json(
            self.workspace / ".harness" / "active-task.json",
            {"task_id": "bad", "task_dir": "../outside", "updated_at": "now"},
        )
        result = classify(self.workspace)
        self.assertEqual("invalid", result["status"])
        self.assertEqual("ACTIVE_TASK_PATH_INVALID", result["error"]["code"])

    def test_pointer_requires_timestamp(self) -> None:
        write_json(
            self.workspace / ".harness" / "active-task.json",
            {"task_id": "bad", "task_dir": ".harness/tasks/bad", "updated_at": None},
        )
        result = classify(self.workspace)
        self.assertEqual("invalid", result["status"])
        self.assertEqual("ACTIVE_TASK_POINTER_INVALID", result["error"]["code"])

    def test_clear_repairs_invalid_pointer_without_deleting_task_data(self) -> None:
        pointer = self.workspace / ".harness" / "active-task.json"
        write_json(
            pointer,
            {"task_id": "bad", "task_dir": "../outside", "updated_at": "now"},
        )
        with self.assertRaises(ActiveTaskError):
            clear(self.workspace, "other")
        self.assertTrue(pointer.exists())
        result = clear(self.workspace, "bad")
        self.assertEqual("cleared", result["status"])
        self.assertFalse(pointer.exists())

    def test_state_controls_lifecycle(self) -> None:
        task_dir = self.task_dir("stateful")
        write_bundle(task_dir, compact_contract(task_id="stateful"))
        activate(self.workspace, str(task_dir), allow_switch=False, expected_task_id=None)
        write_json(task_dir / "run-state.json", {"task_id": "stateful", "lifecycle": "blocked"})
        self.assertEqual("blocked", classify(self.workspace)["task"]["lifecycle"])

    def test_clear_can_guard_expected_task(self) -> None:
        task_dir = self.task_dir("clear")
        write_bundle(task_dir, compact_contract(task_id="clear"))
        activate(self.workspace, str(task_dir), allow_switch=False, expected_task_id=None)
        with self.assertRaises(ActiveTaskError):
            clear(self.workspace, "wrong")
        self.assertEqual("cleared", clear(self.workspace, "clear")["status"])
        self.assertEqual("none", classify(self.workspace)["status"])


if __name__ == "__main__":
    unittest.main()
