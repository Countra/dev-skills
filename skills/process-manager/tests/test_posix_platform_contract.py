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
from process_manager.errors import IdentityError, RuntimeInsecureError, SupervisorError  # noqa: E402
from process_manager.platforms.base import OwnerInspection, PersistedOwnerEvidence, PlatformSelection  # noqa: E402
from process_manager.platforms.linux import CgroupRunOwner, LinuxCgroupAdapter, LinuxProcessGroupAdapter  # noqa: E402
from process_manager.platforms.macos import MacOSAdapter, MacRunOwner  # noqa: E402
from process_manager.platforms.posix import PosixRunOwner  # noqa: E402


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
    def test_cgroup_owner_directory_failure_still_terminates_host(self) -> None:
        host = mock.Mock()
        host.pid = 123
        host.poll.side_effect = [None, 1]
        path = mock.MagicMock(spec=Path)
        path.mkdir.side_effect = OSError("denied")
        selection = PlatformSelection("linux", "cgroup-v2", "kernel-process-tree", "test")
        with self.assertRaisesRegex(OSError, "denied"):
            CgroupRunOwner(selection, host, "hash", path)
        host.kill.assert_called_once_with()
        host.wait.assert_called_once_with(timeout=5)
        path.rmdir.assert_not_called()

    def test_cgroup_owner_constructor_rolls_back_host_and_run_cgroup(self) -> None:
        class LiveHost:
            def __init__(self) -> None:
                self.pid = 123
                self.stdin = None
                self.stdout = None
                self.stderr = None
                self.alive = True
                self.killed = False

            def poll(self):  # noqa: ANN201
                return None if self.alive else 1

            def kill(self) -> None:
                self.killed = True

            def wait(self, timeout):  # noqa: ANN001,ANN201
                del timeout
                self.alive = False
                return 1

        path = mock.MagicMock(spec=Path)
        kill_file = mock.Mock()
        process_file = mock.Mock()
        path.__truediv__.side_effect = lambda name: {
            "cgroup.kill": kill_file,
            "cgroup.procs": process_file,
        }[name]
        kill_file.exists.return_value = True
        host = LiveHost()
        selection = PlatformSelection("linux", "cgroup-v2", "kernel-process-tree", "test")
        with (
            mock.patch.object(CgroupRunOwner, "_member_pids", return_value=set()),
            self.assertRaisesRegex(SupervisorError, "membership"),
        ):
            CgroupRunOwner(selection, host, "hash", path)
        self.assertTrue(host.killed)
        self.assertEqual(host.poll(), 1)
        path.rmdir.assert_called_once_with()

    def test_cgroup_owner_release_failure_is_not_silently_accepted(self) -> None:
        owner = object.__new__(CgroupRunOwner)
        owner.cgroup_path = mock.Mock()
        owner.cgroup_path.rmdir.side_effect = OSError("busy")
        with (
            mock.patch.object(PosixRunOwner, "close"),
            mock.patch.object(owner, "is_empty", return_value=True),
            self.assertRaises(SupervisorError),
        ):
            owner.close()

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
            "inspect_persisted_owner",
            "signal_persisted_owner",
            "terminate_manager",
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
            library = mock.Mock()

            def proc_pidinfo(pid, flavor, arg, pointer, size):  # noqa: ANN001,ANN201
                del flavor, arg
                info = pointer._obj
                info.pbi_pid = pid
                info.pbi_start_tvsec = 1_720_607_230
                info.pbi_start_tvusec = 456_789
                return size

            def proc_pidpath(pid, buffer, size):  # noqa: ANN001,ANN201
                del pid, size
                buffer.value = b"/usr/bin/python3"
                return len(buffer.value)

            library.proc_pidinfo.side_effect = proc_pidinfo
            library.proc_pidpath.side_effect = proc_pidpath
            with mock.patch("process_manager.platforms.macos.ctypes.CDLL", return_value=library):
                identity = adapter.process_identity(123)
                self.assertEqual(identity["startTimeMicros"], "1720607230456789")
                self.assertEqual(identity["executable"], "/usr/bin/python3")
                self.assertTrue(adapter.identity_matches(identity))
                self.assertFalse(adapter.identity_matches({**identity, "startTimeMicros": "1720607230456790"}))

    def test_macos_identity_failure_is_closed(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = MacOSAdapter(
                PlatformSelection("macos", "process-group-guardian", "process-group+kqueue", "test"),
                workspace,
                workspace / "state",
            )
            library = mock.Mock()
            library.proc_pidinfo.return_value = 0
            library.proc_pidpath.return_value = 0
            with mock.patch("process_manager.platforms.macos.ctypes.CDLL", return_value=library):
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
            with self.assertRaises(RuntimeInsecureError):
                adapter.verify_file(token)

    def test_process_group_recovery_requires_exact_live_leader(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = LinuxProcessGroupAdapter(
                PlatformSelection("linux", "process-group-guardian", "process-group", "test"),
                workspace,
                workspace / "state",
            )
            evidence = PersistedOwnerEvidence(
                "run-" + "1" * 32,
                "hash",
                {
                    "platform": "linux",
                    "backend": "process-group-guardian",
                    "capabilityHash": "hash",
                    "hostPid": 101,
                    "targetProcessGroup": 202,
                },
                {"pid": 101, "startTimeTicks": "1", "executable": "/host"},
                {"pid": 202, "startTimeTicks": "2", "executable": "/target"},
            )
            with (
                mock.patch.object(adapter, "identity_matches", side_effect=[True, True]),
                mock.patch("process_manager.platforms.posix.os.killpg", create=True),
                mock.patch("process_manager.platforms.posix.os.getpgid", return_value=202, create=True),
            ):
                inspection = adapter.inspect_persisted_owner(evidence)
            self.assertEqual(inspection.state, "active")
            self.assertTrue(inspection.cleanup_supported)
            with (
                mock.patch.object(adapter, "identity_matches", side_effect=[False, False]),
                mock.patch("process_manager.platforms.posix.os.killpg", create=True),
            ):
                unverifiable = adapter.inspect_persisted_owner(evidence)
            self.assertEqual(unverifiable.state, "unverifiable")
            self.assertEqual(unverifiable.error, "owner_group_leader_missing")
            missing_target = PersistedOwnerEvidence(
                evidence.run_id,
                evidence.capability_hash,
                evidence.owner,
                evidence.host_identity,
                None,
            )
            with (
                mock.patch.object(adapter, "identity_matches", return_value=False),
                mock.patch(
                    "process_manager.platforms.posix.os.killpg",
                    side_effect=ProcessLookupError,
                    create=True,
                ),
            ):
                pre_handshake_empty = adapter.inspect_persisted_owner(missing_target)
            self.assertTrue(pre_handshake_empty.empty)
            with (
                mock.patch.object(adapter, "identity_matches", return_value=False),
                mock.patch("process_manager.platforms.posix.os.killpg", create=True),
            ):
                pre_handshake_live = adapter.inspect_persisted_owner(missing_target)
            self.assertEqual(pre_handshake_live.state, "unverifiable")
            self.assertEqual(pre_handshake_live.error, "owner_target_identity_missing")

    def test_manager_termination_never_signals_unmatched_identity(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = LinuxProcessGroupAdapter(
                PlatformSelection("linux", "process-group-guardian", "process-group", "test"),
                workspace,
                workspace / "state",
            )
            with (
                mock.patch.object(adapter, "identity_matches", return_value=False),
                mock.patch("process_manager.platforms.posix.os.kill") as kill,
            ):
                self.assertFalse(adapter.terminate_manager({"pid": 123}, timeout=1))
            kill.assert_not_called()

    def test_cgroup_graceful_failure_does_not_fall_through_to_force_kill(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = LinuxCgroupAdapter(
                PlatformSelection("linux", "cgroup-v2", "kernel-process-tree", "test"),
                workspace,
                workspace / "state",
                workspace / "delegated",
            )
            evidence = PersistedOwnerEvidence(
                "run-" + "1" * 32,
                "hash",
                {
                    "platform": "linux",
                    "backend": "cgroup-v2",
                    "capabilityHash": "hash",
                    "hostPid": 101,
                    "targetProcessGroup": 202,
                    "cgroupPath": str(adapter.cgroup_base / ("run-" + "1" * 32)),
                },
                {"pid": 101, "startTimeTicks": "1", "executable": "/host"},
                {"pid": 202, "startTimeTicks": "2", "executable": "/target"},
            )
            with (
                mock.patch.object(
                    adapter,
                    "inspect_persisted_owner",
                    return_value=OwnerInspection("active", True, {}),
                ),
                mock.patch.object(
                    adapter,
                    "_persisted_cgroup",
                    return_value=adapter.cgroup_base / evidence.run_id,
                ),
                mock.patch.object(
                    LinuxProcessGroupAdapter,
                    "signal_persisted_owner",
                    return_value=False,
                ),
                mock.patch("pathlib.Path.write_text") as write_text,
            ):
                self.assertFalse(adapter.signal_persisted_owner(evidence, force=False))
            write_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
