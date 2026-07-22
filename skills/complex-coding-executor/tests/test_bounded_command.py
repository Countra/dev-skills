from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import WritableTemporaryDirectory


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "harness_bounded_command.py"
sys.path.insert(0, str(SCRIPTS))

from harness_bounded_command import (  # noqa: E402
    EXIT_CANCELLED,
    EXIT_CLEANUP_FAILED,
    WindowsJobState,
    _force_kill_windows_pids,
    _terminate_windows_tree,
    cleanup_completed_process_tree,
    run_bounded_command,
)


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
                "--",
                *command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=25,
        )

    def test_success_streams_output_and_human_summary(self) -> None:
        completed = self.run_cli(sys.executable, "-c", "print('bounded-output')")
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("bounded-output", completed.stdout)
        self.assertIn("bounded-command: completed", completed.stderr)
        self.assertIn("cleanup=verified", completed.stderr)
        self.assertFalse(list(self.root.rglob("*.json")))

    def test_normal_failure_preserves_child_exit_code(self) -> None:
        completed = self.run_cli(sys.executable, "-c", "raise SystemExit(7)")
        self.assertEqual(7, completed.returncode)
        self.assertIn("exit=7", completed.stderr)

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
        self.assertLess(elapsed, 12.5)
        self.assertIn("bounded-command: timeout", completed.stderr)
        self.assertIn("cleanup=verified", completed.stderr)

    def test_missing_program_is_classified_without_echoing_argument(self) -> None:
        marker = "missing-program-with-secret-marker"
        completed = self.run_cli(marker)
        self.assertEqual(126, completed.returncode)
        self.assertNotIn(marker, completed.stderr)
        self.assertIn("launch-failed", completed.stderr)

    def test_non_finite_deadline_is_rejected_before_launch(self) -> None:
        for value in ("nan", "inf"):
            with self.subTest(value=value):
                completed = self.run_cli(
                    sys.executable,
                    "-c",
                    "raise SystemExit(99)",
                    timeout_seconds=value,
                )
                self.assertEqual(2, completed.returncode)
                self.assertIn("必须是正数秒数", completed.stderr)

    def test_excessive_timeout_and_grace_are_rejected_before_launch(self) -> None:
        cases = (("86401", "1", "--timeout-seconds"), ("5", "301", "--grace-seconds"))
        for timeout, grace, option in cases:
            with self.subTest(option=option):
                completed = self.run_cli(
                    sys.executable,
                    "-c",
                    "raise SystemExit(99)",
                    timeout_seconds=timeout,
                    grace_seconds=grace,
                )
                self.assertEqual(2, completed.returncode)
                self.assertIn(f"{option} 不得超过", completed.stderr)

    def test_windows_job_setup_failure_reclaims_started_process(self) -> None:
        process = mock.Mock(pid=43210)
        with (
            mock.patch("harness_bounded_command.subprocess.Popen", return_value=process),
            mock.patch("harness_bounded_command.os.name", "nt"),
            mock.patch.object(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                512,
                create=True,
            ),
            mock.patch(
                "harness_bounded_command._create_windows_job",
                side_effect=RuntimeError("job setup failed"),
            ),
            mock.patch(
                "harness_bounded_command.terminate_process_tree",
                return_value=(True, []),
            ) as terminate,
        ):
            exit_code, result = run_bounded_command(
                ["unit"],
                cwd=self.root,
                timeout_seconds=1,
                grace_seconds=0.1,
            )
        self.assertEqual(126, exit_code)
        self.assertEqual("launch-failed", result["termination"])
        terminate.assert_called_once_with(process, 0.1, None)

    def test_cleanup_failure_returns_stable_exit_and_pids(self) -> None:
        process = mock.Mock(pid=43210)
        process.wait.side_effect = subprocess.TimeoutExpired(["unit"], 0.1)
        with (
            mock.patch("harness_bounded_command.subprocess.Popen", return_value=process),
            mock.patch("harness_bounded_command._create_windows_job", return_value=None),
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
        self.assertEqual([43210, 43211], result["cleanup_failure_pids"])

    def test_keyboard_interrupt_is_bounded(self) -> None:
        process = mock.Mock(pid=43210)
        process.wait.side_effect = KeyboardInterrupt
        with (
            mock.patch("harness_bounded_command.subprocess.Popen", return_value=process),
            mock.patch("harness_bounded_command._create_windows_job", return_value=None),
            mock.patch(
                "harness_bounded_command.terminate_process_tree",
                return_value=(True, []),
            ),
        ):
            exit_code, result = run_bounded_command(
                ["unit"],
                cwd=self.root,
                timeout_seconds=1,
                grace_seconds=0.1,
            )
        self.assertEqual(EXIT_CANCELLED, exit_code)
        self.assertEqual("cancelled", result["termination"])

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
        completed = self.run_cli(sys.executable, "-c", child_code, str(pid_file))
        self.assertEqual(0, completed.returncode, completed.stderr)
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        self.addCleanup(self._force_stop, child_pid)
        self.assertFalse(self._is_running(child_pid))

    def test_windows_job_race_force_kills_tracked_escapee(self) -> None:
        process = mock.Mock(pid=43210)
        tracked = {43210: "root-handle", 43211: "child-handle"}
        with (
            mock.patch("harness_bounded_command._windows_descendant_pids", return_value=[43211]),
            mock.patch("harness_bounded_command._track_windows_processes", return_value=tracked),
            mock.patch(
                "harness_bounded_command._wait_until_stopped",
                side_effect=[[43210, 43211], [43211], []],
            ),
            mock.patch("harness_bounded_command._close_windows_job", return_value=True),
            mock.patch("harness_bounded_command._force_kill_windows_pids") as force_kill,
            mock.patch("harness_bounded_command._close_windows_process_handles"),
            mock.patch.object(signal, "CTRL_BREAK_EVENT", 1, create=True),
        ):
            cleaned, remaining = _terminate_windows_tree(
                process,
                0.1,
                WindowsJobState(object(), {}),
            )
        self.assertTrue(cleaned)
        self.assertEqual([], remaining)
        force_kill.assert_called_once_with({43211: "child-handle"}, 5.0)

    def test_windows_force_kill_shares_one_deadline(self) -> None:
        tracked = {43210: "first-handle", 43211: "second-handle"}
        with (
            mock.patch("harness_bounded_command._windows_handle_running", return_value=True),
            mock.patch("harness_bounded_command.time.monotonic", side_effect=[10.0, 10.1, 15.1]),
            mock.patch(
                "harness_bounded_command.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["taskkill"], 4.9),
            ) as run,
        ):
            _force_kill_windows_pids(tracked, 5.0)
        self.assertEqual(1, run.call_count)

    def test_completed_windows_job_does_not_rescan_reused_root_pid(self) -> None:
        process = mock.Mock(pid=43210)
        job = WindowsJobState("job-handle", {})
        with (
            mock.patch("harness_bounded_command.os.name", "nt"),
            mock.patch("harness_bounded_command._windows_descendant_pids") as descendants,
            mock.patch("harness_bounded_command._close_windows_job", return_value=True),
            mock.patch("harness_bounded_command._wait_until_stopped", return_value=[]),
            mock.patch("harness_bounded_command._close_windows_process_handles"),
        ):
            cleaned, remaining = cleanup_completed_process_tree(process, 0.1, job)
        self.assertTrue(cleaned)
        self.assertEqual([], remaining)
        descendants.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
