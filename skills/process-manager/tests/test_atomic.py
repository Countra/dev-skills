from __future__ import annotations

import errno
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import workspace_directory  # noqa: E402
from process_manager.atomic import (  # noqa: E402
    WINDOWS_FILE_RETRY_DELAYS,
    _is_lock_contention_error,
    atomic_write_bytes,
    InterProcessFileLock,
)
from process_manager.errors import StateError  # noqa: E402


class AtomicWriteTests(unittest.TestCase):
    def test_lock_rejects_non_finite_timing_before_creating_file(self) -> None:
        with workspace_directory() as directory:
            lock_path = Path(directory) / "operation.lock"
            for timeout, poll_interval in (
                (float("nan"), 0.05),
                (float("inf"), 0.05),
                (1, float("nan")),
                (1, 0),
            ):
                with self.subTest(timeout=timeout, poll_interval=poll_interval), self.assertRaises(ValueError):
                    InterProcessFileLock(
                        lock_path,
                        timeout=timeout,
                        poll_interval=poll_interval,
                    )
            self.assertFalse(lock_path.exists())

    def test_lock_retry_only_accepts_known_contention_errors(self) -> None:
        contention = OSError(errno.EAGAIN, "busy")
        unknown = OSError(errno.EIO, "io failure")
        acl_denied = PermissionError(errno.EACCES, "access denied")
        acl_denied.winerror = 5
        lock_violation = PermissionError(errno.EACCES, "lock violation")
        lock_violation.winerror = 33

        self.assertTrue(_is_lock_contention_error(contention))
        self.assertTrue(_is_lock_contention_error(lock_violation))
        self.assertFalse(_is_lock_contention_error(unknown))
        self.assertFalse(_is_lock_contention_error(acl_denied))

    def test_windows_replace_retries_without_mutating_runtime_platform(self) -> None:
        with workspace_directory() as directory:
            target = Path(directory) / "state.json"
            original_replace = os.replace
            runtime_platform = os.name
            attempts = 0

            def flaky_replace(source: str | bytes, destination: str | bytes) -> None:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    error = PermissionError("sharing violation")
                    error.winerror = 32
                    raise error
                original_replace(source, destination)

            with (
                mock.patch("process_manager.atomic._windows_file_retry_enabled", return_value=True),
                mock.patch("process_manager.atomic.os.replace", new=flaky_replace),
                mock.patch("process_manager.atomic.time.sleep") as sleep,
            ):
                self.assertEqual(os.name, runtime_platform)
                atomic_write_bytes(target, b"{}\n")

            self.assertEqual(target.read_bytes(), b"{}\n")
            self.assertEqual(attempts, 3)
            self.assertEqual(sleep.call_count, 2)

    def test_windows_replace_exhaustion_remains_fail_closed(self) -> None:
        with workspace_directory() as directory:
            target = Path(directory) / "state.json"
            error = PermissionError("persistent access denied")
            error.winerror = 5
            with (
                mock.patch("process_manager.atomic._windows_file_retry_enabled", return_value=True),
                mock.patch("process_manager.atomic.os.replace", side_effect=error) as replace,
                mock.patch("process_manager.atomic.time.sleep") as sleep,
            ):
                with self.assertRaisesRegex(StateError, "原子写入失败"):
                    atomic_write_bytes(target, b"{}\n")

            self.assertEqual(replace.call_count, len(WINDOWS_FILE_RETRY_DELAYS) + 1)
            self.assertEqual(sleep.call_count, len(WINDOWS_FILE_RETRY_DELAYS))

    def test_non_windows_permission_error_is_not_retried(self) -> None:
        with workspace_directory() as directory:
            target = Path(directory) / "state.json"
            with (
                mock.patch("process_manager.atomic._windows_file_retry_enabled", return_value=False),
                mock.patch(
                    "process_manager.atomic.os.replace",
                    side_effect=PermissionError("access denied"),
                ) as replace,
                mock.patch("process_manager.atomic.time.sleep") as sleep,
            ):
                with self.assertRaisesRegex(StateError, "原子写入失败"):
                    atomic_write_bytes(target, b"{}\n")

            replace.assert_called_once()
            sleep.assert_not_called()

    def test_cleanup_failure_does_not_mask_primary_write_error(self) -> None:
        with workspace_directory() as directory:
            target = Path(directory) / "state.json"
            with (
                mock.patch("process_manager.atomic.os.replace", side_effect=OSError("primary")),
                mock.patch("process_manager.atomic.Path.unlink", side_effect=OSError("cleanup")),
            ):
                with self.assertRaisesRegex(StateError, "原子写入失败"):
                    atomic_write_bytes(target, b"{}\n")


if __name__ == "__main__":
    unittest.main()
