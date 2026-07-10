from __future__ import annotations

import inspect
import os
import stat
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

if os.name == "nt" and "fcntl" not in sys.modules:
    fcntl_stub = types.ModuleType("fcntl")
    fcntl_stub.LOCK_EX = 1
    fcntl_stub.LOCK_NB = 2
    fcntl_stub.LOCK_UN = 4
    fcntl_stub.flock = lambda *_args: None
    sys.modules["fcntl"] = fcntl_stub

from helpers import workspace_directory  # noqa: E402
from process_manager.errors import IdentityError, SupervisorError  # noqa: E402
from process_manager.platforms.base import PlatformSelection  # noqa: E402
from process_manager.platforms.linux import LinuxCgroupAdapter, LinuxProcessGroupAdapter  # noqa: E402
from process_manager.platforms.macos import MacOSAdapter, MacRunOwner  # noqa: E402


class FakeHost:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stdin = None
        self.stdout = None
        self.stderr = None

    def poll(self) -> int:
        return 0


class FakeKqueue:
    def __init__(self) -> None:
        self.registered = False
        self.polled = False
        self.closed = False

    def control(self, changelist, max_events, timeout):  # noqa: ANN001,ANN201
        del max_events, timeout
        if changelist is not None:
            self.registered = True
            return []
        self.polled = True
        return [object()]

    def close(self) -> None:
        self.closed = True


class PosixPlatformContractTests(unittest.TestCase):
    def test_linux_and_macos_adapters_share_internal_contract(self) -> None:
        required_methods = {
            "secure_directory",
            "secure_file",
            "verify_file",
            "acquire_manager_lock",
            "spawn_manager",
            "spawn_service_host",
            "create_run_owner",
            "process_identity",
            "identity_matches",
        }
        with workspace_directory() as directory:
            workspace = Path(directory)
            state_root = workspace / ".harness" / "process-manager"
            adapters = (
                LinuxProcessGroupAdapter(
                    PlatformSelection("linux", "process-group-guardian", "process-group", "test"),
                    workspace,
                    state_root,
                ),
                LinuxCgroupAdapter(
                    PlatformSelection("linux", "cgroup-v2", "kernel-process-tree", "test"),
                    workspace,
                    state_root,
                    workspace / "delegated-cgroup",
                ),
                MacOSAdapter(
                    PlatformSelection("macos", "process-group-guardian", "process-group+kqueue", "test"),
                    workspace,
                    state_root,
                ),
            )
            for adapter in adapters:
                with self.subTest(adapter=type(adapter).__name__):
                    self.assertFalse(inspect.isabstract(type(adapter)))
                    for method in required_methods:
                        self.assertTrue(callable(getattr(adapter, method)))

    def test_macos_identity_uses_start_time_and_executable(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = MacOSAdapter(
                PlatformSelection("macos", "process-group-guardian", "process-group+kqueue", "test"),
                workspace,
                workspace / "state",
            )
            result = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="Fri Jul 10 10:20:30 2026 /usr/bin/python3\n",
                stderr="",
            )
            with mock.patch("process_manager.platforms.macos.subprocess.run", return_value=result):
                identity = adapter.process_identity(123)
                self.assertEqual(identity["startTime"], "Fri Jul 10 10:20:30 2026")
                self.assertEqual(identity["executable"], "/usr/bin/python3")
                self.assertTrue(adapter.identity_matches(identity))
                self.assertFalse(adapter.identity_matches({**identity, "startTime": "changed"}))

    def test_macos_identity_failure_is_closed(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = MacOSAdapter(
                PlatformSelection("macos", "process-group-guardian", "process-group+kqueue", "test"),
                workspace,
                workspace / "state",
            )
            result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
            with mock.patch("process_manager.platforms.macos.subprocess.run", return_value=result):
                with self.assertRaises(IdentityError):
                    adapter.process_identity(123)

    def test_macos_owner_consumes_kqueue_exit_event(self) -> None:
        queue = FakeKqueue()
        host = FakeHost(123)
        owner = MacRunOwner(
            PlatformSelection("macos", "process-group-guardian", "process-group+kqueue", "test"),
            host,  # type: ignore[arg-type]
            "capability-hash",
        )
        with (
            mock.patch("process_manager.platforms.macos.select.kqueue", return_value=queue, create=True),
            mock.patch("process_manager.platforms.macos.select.kevent", return_value=object(), create=True),
            mock.patch("process_manager.platforms.macos.select.KQ_FILTER_PROC", 1, create=True),
            mock.patch("process_manager.platforms.macos.select.KQ_EV_ADD", 2, create=True),
            mock.patch("process_manager.platforms.macos.select.KQ_EV_ENABLE", 4, create=True),
            mock.patch("process_manager.platforms.macos.select.KQ_NOTE_EXIT", 8, create=True),
            mock.patch("process_manager.platforms.posix.os.getpgid", return_value=123, create=True),
            mock.patch(
                "process_manager.platforms.posix.os.killpg",
                side_effect=ProcessLookupError,
                create=True,
            ),
        ):
            owner.bind_target({"pid": 123, "pgid": 123})
            self.assertEqual(owner.internal_identity()["targetExitMonitor"], "kqueue")
            self.assertTrue(owner.is_empty())
            owner.close()
        self.assertTrue(queue.registered)
        self.assertTrue(queue.polled)
        self.assertTrue(queue.closed)

    @unittest.skipUnless(os.name == "posix", "POSIX 权限语义需要 POSIX runner")
    def test_posix_runtime_permissions_are_owner_only(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            state_root = workspace / "state"
            adapter = LinuxProcessGroupAdapter(
                PlatformSelection("linux", "process-group-guardian", "process-group", "test"),
                workspace,
                state_root,
            )
            adapter.secure_directory(state_root)
            self.assertEqual(stat.S_IMODE(state_root.stat().st_mode), 0o700)
            token = state_root / "token"
            token.write_text("test", encoding="utf-8")
            adapter.secure_file(token)
            self.assertEqual(stat.S_IMODE(token.stat().st_mode), 0o600)
            os.chmod(token, 0o644)
            with self.assertRaises(SupervisorError):
                adapter.verify_file(token)


if __name__ == "__main__":
    unittest.main()
