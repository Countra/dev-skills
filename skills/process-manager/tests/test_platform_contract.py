from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import pm_manager  # noqa: E402
from process_manager.bootstrap import ManagerBootstrap  # noqa: E402
from process_manager.errors import (  # noqa: E402
    EnvironmentUnverifiableError,
    ManagerUnresponsiveError,
    RuntimeInsecureError,
    SupervisorError,
    UnsupportedPlatformError,
)
from process_manager.platforms.base import PersistedOwnerEvidence, PlatformSelection  # noqa: E402
from process_manager.platforms.dispatcher import describe_platform_selection  # noqa: E402
from process_manager.platforms.windows import WindowsAdapter  # noqa: E402
from process_manager.platforms.windows_acl import (  # noqa: E402
    DENY_ACCESS,
    FILE_ALL_ACCESS,
    GRANT_ACCESS,
    AclEntry,
    AclSnapshot,
    WindowsAcl,
    validate_acl_snapshot,
)
from process_manager.service_host import SecretRedactor  # noqa: E402


class PlatformContractTests(unittest.TestCase):
    def test_windows_acl_accepts_semantically_equivalent_safe_entries(self) -> None:
        sid = "S-1-5-21-1-2-3-1001"
        snapshot = AclSnapshot(
            sid,
            (
                AclEntry("S-1-5-32-544", FILE_ALL_ACCESS, GRANT_ACCESS, 0),
                AclEntry("S-1-1-0", FILE_ALL_ACCESS, DENY_ACCESS, 3),
                AclEntry(sid, FILE_ALL_ACCESS, GRANT_ACCESS, 3),
                AclEntry("S-1-5-18", FILE_ALL_ACCESS, GRANT_ACCESS, 0),
            ),
            FILE_ALL_ACCESS,
        )
        validate_acl_snapshot(snapshot, sid)

    def test_windows_acl_rejects_broad_or_unknown_allow_entries(self) -> None:
        sid = "S-1-5-21-1-2-3-1001"
        broad = AclSnapshot(
            sid,
            (AclEntry("S-1-1-0", 1, GRANT_ACCESS, 0),),
            FILE_ALL_ACCESS,
        )
        with self.assertRaises(RuntimeInsecureError):
            validate_acl_snapshot(broad, sid)
        unknown = AclSnapshot(
            sid,
            (AclEntry(sid, FILE_ALL_ACCESS, 99, 0),),
            FILE_ALL_ACCESS,
        )
        with self.assertRaises(EnvironmentUnverifiableError):
            validate_acl_snapshot(unknown, sid)

    def test_manager_stop_fails_when_bootstrap_cleanup_is_unverified(self) -> None:
        from helpers import create_config, workspace_directory

        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = mock.Mock()
            adapter.identity_matches.return_value = False
            adapter.validate_runtime_path.side_effect = lambda path: path
            bootstrap = ManagerBootstrap(config, adapter)
            identity = {
                "instanceId": "test-manager",
                "identity": {"pid": 123},
                "bootstrapBackend": "test",
            }
            with mock.patch.object(bootstrap, "cleanup", return_value=False):
                with self.assertRaisesRegex(ManagerUnresponsiveError, "bootstrap"):
                    bootstrap.stop_manager(
                        identity,
                        request_shutdown=None,
                        allow_terminate=False,
                        timeout=1,
                    )

    def test_internal_selection_covers_three_platforms_without_public_selector(self) -> None:
        selections = {
            "windows": describe_platform_selection("win32"),
            "linux-strict": describe_platform_selection("linux", delegated_cgroup_available=True),
            "linux-fallback": describe_platform_selection("linux", delegated_cgroup_available=False),
            "macos": describe_platform_selection("darwin"),
        }
        self.assertEqual(selections["windows"].backend, "job-object")
        self.assertEqual(selections["linux-strict"].backend, "cgroup-v2")
        self.assertEqual(selections["linux-fallback"].backend, "process-group-guardian")
        self.assertEqual(selections["macos"].capability, "process-group+kqueue")
        parser = pm_manager.build_parser()
        option_strings = {
            option
            for action in parser._actions  # noqa: SLF001
            for option in getattr(action, "option_strings", [])
        }
        self.assertFalse({"--platform", "--backend", "--guarantee"} & option_strings)
        with self.assertRaises(UnsupportedPlatformError):
            describe_platform_selection("plan9")

    def test_windows_persisted_job_recovery_is_verify_only_without_handle(self) -> None:
        adapter = object.__new__(WindowsAdapter)
        adapter.selection = PlatformSelection("windows", "job-object", "kernel-process-tree", "test")
        evidence = PersistedOwnerEvidence(
            "run-" + "1" * 32,
            "hash",
            {
                "platform": "windows",
                "backend": "job-object",
                "capabilityHash": "hash",
                "hostPid": 101,
            },
            {"pid": 101, "creationFileTime": "1", "executable": "host.exe"},
            {"pid": 202, "creationFileTime": "2", "executable": "target.exe"},
        )
        with mock.patch.object(adapter, "identity_matches", side_effect=[False, False]):
            empty = adapter.inspect_persisted_owner(evidence)
        self.assertTrue(empty.empty)
        with mock.patch.object(adapter, "identity_matches", side_effect=[True, True]):
            active = adapter.inspect_persisted_owner(evidence)
        self.assertEqual(active.state, "active")
        self.assertFalse(active.cleanup_supported)
        self.assertEqual(active.error, "owner_job_handle_unavailable")
        missing_target = PersistedOwnerEvidence(
            evidence.run_id,
            evidence.capability_hash,
            evidence.owner,
            evidence.host_identity,
            None,
        )
        with mock.patch.object(adapter, "identity_matches", return_value=False):
            pre_handshake_empty = adapter.inspect_persisted_owner(missing_target)
        self.assertTrue(pre_handshake_empty.empty)
        with mock.patch.object(adapter, "identity_matches", return_value=True):
            pre_handshake_live = adapter.inspect_persisted_owner(missing_target)
        self.assertEqual(pre_handshake_live.state, "unverifiable")
        self.assertEqual(pre_handshake_live.error, "owner_target_identity_missing")
        malformed = PersistedOwnerEvidence(
            evidence.run_id,
            evidence.capability_hash,
            evidence.owner,
            {"pid": 101},
            {"pid": 202},
        )
        with mock.patch.object(adapter, "identity_matches", side_effect=AssertionError("不得探测不完整身份")):
            invalid = adapter.inspect_persisted_owner(malformed)
        self.assertEqual(invalid.state, "unverifiable")

    def test_windows_manager_termination_closes_handle_before_final_identity_check(self) -> None:
        adapter = object.__new__(WindowsAdapter)
        closed: list[int] = []
        calls = 0

        def identity_matches(expected):  # noqa: ANN001,ANN201
            nonlocal calls
            del expected
            calls += 1
            if calls == 3:
                self.assertEqual(closed, [123])
                return False
            return True

        kernel32 = types.SimpleNamespace(
            OpenProcess=mock.Mock(return_value=123),
            TerminateProcess=mock.Mock(return_value=True),
            WaitForSingleObject=mock.Mock(return_value=0),
        )
        adapter.api = types.SimpleNamespace(
            kernel32=kernel32,
            close=lambda handle: closed.append(handle),
        )
        adapter.identity_matches = identity_matches  # type: ignore[method-assign]
        self.assertTrue(adapter.terminate_manager({"pid": 42}, timeout=1))
        self.assertEqual(calls, 3)

    def test_secret_redactor_handles_values_across_chunk_boundaries(self) -> None:
        redactor = SecretRedactor(["secret-token"])
        output = redactor.feed(b"prefix secret-") + redactor.feed(b"token suffix") + redactor.finish()
        self.assertEqual(output, b"prefix ***redacted*** suffix")
        overlapping = SecretRedactor(["abc", "ab"])
        self.assertEqual(overlapping.feed(b"ab"), b"")
        self.assertEqual(overlapping.feed(b"c!"), b"***redacted***!")

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows ACL contract")
    def test_windows_acl_application_fails_closed(self) -> None:
        from unittest import mock

        from helpers import workspace_directory
        from process_manager.errors import SupervisorError
        from process_manager.platforms import select_platform_adapter

        with workspace_directory() as directory:
            workspace = Path(directory)
            state_root = workspace / ".harness" / "process-manager"
            state_root.mkdir(parents=True)
            adapter = select_platform_adapter(workspace, state_root)
            with mock.patch.object(adapter.acl, "_current_sid", return_value="S-1-5-21-test"):
                with mock.patch.object(adapter.acl, "_apply_acl", side_effect=SupervisorError("ACL denied")):
                    with self.assertRaises(SupervisorError):
                        adapter.secure_directory(state_root)

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows ACL contract")
    def test_windows_acl_descriptor_is_protected_and_closed(self) -> None:
        from unittest import mock

        from helpers import workspace_directory
        from process_manager.platforms import select_platform_adapter

        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = select_platform_adapter(workspace, workspace / ".harness" / "process-manager")
            with mock.patch.object(adapter.acl, "_current_sid", return_value="S-1-5-21-test"):
                directory_sddl = adapter.acl._acl_sddl(directory=True)  # noqa: SLF001
                file_sddl = adapter.acl._acl_sddl(directory=False)  # noqa: SLF001
            self.assertTrue(directory_sddl.startswith("D:P"))
            self.assertIn("S-1-5-21-test", directory_sddl)
            self.assertIn("OICI", directory_sddl)
            self.assertNotIn("OICI", file_sddl)

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows mutex contract")
    def test_windows_manager_lock_is_exclusive(self) -> None:
        from helpers import workspace_directory
        from process_manager.errors import ConflictError
        from process_manager.platforms import select_platform_adapter

        with workspace_directory() as directory:
            workspace = Path(directory)
            adapter = select_platform_adapter(workspace, workspace / ".harness" / "process-manager")
            first = adapter.acquire_manager_lock()
            try:
                with self.assertRaises(ConflictError):
                    adapter.acquire_manager_lock()
            finally:
                first.close()
            second = adapter.acquire_manager_lock()
            second.close()


if __name__ == "__main__":
    unittest.main()
