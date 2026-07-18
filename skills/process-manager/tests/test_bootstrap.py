from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory  # noqa: E402
from process_manager.bootstrap import (  # noqa: E402
    BootstrapResult,
    ManagerBootstrap,
    read_bootstrap_capture,
    remove_bootstrap_capture,
    write_bootstrap_capture,
)
from process_manager.errors import (  # noqa: E402
    ConflictError,
    EnvironmentUnverifiableError,
    ManagerUnresponsiveError,
    RuntimeCorruptError,
)
from process_manager.manager_start import cleanup_bootstrap_result  # noqa: E402
from process_manager.platforms.base import PlatformSelection  # noqa: E402
from process_manager.runtime import initialize_runtime  # noqa: E402


def command_factory(backend: str, reason: str) -> list[str]:
    return [sys.executable, "manager_server.py", "--bootstrap-backend", backend, "--bootstrap-reason", reason]


class BootstrapTests(unittest.TestCase):
    def make_bootstrap(
        self,
        workspace: Path,
        platform: str,
        runner,
        *,
        manager_probe=None,
    ):  # noqa: ANN001,ANN201
        config = create_config(workspace)
        adapter = FakeAdapter(workspace, config.state_root)
        adapter.selection = PlatformSelection(platform, "fake-owner", "test", "fixture")
        bootstrap = ManagerBootstrap(
            config,
            adapter,
            runner=runner,
            which=lambda name: f"/usr/bin/{name}",
            manager_probe=manager_probe or (lambda: True),
            native_ready_timeout=0,
        )
        return config, adapter, bootstrap

    def test_linux_prefers_systemd_user_without_exposing_selector(self) -> None:
        calls: list[list[str]] = []

        def runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}):
            workspace = Path(directory)
            _, _, bootstrap = self.make_bootstrap(workspace, "linux", runner)
            result = bootstrap.start(
                command_factory,
                stdout_path=workspace / "out.log",
                stderr_path=workspace / "err.log",
                stdout=io.BytesIO(),
                stderr=io.BytesIO(),
            )
        self.assertEqual(result.backend, "systemd-user")
        self.assertIsNone(result.process)
        self.assertTrue(any(command[0] == "systemd-run" for command in calls))
        self.assertFalse(any("sudo" in item for command in calls for item in command))

    def test_linux_and_macos_fallback_use_same_adapter_spawn(self) -> None:
        def unavailable(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            return subprocess.CompletedProcess(command, 1, "", "unavailable")

        for platform in ("linux", "macos"):
            with self.subTest(platform=platform), workspace_directory() as directory:
                workspace = Path(directory)
                _, adapter, bootstrap = self.make_bootstrap(workspace, platform, unavailable)
                process = object()
                with mock.patch.object(adapter, "spawn_manager", return_value=process) as spawn:
                    result = bootstrap.start(
                        command_factory,
                        stdout_path=workspace / "out.log",
                        stderr_path=workspace / "err.log",
                        stdout=io.BytesIO(),
                        stderr=io.BytesIO(),
                    )
                self.assertEqual(result.backend, "posix-session")
                self.assertIs(result.process, process)
                spawn.assert_called_once()

    def test_macos_falls_back_when_launchd_does_not_create_identity(self) -> None:
        calls: list[list[str]] = []
        booted_out = False

        def runner(command, **kwargs):  # noqa: ANN001,ANN201
            nonlocal booted_out
            del kwargs
            calls.append(command)
            if command[:2] == ["/bin/launchctl", "bootout"]:
                booted_out = True
            returncode = 113 if booted_out and command[:2] == ["/bin/launchctl", "print"] else 0
            return subprocess.CompletedProcess(command, returncode, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(
                workspace,
                "macos",
                runner,
                manager_probe=lambda: False,
            )
            process = object()
            with (
                mock.patch.object(bootstrap, "_launchd_domain", return_value="gui/501"),
                mock.patch.object(adapter, "spawn_manager", return_value=process),
            ):
                result = bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
        self.assertEqual(result.backend, "posix-session")
        self.assertIs(result.process, process)
        self.assertTrue(any(command[:2] == ["/bin/launchctl", "bootout"] for command in calls))

    def test_macos_keeps_launchd_when_manager_is_healthy(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            job_present = False

            def runner(command, **kwargs):  # noqa: ANN001,ANN201
                nonlocal job_present
                del kwargs
                if command[:2] == ["/bin/launchctl", "bootout"]:
                    job_present = False
                elif command[:2] == ["/bin/launchctl", "bootstrap"]:
                    job_present = True
                returncode = (
                    0
                    if command[:2] != ["/bin/launchctl", "print"] or job_present
                    else 113
                )
                return subprocess.CompletedProcess(command, returncode, "", "")

            _, _, bootstrap = self.make_bootstrap(workspace, "macos", runner)
            with mock.patch.object(bootstrap, "_launchd_domain", return_value="gui/501"):
                result = bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
        self.assertEqual(result.backend, "launchd-user")
        self.assertIsNone(result.process)

    def test_native_residue_blocks_detached_fallback(self) -> None:
        def systemd_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            returncode = 1 if command[0] == "systemd-run" else 0
            return subprocess.CompletedProcess(command, returncode, "", "")

        with workspace_directory() as directory, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}):
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(workspace, "linux", systemd_runner)
            with (
                mock.patch.object(adapter, "spawn_manager") as spawn,
                self.assertRaises(ManagerUnresponsiveError),
            ):
                bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
            spawn.assert_not_called()

        def launchd_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(workspace, "macos", launchd_runner)
            with (
                mock.patch.object(bootstrap, "_launchd_domain", return_value="gui/501"),
                mock.patch.object(adapter, "spawn_manager") as spawn,
                self.assertRaises(ManagerUnresponsiveError),
            ):
                bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
            spawn.assert_not_called()

    def test_native_command_errors_require_verified_absence_before_fallback(self) -> None:
        def systemd_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            if command[0] == "systemd-run":
                raise OSError("fixture")
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}):
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(workspace, "linux", systemd_runner)
            with (
                mock.patch.object(adapter, "spawn_manager") as spawn,
                self.assertRaises(ManagerUnresponsiveError),
            ):
                bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
            spawn.assert_not_called()

        def launchd_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            if command[:2] == ["/bin/launchctl", "bootstrap"]:
                raise OSError("fixture")
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(workspace, "macos", launchd_runner)
            with (
                mock.patch.object(bootstrap, "_launchd_domain", return_value="gui/501"),
                mock.patch.object(adapter, "spawn_manager") as spawn,
                self.assertRaises(ManagerUnresponsiveError),
            ):
                bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
            spawn.assert_not_called()

    def test_native_status_command_errors_are_environment_unverifiable(self) -> None:
        def failing_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del command, kwargs
            raise OSError("fixture")

        with workspace_directory() as directory, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}):
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(workspace, "linux", failing_runner)
            with (
                mock.patch.object(adapter, "spawn_manager") as spawn,
                self.assertRaises(EnvironmentUnverifiableError),
            ):
                bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
            spawn.assert_not_called()

    def test_windows_uses_detached_adapter_and_cleanup_is_workspace_scoped(self) -> None:
        def runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, bootstrap = self.make_bootstrap(workspace, "windows", runner)
            process = object()
            with mock.patch.object(adapter, "spawn_manager", return_value=process):
                result = bootstrap.start(
                    command_factory,
                    stdout_path=workspace / "out.log",
                    stderr_path=workspace / "err.log",
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                )
            self.assertEqual(result.backend, "windows-detached")
            self.assertTrue(bootstrap.cleanup(result.backend))

        launchd = BootstrapResult("launchd-user", "test", None)
        self.assertEqual(launchd.backend, "launchd-user")

    def test_systemd_cleanup_requires_explicit_inactive_state(self) -> None:
        calls: list[list[str]] = []

        def active_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, bootstrap = self.make_bootstrap(workspace, "linux", active_runner)
            self.assertFalse(bootstrap.cleanup("systemd-user"))
            self.assertEqual(calls[-1][:4], ["systemctl", "--user", "is-active", "--quiet"])

            def inactive_runner(command, **kwargs):  # noqa: ANN001,ANN201
                del kwargs
                returncode = 3 if "is-active" in command else 0
                return subprocess.CompletedProcess(command, returncode, "", "")

            _, _, bootstrap = self.make_bootstrap(workspace, "linux", inactive_runner)
            self.assertTrue(bootstrap.cleanup("systemd-user"))

            def unknown_runner(command, **kwargs):  # noqa: ANN001,ANN201
                del kwargs
                returncode = 1 if "is-active" in command else 0
                return subprocess.CompletedProcess(command, returncode, "", "")

            _, _, bootstrap = self.make_bootstrap(workspace, "linux", unknown_runner)
            with self.assertRaises(EnvironmentUnverifiableError):
                bootstrap.cleanup("systemd-user")

            def failing_runner(command, **kwargs):  # noqa: ANN001,ANN201
                del command, kwargs
                raise OSError("fixture")

            _, _, bootstrap = self.make_bootstrap(workspace, "linux", failing_runner)
            self.assertFalse(bootstrap.cleanup("systemd-user"))

    def test_launchd_cleanup_requires_explicit_absence_state(self) -> None:
        def present_runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, bootstrap = self.make_bootstrap(workspace, "macos", present_runner)
            bootstrap.launchd_plist.write_text("fixture", encoding="utf-8")
            with mock.patch.object(bootstrap, "_launchd_domain", return_value="gui/501"):
                self.assertFalse(bootstrap.cleanup("launchd-user"))
            self.assertTrue(bootstrap.launchd_plist.exists())

            def absent_runner(command, **kwargs):  # noqa: ANN001,ANN201
                del kwargs
                returncode = 113 if command[:2] == ["/bin/launchctl", "print"] else 0
                return subprocess.CompletedProcess(command, returncode, "", "")

            _, _, bootstrap = self.make_bootstrap(workspace, "macos", absent_runner)
            with mock.patch.object(bootstrap, "_launchd_domain", return_value="gui/501"):
                self.assertTrue(bootstrap.cleanup("launchd-user"))
            self.assertFalse(bootstrap.launchd_plist.exists())

    def test_unknown_bootstrap_backend_is_not_treated_as_clean(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, bootstrap = self.make_bootstrap(workspace, "fixture", mock.Mock())
            self.assertFalse(bootstrap.cleanup("unknown"))
            self.assertTrue(bootstrap.cleanup("platform-session"))

    def test_linux_residue_probe_only_reads_deterministic_unit(self) -> None:
        calls: list[list[str]] = []

        def runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": directory}):
            workspace = Path(directory)
            _, _, bootstrap = self.make_bootstrap(workspace, "linux", runner)
            self.assertTrue(bootstrap.residue_present())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ["systemctl", "--user", "is-active", "--quiet"])

    def test_non_native_bootstrap_has_no_residue_probe(self) -> None:
        calls: list[list[str]] = []

        def runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, bootstrap = self.make_bootstrap(workspace, "windows", runner)
            self.assertFalse(bootstrap.residue_present())
        self.assertEqual(calls, [])

    def test_bootstrap_cleanup_escalates_exact_handle_and_verifies_backend(self) -> None:
        class StubbornProcess:
            def __init__(self) -> None:
                self.alive = True
                self.killed = False

            def poll(self):  # noqa: ANN201
                return None if self.alive else 0

            def terminate(self) -> None:
                return

            def wait(self, timeout):  # noqa: ANN001,ANN201
                if not self.killed:
                    raise subprocess.TimeoutExpired("fixture", timeout)
                self.alive = False
                return 0

            def kill(self) -> None:
                self.killed = True

        process = StubbornProcess()
        bootstrap = mock.Mock()
        bootstrap.cleanup_residue.return_value = True
        result = BootstrapResult("fixture", "fixture", process)
        self.assertTrue(cleanup_bootstrap_result(bootstrap, result, timeout=0.01))
        self.assertTrue(process.killed)
        bootstrap.cleanup_residue.assert_called_once_with(timeout=0.01, preferred_backend="fixture")

    def test_bootstrap_capture_is_closed_and_never_overwritten(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, _ = self.make_bootstrap(workspace, "windows", mock.Mock())
            initialize_runtime(config, adapter)
            operation_id = uuid.uuid4().hex
            capture = write_bootstrap_capture(
                config,
                adapter,
                operation_id=operation_id,
                backend="fixture",
                runtime_fingerprint="a" * 64,
            )
            self.assertEqual(read_bootstrap_capture(config, adapter), capture)
            with self.assertRaises(ConflictError):
                write_bootstrap_capture(
                    config,
                    adapter,
                    operation_id=uuid.uuid4().hex,
                    backend="other",
                    runtime_fingerprint="b" * 64,
                )
            self.assertFalse(
                remove_bootstrap_capture(
                    config,
                    adapter,
                    operation_id=uuid.uuid4().hex,
                    process_identity=capture["processIdentity"],
                )
            )
            with mock.patch.object(adapter, "verify_file", wraps=adapter.verify_file) as verify_file:
                self.assertTrue(
                    remove_bootstrap_capture(
                        config,
                        adapter,
                        operation_id=operation_id,
                        process_identity=capture["processIdentity"],
                    )
                )
            self.assertEqual(verify_file.call_count, 2)

    def test_bootstrap_capture_cleanup_terminates_only_exact_identity(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, bootstrap = self.make_bootstrap(workspace, "windows", mock.Mock())
            initialize_runtime(config, adapter)
            write_bootstrap_capture(
                config,
                adapter,
                operation_id=uuid.uuid4().hex,
                backend="windows-detached",
                runtime_fingerprint="a" * 64,
            )
            self.assertTrue(bootstrap.cleanup_residue(timeout=1))
            self.assertEqual(adapter.manager_terminations, 1)
            self.assertIsNone(read_bootstrap_capture(config, adapter))

    def test_bootstrap_capture_rejects_tampered_config_digest(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, _ = self.make_bootstrap(workspace, "windows", mock.Mock())
            initialize_runtime(config, adapter)
            write_bootstrap_capture(
                config,
                adapter,
                operation_id=uuid.uuid4().hex,
                backend="fixture",
                runtime_fingerprint="a" * 64,
            )
            value = config.paths.bootstrap.read_text(encoding="utf-8").replace(
                '"configDigest": "',
                '"configDigest": "tampered-',
            )
            config.paths.bootstrap.write_text(value, encoding="utf-8")
            with self.assertRaises(RuntimeCorruptError):
                read_bootstrap_capture(config, adapter)


if __name__ == "__main__":
    unittest.main()
