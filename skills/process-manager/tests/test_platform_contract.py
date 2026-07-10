from __future__ import annotations

import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import pm_manager  # noqa: E402
from process_manager.errors import SupervisorError, UnsupportedPlatformError  # noqa: E402
from process_manager.platforms.dispatcher import describe_platform_selection  # noqa: E402
from process_manager.platforms.windows_acl import WindowsAcl  # noqa: E402
from process_manager.service_host import SecretRedactor  # noqa: E402


class PlatformContractTests(unittest.TestCase):
    def test_windows_acl_accepts_equivalent_full_access_masks(self) -> None:
        for value in ("FA", "GA", "0x1f01ff", "0x001f01ff", "0x10000000"):
            with self.subTest(value=value):
                self.assertTrue(WindowsAcl._is_full_access(value))  # noqa: SLF001
        for value in ("FR", "0x120089", "not-a-mask"):
            with self.subTest(value=value):
                self.assertFalse(WindowsAcl._is_full_access(value))  # noqa: SLF001

    def test_windows_acl_verifies_normalized_numeric_sddl(self) -> None:
        sid = "S-1-5-21-1-2-3-1001"
        acl = object.__new__(WindowsAcl)
        with (
            mock.patch.object(acl, "_current_sid", return_value=sid),
            mock.patch.object(
                acl,
                "_read_acl_sddl",
                return_value=(
                    f"D:PAI(A;OICI;0x001f01ff;;;{sid})"
                    "(A;OICI;0x001f01ff;;;S-1-5-18)"
                    "(A;OICI;0x001f01ff;;;S-1-5-32-544)"
                ),
            ),
        ):
            acl._verify_acl(Path("runtime"))  # noqa: SLF001

    def test_windows_acl_accepts_local_administrator_alias_only_for_matching_rid(self) -> None:
        acl = object.__new__(WindowsAcl)
        sddl = "D:PAI(A;OICI;FA;;;LA)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        with mock.patch.object(acl, "_read_acl_sddl", return_value=sddl):
            with mock.patch.object(
                acl,
                "_current_sid",
                return_value="S-1-5-21-1-2-3-500",
            ):
                acl._verify_acl(Path("runtime"))  # noqa: SLF001
            with mock.patch.object(
                acl,
                "_current_sid",
                return_value="S-1-5-21-1-2-3-1001",
            ):
                with self.assertRaises(SupervisorError):
                    acl._verify_acl(Path("runtime"))  # noqa: SLF001

    def test_manager_stop_fails_when_bootstrap_cleanup_is_unverified(self) -> None:
        from helpers import create_config, workspace_directory

        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            client = mock.Mock()
            client.request.return_value = (200, {"ok": True, "data": {}, "meta": {}})
            bootstrap = mock.Mock()
            bootstrap.cleanup.return_value = False
            with (
                mock.patch.object(pm_manager, "_client", return_value=(config, mock.Mock(), client)),
                mock.patch.object(
                    pm_manager,
                    "read_manager_identity",
                    return_value={"bootstrapBackend": "test"},
                ),
                mock.patch.object(pm_manager, "ManagerBootstrap", return_value=bootstrap),
            ):
                with self.assertRaisesRegex(SupervisorError, "bootstrap cleanup"):
                    pm_manager._stop(Namespace(config=str(config.config_path), pretty=False))  # noqa: SLF001

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
