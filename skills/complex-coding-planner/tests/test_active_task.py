from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_active_task import (  # noqa: E402
    ActiveTaskError,
    activate_or_switch,
    classify_active_pointer,
)


class ActiveTaskTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def write_json(self, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def task(self, task_id: str, lifecycle: str | None = None) -> Path:
        task_dir = self.workspace / ".harness" / "tasks" / task_id
        self.write_json(task_dir / "plan-contract.json", {"task_id": task_id})
        if lifecycle:
            self.write_json(
                task_dir / "run-state.json",
                {"task_id": task_id, "lifecycle": lifecycle},
            )
        return task_dir

    def point_to(self, task_dir: Path, task_id: str) -> Path:
        pointer = self.workspace / ".harness" / "active-task.json"
        self.write_json(
            pointer,
            {
                "task_id": task_id,
                "task_dir": task_dir.relative_to(self.workspace).as_posix(),
                "run_state_path": "run-state.json",
                "updated_at": "2026-07-15T00:00:00Z",
            },
        )
        return pointer

    def assert_code(self, code: str, operation: object) -> None:
        with self.assertRaises(ActiveTaskError) as raised:
            operation()
        self.assertEqual(code, raised.exception.code)

    def test_missing_is_created_and_same_task_is_reused_without_write(self) -> None:
        target = self.task("target")
        created = activate_or_switch(self.workspace, target, "activate")
        self.assertEqual(("missing", "created"), (created["state"], created["action"]))
        pointer = self.workspace / ".harness" / "active-task.json"
        before = pointer.read_bytes()
        reused = activate_or_switch(self.workspace, target, "activate")
        self.assertEqual(("same-task", "reused"), (reused["state"], reused["action"]))
        self.assertEqual(before, pointer.read_bytes())

    def test_terminal_task_is_replaced_atomically(self) -> None:
        target = self.task("target")
        terminal = self.task("terminal", "completed")
        self.point_to(terminal, "terminal")
        result = activate_or_switch(self.workspace, target, "activate")
        self.assertEqual("different-terminal", result["state"])
        pointer = json.loads(
            (self.workspace / ".harness" / "active-task.json").read_text(encoding="utf-8")
        )
        self.assertEqual("target", pointer["task_id"])

    def test_nonterminal_and_unknown_require_explicit_switch(self) -> None:
        target = self.task("target")
        active = self.task("active", "in_progress")
        self.point_to(active, "active")
        self.assert_code(
            "TASK_ACTIVE_POINTER_CONFLICT",
            lambda: activate_or_switch(self.workspace, target, "activate"),
        )
        self.assert_code(
            "TASK_ACTIVE_POINTER_SWITCH_CONFLICT",
            lambda: activate_or_switch(self.workspace, target, "switch", "changed"),
        )
        unknown = self.task("unknown")
        self.point_to(unknown, "unknown")
        self.assertEqual(
            "different-unknown",
            classify_active_pointer(self.workspace, target)["state"],
        )
        self.assert_code(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            lambda: activate_or_switch(self.workspace, target, "activate"),
        )
        switched = activate_or_switch(self.workspace, target, "switch", "unknown")
        self.assertEqual("replaced", switched["action"])

    def test_switch_always_requires_expected_current_id(self) -> None:
        target = self.task("target")
        activate_or_switch(self.workspace, target, "activate")
        self.assert_code(
            "TASK_ACTIVE_POINTER_SWITCH_EXPECTATION_REQUIRED",
            lambda: activate_or_switch(self.workspace, target, "switch"),
        )

    def test_atomic_replace_failure_keeps_existing_pointer(self) -> None:
        target = self.task("target")
        terminal = self.task("terminal", "aborted")
        pointer = self.point_to(terminal, "terminal")
        before = pointer.read_bytes()
        with mock.patch("harness_active_task.os.replace", side_effect=OSError("simulated")):
            self.assert_code(
                "TASK_ACTIVE_POINTER_WRITE_FAILED",
                lambda: activate_or_switch(self.workspace, target, "activate"),
            )
        self.assertEqual(before, pointer.read_bytes())
        self.assertEqual([], list(pointer.parent.glob(".active-task.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
