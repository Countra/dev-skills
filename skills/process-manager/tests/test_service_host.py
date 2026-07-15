from __future__ import annotations

import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from process_manager.service_host import (  # noqa: E402
    TargetController,
    WindowsConsole,
    _group_remaining_after_target,
    _log_pumps_timed_out,
    _pump,
)


class FakeKernel32:
    def __init__(self, *, attached: bool) -> None:
        self.attached = attached
        self.allocations = 0
        self.releases = 0

    def GetConsoleProcessList(self, process_ids, count):  # noqa: ANN001,ANN201,N802
        del process_ids, count
        return 1 if self.attached else 0

    def AllocConsole(self):  # noqa: ANN201,N802
        self.allocations += 1
        self.attached = True
        return 1

    def GetConsoleWindow(self):  # noqa: ANN201,N802
        return 0

    def FreeConsole(self):  # noqa: ANN201,N802
        self.releases += 1
        return 1


class RecordingDestination:
    def __init__(self) -> None:
        self.data = bytearray()
        self.written = threading.Event()

    def write(self, data: bytes) -> None:
        self.data.extend(data)
        if data:
            self.written.set()

    def close(self) -> None:
        return


class FailingDestination(RecordingDestination):
    def write(self, data: bytes) -> None:
        del data
        raise OSError(28, "disk full")


class WindowsConsoleTests(unittest.TestCase):
    def test_pipe_pump_flushes_short_output_before_eof(self) -> None:
        read_fd, write_fd = os.pipe()
        source = os.fdopen(read_fd, "rb")
        destination = RecordingDestination()
        pump = threading.Thread(target=_pump, args=(source, destination, ["a-very-long-secret-value"]))
        pump.start()
        try:
            os.write(write_fd, b"service-ready\n")
            self.assertTrue(destination.written.wait(2))
            self.assertEqual(bytes(destination.data), b"service-ready\n")
        finally:
            os.close(write_fd)
            pump.join(timeout=2)
        self.assertFalse(pump.is_alive())

    def test_pipe_pump_drains_source_and_records_log_failure(self) -> None:
        read_fd, write_fd = os.pipe()
        source = os.fdopen(read_fd, "rb")
        failures: list[dict[str, object]] = []
        pump = threading.Thread(
            target=_pump,
            args=(source, FailingDestination(), [], failures, "stdout"),
        )
        pump.start()
        try:
            os.write(write_fd, b"x" * 65536)
        finally:
            os.close(write_fd)
            pump.join(timeout=2)
        self.assertFalse(pump.is_alive())
        self.assertEqual(
            failures,
            [{"stream": "stdout", "errorType": "OSError", "errno": 28, "winerror": None}],
        )

    def test_reuses_existing_console_without_releasing_it(self) -> None:
        kernel32 = FakeKernel32(attached=True)
        with (
            mock.patch("process_manager.service_host._windows_console_supported", return_value=True),
            mock.patch("process_manager.service_host.ctypes.WinDLL", return_value=kernel32, create=True),
        ):
            console = WindowsConsole()
            console.prepare()
            console.close()
        self.assertEqual(kernel32.allocations, 0)
        self.assertEqual(kernel32.releases, 0)

    def test_allocates_and_releases_private_console(self) -> None:
        kernel32 = FakeKernel32(attached=False)
        with (
            mock.patch("process_manager.service_host._windows_console_supported", return_value=True),
            mock.patch("process_manager.service_host.ctypes.WinDLL", return_value=kernel32, create=True),
        ):
            console = WindowsConsole()
            console.prepare()
            console.close()
        self.assertEqual(kernel32.allocations, 1)
        self.assertEqual(kernel32.releases, 1)


class TargetControllerTests(unittest.TestCase):
    def test_log_pumps_share_one_drain_deadline(self) -> None:
        clock = [0.0]
        first = mock.Mock()
        second = mock.Mock()
        first.is_alive.return_value = True
        second.is_alive.return_value = True

        def consume_timeout(*, timeout: float) -> None:
            clock[0] += timeout

        first.join.side_effect = consume_timeout
        timed_out = _log_pumps_timed_out(
            [first, second],
            timeout=5.0,
            monotonic=lambda: clock[0],
        )

        self.assertTrue(timed_out)
        self.assertEqual(clock[0], 5.0)
        first.join.assert_called_once_with(timeout=5.0)
        second.join.assert_not_called()

    def test_process_group_settlement_tolerates_delayed_empty_observation(self) -> None:
        clock = [0.0]
        observations = iter((True, True, False))

        def sleep(delay: float) -> None:
            clock[0] += delay

        remaining = _group_remaining_after_target(
            4321,
            "cgroup-v2",
            timeout=0.1,
            is_alive=lambda pgid: next(observations),
            monotonic=lambda: clock[0],
            sleep=sleep,
        )
        self.assertFalse(remaining)
        self.assertGreater(clock[0], 0)

    def test_process_group_settlement_preserves_persistent_violation(self) -> None:
        clock = [0.0]

        def sleep(delay: float) -> None:
            clock[0] += delay

        remaining = _group_remaining_after_target(
            4321,
            "process-group",
            timeout=0.05,
            is_alive=lambda pgid: True,
            monotonic=lambda: clock[0],
            sleep=sleep,
        )
        self.assertTrue(remaining)
        self.assertGreaterEqual(clock[0], 0.05)

    def test_cgroup_host_force_only_signals_target_group(self) -> None:
        process = mock.Mock(pid=4321)
        controller = TargetController(process, "cgroup-v2", {"cgroupPath": "/sys/fs/cgroup/test"})
        with (
            mock.patch("process_manager.service_host.os.killpg", create=True) as kill_group,
            mock.patch("process_manager.service_host.signal.SIGKILL", 9, create=True),
        ):
            controller.force()
        kill_group.assert_called_once_with(4321, 9)
        process.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
