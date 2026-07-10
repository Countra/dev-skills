from __future__ import annotations

import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from process_manager.service_host import WindowsConsole, _pump  # noqa: E402


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
            mock.patch("process_manager.service_host.os.name", "nt"),
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
            mock.patch("process_manager.service_host.os.name", "nt"),
            mock.patch("process_manager.service_host.ctypes.WinDLL", return_value=kernel32, create=True),
        ):
            console = WindowsConsole()
            console.prepare()
            console.close()
        self.assertEqual(kernel32.allocations, 1)
        self.assertEqual(kernel32.releases, 1)


if __name__ == "__main__":
    unittest.main()
