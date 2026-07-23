from __future__ import annotations

import ctypes
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
    CancellationState,
    EXIT_CANCELLED,
    EXIT_CLEANUP_FAILED,
    PosixGroupTracker,
    PosixInspectionError,
    PosixProcessIdentity,
    StatusReporter,
    WindowsJobState,
    _force_kill_windows_pids,
    _posix_group_pids,
    _posix_process_identity,
    _terminate_posix_group,
    _terminate_windows_tree,
    _wait_for_terminal,
    cleanup_completed_process_tree,
    run_bounded_command,
)


class BoundedCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def cli_arguments(
        self,
        *command: str,
        timeout_seconds: str = "5",
        grace_seconds: str = "1",
        heartbeat_seconds: str = "15",
        inherit_stdin: bool = False,
    ) -> list[str]:
        arguments = [
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
            "--heartbeat-seconds",
            heartbeat_seconds,
        ]
        if inherit_stdin:
            arguments.append("--inherit-stdin")
        arguments.extend(["--", *command])
        return arguments

    def run_cli(
        self,
        *command: str,
        timeout_seconds: str = "5",
        grace_seconds: str = "1",
        heartbeat_seconds: str = "15",
        inherit_stdin: bool = False,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.cli_arguments(
                *command,
                timeout_seconds=timeout_seconds,
                grace_seconds=grace_seconds,
                heartbeat_seconds=heartbeat_seconds,
                inherit_stdin=inherit_stdin,
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=input_text,
            timeout=25,
        )

    def test_success_streams_output_and_human_summary(self) -> None:
        completed = self.run_cli(sys.executable, "-c", "print('bounded-output')")
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("bounded-output", completed.stdout)
        self.assertIn("bounded-command: starting", completed.stderr)
        self.assertIn("bounded-command: started, pid=", completed.stderr)
        self.assertIn("bounded-command: completed", completed.stderr)
        self.assertIn("cleanup=verified", completed.stderr)
        self.assertFalse(list(self.root.rglob("*.json")))

    def test_silent_command_emits_heartbeat_before_completion(self) -> None:
        completed = self.run_cli(
            sys.executable,
            "-c",
            "import time; time.sleep(1.2)",
            timeout_seconds="3",
            heartbeat_seconds="1",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        heartbeat = completed.stderr.index("bounded-command: heartbeat")
        completion = completed.stderr.index("bounded-command: completed")
        self.assertLess(heartbeat, completion)
        self.assertIn("remaining=", completed.stderr)

    def test_default_stdin_is_non_interactive(self) -> None:
        completed = self.run_cli(
            sys.executable,
            "-c",
            "import sys; print(len(sys.stdin.read()))",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("0", completed.stdout.strip())

    def test_inherited_stdin_is_explicit(self) -> None:
        completed = self.run_cli(
            sys.executable,
            "-c",
            "import sys; print(sys.stdin.read())",
            inherit_stdin=True,
            input_text="explicit-input",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("explicit-input", completed.stdout.strip())

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

    def test_invalid_heartbeat_is_rejected_before_launch(self) -> None:
        for value in ("0", "nan", "301"):
            with self.subTest(value=value):
                completed = self.run_cli(
                    sys.executable,
                    "--version",
                    heartbeat_seconds=value,
                )
                self.assertEqual(2, completed.returncode)
                self.assertIn("--heartbeat-seconds", completed.stderr)

    def test_closed_status_stream_does_not_change_execution(self) -> None:
        reporter = StatusReporter()
        with mock.patch(
            "harness_bounded_command.print",
            side_effect=BrokenPipeError,
            create=True,
        ) as status_print:
            reporter.emit("first")
            reporter.emit("second")
        self.assertFalse(reporter.enabled)
        status_print.assert_called_once()

    def test_status_output_does_not_echo_command_arguments(self) -> None:
        marker = "bounded-secret-argument"
        completed = self.run_cli(
            sys.executable,
            "-c",
            "import sys",
            marker,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertNotIn(marker, completed.stderr)

    def test_cancellation_before_deadline_wins_terminal_race(self) -> None:
        process = mock.Mock(pid=43210)
        process.poll.return_value = None
        cancellation = CancellationState(
            reason="sigterm",
            requested_at=5.0,
        )
        with mock.patch(
            "harness_bounded_command.time.monotonic",
            return_value=11.0,
        ):
            terminal, exit_code = _wait_for_terminal(
                process,
                started_monotonic=0.0,
                timeout_seconds=10.0,
                heartbeat_seconds=1.0,
                reporter=None,
                cancellation=cancellation,
            )
        self.assertEqual("cancelled", terminal)
        self.assertIsNone(exit_code)

    def test_deadline_before_cancellation_wins_terminal_race(self) -> None:
        process = mock.Mock(pid=43210)
        process.poll.return_value = None
        cancellation = CancellationState(
            reason="sigterm",
            requested_at=11.0,
        )
        with mock.patch(
            "harness_bounded_command.time.monotonic",
            return_value=11.0,
        ):
            terminal, exit_code = _wait_for_terminal(
                process,
                started_monotonic=0.0,
                timeout_seconds=10.0,
                heartbeat_seconds=1.0,
                reporter=None,
                cancellation=cancellation,
            )
        self.assertEqual("timeout", terminal)
        self.assertIsNone(exit_code)

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
        terminate.assert_called_once_with(process, 0.1, None, None)

    def test_cleanup_failure_returns_stable_exit_and_pids(self) -> None:
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
            mock.patch("harness_bounded_command._create_windows_job", return_value=None),
            mock.patch(
                "harness_bounded_command._wait_for_terminal",
                return_value=("timeout", None),
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
        self.assertEqual([43210, 43211], result["cleanup_failure_pids"])

    def test_keyboard_interrupt_is_bounded(self) -> None:
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
            mock.patch("harness_bounded_command._create_windows_job", return_value=None),
            mock.patch(
                "harness_bounded_command._wait_for_terminal",
                return_value=("cancelled", None),
            ),
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

    @unittest.skipUnless(os.name == "nt", "仅 Windows 验证原生 Job fallback")
    def test_windows_no_console_fallback_reclaims_child(self) -> None:
        pid_file = self.root / "no-console-child.pid"
        child_code = (
            "import pathlib,subprocess,sys,time;"
            "child=subprocess.Popen([sys.executable,'-c',"
            "'import time; time.sleep(60)']);"
            "pathlib.Path(sys.argv[1]).write_text("
            "str(child.pid),encoding='utf-8');"
            "time.sleep(60)"
        )
        completed = subprocess.run(
            self.cli_arguments(
                sys.executable,
                "-c",
                child_code,
                str(pid_file),
                timeout_seconds="2",
                grace_seconds="1",
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=20,
        )
        self.assertEqual(124, completed.returncode, completed.stderr)
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        self.addCleanup(self._force_stop, child_pid)
        self.assertFalse(self._is_running(child_pid))

    @unittest.skipUnless(os.name == "nt", "仅 Windows 验证原生 CTRL_BREAK")
    def test_windows_ctrl_break_cancels_and_reclaims_child(self) -> None:
        pid_file = self.root / "ctrl-break-child.pid"
        child_code = (
            "import pathlib,subprocess,sys,time;"
            "child=subprocess.Popen([sys.executable,'-c',"
            "'import time; time.sleep(60)']);"
            "pathlib.Path(sys.argv[1]).write_text("
            "str(child.pid),encoding='utf-8');"
            "time.sleep(60)"
        )
        wrapper = subprocess.Popen(
            self.cli_arguments(
                sys.executable,
                "-c",
                child_code,
                str(pid_file),
                timeout_seconds="10",
                grace_seconds="1",
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.addCleanup(self._force_stop, wrapper.pid)
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(pid_file.exists())
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        self.addCleanup(self._force_stop, child_pid)
        wrapper.send_signal(signal.CTRL_BREAK_EVENT)
        _, stderr = wrapper.communicate(timeout=15)
        self.assertEqual(130, wrapper.returncode, stderr)
        self.assertIn("bounded-command: cancelled", stderr)
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

    def test_windows_break_failure_falls_back_to_job_without_grace_wait(
        self,
    ) -> None:
        process = mock.Mock(pid=43210)
        process.send_signal.side_effect = OSError("no console")
        tracked = {43210: "root-handle"}
        with (
            mock.patch(
                "harness_bounded_command._windows_descendant_pids",
                return_value=[],
            ),
            mock.patch(
                "harness_bounded_command._track_windows_processes",
                return_value=tracked,
            ),
            mock.patch(
                "harness_bounded_command._windows_handle_running",
                return_value=True,
            ),
            mock.patch(
                "harness_bounded_command._wait_until_stopped",
                return_value=[],
            ) as wait,
            mock.patch(
                "harness_bounded_command._close_windows_job",
                return_value=True,
            ) as close_job,
            mock.patch(
                "harness_bounded_command._close_windows_process_handles"
            ),
            mock.patch.object(
                signal,
                "CTRL_BREAK_EVENT",
                1,
                create=True,
            ),
        ):
            cleaned, remaining = _terminate_windows_tree(
                process,
                30.0,
                WindowsJobState("job-handle", {}),
            )
        self.assertTrue(cleaned)
        self.assertEqual([], remaining)
        close_job.assert_called_once()
        wait.assert_called_once()

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

    @unittest.skipIf(os.name == "nt", "POSIX 信号仅在 Ubuntu/macOS 执行")
    def test_posix_sigterm_and_sighup_cancel_and_reclaim_child(self) -> None:
        for sent_signal in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(sent_signal=sent_signal):
                pid_file = self.root / f"child-{sent_signal}.pid"
                child_code = (
                    "import pathlib,subprocess,sys,time;"
                    "child=subprocess.Popen([sys.executable,'-c',"
                    "'import time; time.sleep(60)']);"
                    "pathlib.Path(sys.argv[1]).write_text("
                    "str(child.pid),encoding='utf-8');"
                    "time.sleep(60)"
                )
                wrapper = subprocess.Popen(
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
                        "30",
                        "--grace-seconds",
                        "1",
                        "--heartbeat-seconds",
                        "1",
                        "--",
                        sys.executable,
                        "-c",
                        child_code,
                        str(pid_file),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                self.addCleanup(self._force_stop, wrapper.pid)
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pid_file.exists())
                child_pid = int(pid_file.read_text(encoding="utf-8"))
                self.addCleanup(self._force_stop, child_pid)
                os.kill(wrapper.pid, sent_signal)
                _, stderr = wrapper.communicate(timeout=15)
                self.assertEqual(130, wrapper.returncode, stderr)
                self.assertIn("bounded-command: cancelled", stderr)
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


class PosixTrackingTest(unittest.TestCase):
    @staticmethod
    def identity(
        pid: int,
        start_time: str,
        process_group_id: int = 100,
        session_id: int = 100,
    ) -> PosixProcessIdentity:
        return PosixProcessIdentity(
            pid=pid,
            start_time=start_time,
            process_group_id=process_group_id,
            session_id=session_id,
        )

    def test_tracker_accepts_later_member_in_same_session(self) -> None:
        root = self.identity(100, "root")
        child = self.identity(101, "child")
        tracker = PosixGroupTracker(100, 100, {100: root})
        with (
            mock.patch(
                "harness_bounded_command._posix_group_pids",
                return_value=[100, 101],
            ),
            mock.patch(
                "harness_bounded_command._posix_process_identity",
                side_effect=[root, child],
            ),
        ):
            self.assertEqual([100, 101], tracker.inspect(time.monotonic() + 1))
        self.assertEqual(child, tracker.members[101])

    def test_tracker_rejects_reused_pid_identity(self) -> None:
        root = self.identity(100, "root")
        tracker = PosixGroupTracker(100, 100, {100: root})
        with (
            mock.patch(
                "harness_bounded_command._posix_group_pids",
                return_value=[100],
            ),
            mock.patch(
                "harness_bounded_command._posix_process_identity",
                return_value=self.identity(100, "reused"),
            ),
            self.assertRaises(PosixInspectionError),
        ):
            tracker.inspect(time.monotonic() + 1)

    def test_tracker_never_reopens_observed_empty_group(self) -> None:
        root = self.identity(100, "root")
        tracker = PosixGroupTracker(100, 100, {100: root})
        with mock.patch(
            "harness_bounded_command._posix_group_pids",
            side_effect=[[], [100]],
        ):
            self.assertEqual([], tracker.inspect(time.monotonic() + 1))
            with self.assertRaises(PosixInspectionError):
                tracker.inspect(time.monotonic() + 1)

    def test_tracker_tolerates_member_exit_between_queries(self) -> None:
        root = self.identity(100, "root")
        tracker = PosixGroupTracker(100, 100, {100: root})
        with (
            mock.patch(
                "harness_bounded_command._posix_group_pids",
                side_effect=[[100, 101], [100], [100]],
            ),
            mock.patch(
                "harness_bounded_command._posix_process_identity",
                side_effect=[root, PosixInspectionError("exited"), root],
            ),
        ):
            self.assertEqual([100], tracker.inspect(time.monotonic() + 1))

    def test_group_query_refuses_exhausted_cleanup_budget(self) -> None:
        with (
            mock.patch(
                "harness_bounded_command.time.monotonic",
                return_value=10.0,
            ),
            mock.patch(
                "harness_bounded_command.subprocess.run"
            ) as query,
            self.assertRaises(PosixInspectionError),
        ):
            _posix_group_pids(100, 10.0)
        query.assert_not_called()

    def test_group_query_timeout_fails_closed(self) -> None:
        with (
            mock.patch(
                "harness_bounded_command.time.monotonic",
                return_value=10.0,
            ),
            mock.patch(
                "harness_bounded_command.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["ps"], 0.5),
            ) as query,
            self.assertRaises(PosixInspectionError),
        ):
            _posix_group_pids(100, 10.5)
        self.assertEqual(0.5, query.call_args.kwargs["timeout"])

    def test_identity_failure_still_stops_exact_root_process(self) -> None:
        process = mock.Mock(pid=100)
        process.poll.return_value = None
        process.wait.return_value = 0
        with mock.patch(
            "harness_bounded_command._create_posix_tracker",
            side_effect=PosixInspectionError("identity unavailable"),
        ):
            cleaned, remaining = _terminate_posix_group(process, 0.5)
        self.assertFalse(cleaned)
        self.assertEqual([], remaining)
        process.terminate.assert_called_once()
        process.kill.assert_not_called()

    def test_linux_identity_uses_start_time_group_and_session(self) -> None:
        fields = ["S", "1", "100", "100", *(["0"] * 15), "987654"]
        stat = f"100 (python worker) {' '.join(fields)}"
        with (
            mock.patch("harness_bounded_command.sys.platform", "linux"),
            mock.patch(
                "harness_bounded_command.Path.read_text",
                return_value=stat,
            ),
        ):
            identity = _posix_process_identity(100)
        self.assertEqual(self.identity(100, "987654"), identity)

    def test_macos_identity_uses_microsecond_start_time(self) -> None:
        library = mock.Mock()

        def fill_info(
            pid: int,
            _flavor: int,
            _arg: int,
            pointer: object,
            size: int,
        ) -> int:
            from harness_bounded_command import _MacProcBsdInfo

            info = ctypes.cast(
                pointer,
                ctypes.POINTER(_MacProcBsdInfo),
            ).contents
            info.pbi_pid = pid
            info.pbi_pgid = 100
            info.pbi_start_tvsec = 1720607230
            info.pbi_start_tvusec = 456789
            return size

        library.proc_pidinfo.side_effect = fill_info
        with (
            mock.patch("harness_bounded_command.sys.platform", "darwin"),
            mock.patch(
                "harness_bounded_command.ctypes.CDLL",
                return_value=library,
            ),
            mock.patch(
                "harness_bounded_command.os.getsid",
                return_value=100,
                create=True,
            ),
        ):
            identity = _posix_process_identity(100)
        self.assertEqual(
            self.identity(100, "1720607230456789"),
            identity,
        )


if __name__ == "__main__":
    unittest.main()
