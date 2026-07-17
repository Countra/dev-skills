from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory  # noqa: E402
from process_manager.bootstrap import (  # noqa: E402
    BootstrapResult,
    ManagerBootstrap,
    cleanup_bootstrap_result,
)
from process_manager.platforms.base import PlatformSelection  # noqa: E402


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

        def runner(command, **kwargs):  # noqa: ANN001,ANN201
            del kwargs
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

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

            def runner(command, **kwargs):  # noqa: ANN001,ANN201
                del kwargs
                return subprocess.CompletedProcess(command, 0, "", "")

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
        bootstrap.cleanup.return_value = True
        result = BootstrapResult("fixture", "fixture", process)
        self.assertTrue(cleanup_bootstrap_result(bootstrap, result, timeout=0.01))
        self.assertTrue(process.killed)
        bootstrap.cleanup.assert_called_once_with("fixture")


if __name__ == "__main__":
    unittest.main()
