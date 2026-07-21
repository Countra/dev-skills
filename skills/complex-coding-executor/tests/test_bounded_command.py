from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import WritableTemporaryDirectory


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS_DIR / "harness_bounded_command.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_bounded_command import (  # noqa: E402
    EXIT_CLEANUP_FAILED,
    WindowsJobState,
    _terminate_windows_tree,
    cleanup_completed_process_tree,
    run_bounded_command,
)
from harness_state_errors import StateError  # noqa: E402
from harness_validation_schema import (  # noqa: E402
    validate_validation_record,
    validation_timeout_seconds,
)


def validation_payload() -> dict[str, object]:
    return {
        "validation_id": "VAL-01",
        "result": "passed",
        "command": "python -m unittest",
        "claim_source": "observed",
        "stage_attempt": 1,
        "target_digest": "a" * 64,
        "exit_code": 0,
        "summary": "unit test passed",
        "claim_boundary": "只证明当前 target 的单元测试结果。",
    }


class BoundedCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def run_cli(
        self,
        *command: str,
        timeout_seconds: str = "5",
        grace_seconds: str = "1",
        result_path: str = "artifacts/result.json",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-u",
                "-X",
                "utf8",
                "-B",
                str(SCRIPT),
                "--cwd",
                str(self.root),
                "--timeout-seconds",
                timeout_seconds,
                "--grace-seconds",
                grace_seconds,
                "--result-json",
                result_path,
                "--",
                *command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def read_result(self, relative: str = "artifacts/result.json") -> dict[str, object]:
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def test_success_inherits_output_and_writes_result(self) -> None:
        completed = self.run_cli(
            sys.executable,
            "-c",
            "print('bounded-output')",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("bounded-output", completed.stdout)
        result = self.read_result()
        self.assertEqual("passed", result["result"])
        self.assertEqual("completed", result["termination"])
        self.assertTrue(result["cleanup_verified"])

    def test_normal_failure_preserves_child_exit_code(self) -> None:
        completed = self.run_cli(
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        )
        self.assertEqual(7, completed.returncode)
        result = self.read_result()
        self.assertEqual(7, result["exit_code"])
        self.assertEqual("completed", result["termination"])

    def test_silent_timeout_is_bounded_and_cleaned(self) -> None:
        started = time.monotonic()
        completed = self.run_cli(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            timeout_seconds="0.5",
            grace_seconds="0.5",
        )
        elapsed = time.monotonic() - started
        self.assertEqual(124, completed.returncode, completed.stderr)
        self.assertLess(elapsed, 11.0)
        result = self.read_result()
        self.assertEqual("timeout", result["termination"])
        self.assertTrue(result["cleanup_verified"])
        self.assertEqual("RUN_STATE_COMMAND_TIMEOUT", result["error_code"])

    def test_missing_program_is_classified_without_command_echo(self) -> None:
        marker = "missing-program-with-secret-marker"
        completed = self.run_cli(marker)
        self.assertEqual(126, completed.returncode)
        result = self.read_result()
        self.assertEqual("launch-failed", result["termination"])
        self.assertEqual("RUN_STATE_COMMAND_LAUNCH_FAILED", result["error_code"])
        self.assertNotIn(marker, json.dumps(result, ensure_ascii=False))

    def test_result_path_cannot_escape_cwd(self) -> None:
        completed = self.run_cli(
            sys.executable,
            "-c",
            "raise SystemExit(0)",
            result_path="../outside.json",
        )
        self.assertEqual(126, completed.returncode)
        self.assertFalse((self.root.parent / "outside.json").exists())

    def test_cleanup_failure_returns_stable_exit_and_pids(self) -> None:
        process = mock.Mock()
        process.pid = 43210
        process.wait.side_effect = subprocess.TimeoutExpired(["unit"], 0.1)
        with (
            mock.patch(
                "harness_bounded_command.subprocess.Popen",
                return_value=process,
            ),
            mock.patch(
                "harness_bounded_command.terminate_process_tree",
                return_value=(False, [43211, 43210]),
            ),
        ):
            exit_code, result = run_bounded_command(
                ["unit"],
                cwd=self.root,
                timeout_seconds=0.1,
                grace_seconds=0.1,
            )
        self.assertEqual(EXIT_CLEANUP_FAILED, exit_code)
        self.assertEqual("cleanup-failed", result["termination"])
        self.assertEqual([43210, 43211], result["cleanup_failure_pids"])

    def test_windows_job_race_force_kills_tracked_escapee(self) -> None:
        process = mock.Mock(pid=43210)
        tracked = {43210: "root-handle", 43211: "child-handle"}
        with (
            mock.patch(
                "harness_bounded_command._windows_descendant_pids",
                return_value=[43211],
            ),
            mock.patch(
                "harness_bounded_command._track_windows_processes",
                return_value=tracked,
            ),
            mock.patch(
                "harness_bounded_command._wait_until_stopped",
                side_effect=[[43210, 43211], [43211], []],
            ),
            mock.patch(
                "harness_bounded_command._close_windows_job",
                return_value=True,
            ),
            mock.patch(
                "harness_bounded_command._force_kill_windows_pids"
            ) as force_kill,
            mock.patch(
                "harness_bounded_command._close_windows_process_handles"
            ) as close_handles,
        ):
            cleaned, remaining = _terminate_windows_tree(
                process,
                0.1,
                WindowsJobState(object(), {}),
            )
        self.assertTrue(cleaned)
        self.assertEqual([], remaining)
        force_kill.assert_called_once_with({43211: "child-handle"}, 5.0)
        close_handles.assert_called_once_with(tracked)

    def test_completed_windows_job_does_not_rescan_reused_root_pid(self) -> None:
        process = mock.Mock(pid=43210)
        job = WindowsJobState("job-handle", {})
        with (
            mock.patch("harness_bounded_command.os.name", "nt"),
            mock.patch(
                "harness_bounded_command._windows_descendant_pids"
            ) as descendants,
            mock.patch(
                "harness_bounded_command._close_windows_job",
                return_value=True,
            ),
            mock.patch(
                "harness_bounded_command._wait_until_stopped",
                return_value=[],
            ),
            mock.patch(
                "harness_bounded_command._close_windows_process_handles"
            ),
        ):
            cleaned, remaining = cleanup_completed_process_tree(process, 0.1, job)
        self.assertTrue(cleaned)
        self.assertEqual([], remaining)
        descendants.assert_not_called()

    def test_timeout_reclaims_spawned_child(self) -> None:
        pid_file = self.root / "child.pid"
        child_code = (
            "import pathlib,subprocess,sys,time;"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']);"
            "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='utf-8');"
            "time.sleep(60)"
        )
        completed = self.run_cli(
            sys.executable,
            "-c",
            child_code,
            str(pid_file),
            timeout_seconds="2",
            grace_seconds="1",
        )
        self.assertEqual(124, completed.returncode, completed.stderr)
        self.assertTrue(pid_file.is_file())
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        self.addCleanup(self._force_stop, child_pid)
        deadline = time.monotonic() + 3
        while self._is_running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self._is_running(child_pid))

    def test_normal_parent_exit_does_not_leave_child(self) -> None:
        pid_file = self.root / "detached-child.pid"
        child_code = (
            "import pathlib,subprocess,sys;"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']);"
            "pathlib.Path(sys.argv[1]).write_text(str(child.pid),encoding='utf-8')"
        )
        completed = self.run_cli(
            sys.executable,
            "-c",
            child_code,
            str(pid_file),
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        self.addCleanup(self._force_stop, child_pid)
        self.assertFalse(self._is_running(child_pid))

    @staticmethod
    def _is_running(pid: int) -> bool:
        if os.name == "nt":
            from harness_bounded_command import _windows_process_running

            return _windows_process_running(pid)
        completed = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        state = completed.stdout.strip()
        return completed.returncode == 0 and bool(state) and not state.startswith("Z")

    @staticmethod
    def _force_stop(pid: int) -> None:
        if not BoundedCommandTest._is_running(pid):
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class ValidationMetadataTest(unittest.TestCase):
    def test_old_payload_and_new_metadata_are_both_valid(self) -> None:
        old = validation_payload()
        self.assertEqual("passed", validate_validation_record(old, attempt=1)["result"])
        current = {
            **old,
            "duration_ms": 123,
            "termination": "completed",
            "cleanup_verified": True,
        }
        self.assertEqual(
            "completed",
            validate_validation_record(current, attempt=1)["termination"],
        )

    def test_timeout_metadata_requires_stable_exit_code(self) -> None:
        payload = {
            **validation_payload(),
            "result": "failed",
            "exit_code": 1,
            "termination": "timeout",
            "cleanup_verified": True,
        }
        with self.assertRaisesRegex(StateError, "RUN_STATE_VALIDATION_EXIT_INVALID"):
            validate_validation_record(payload, attempt=1)
        payload["exit_code"] = 124
        self.assertEqual(
            "timeout",
            validate_validation_record(payload, attempt=1)["termination"],
        )

    def test_cleanup_failure_must_be_explicit(self) -> None:
        payload = {
            **validation_payload(),
            "result": "failed",
            "exit_code": 125,
            "termination": "cleanup-failed",
            "cleanup_verified": True,
        }
        with self.assertRaisesRegex(
            StateError,
            "RUN_STATE_VALIDATION_PROVENANCE_INVALID",
        ):
            validate_validation_record(payload, attempt=1)

    def test_timeout_defaults_preserve_old_contracts(self) -> None:
        self.assertEqual(300, validation_timeout_seconds({"kind": "test"}))
        self.assertEqual(300, validation_timeout_seconds({"kind": "lint"}))
        self.assertEqual(900, validation_timeout_seconds({"kind": "build"}))
        self.assertEqual(900, validation_timeout_seconds({"id": "VAL-OLD"}))
        self.assertEqual(
            42,
            validation_timeout_seconds({"kind": "test", "timeout_seconds": 42}),
        )


if __name__ == "__main__":
    unittest.main()
