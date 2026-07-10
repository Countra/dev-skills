from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, service_value, workspace_directory, write_json  # noqa: E402
from process_manager.errors import ConflictError, IdentityError, NotFoundError, SupervisorError  # noqa: E402
from process_manager.manager import ProcessManager  # noqa: E402
from process_manager.state import StateStore  # noqa: E402


class FakeHost:
    def __init__(self) -> None:
        self.pid = 4242
        self.returncode = None
        self.capability_hash = ""
        self.stdout = FakeControlOutput(self)
        self.stderr = io.StringIO()
        self.stdin = io.StringIO()
        self._exited = threading.Event()

    def poll(self):  # noqa: ANN201
        return self.returncode

    def kill(self) -> None:
        self.finish(1)

    def terminate(self) -> None:
        self.finish(1)

    def finish(self, code: int) -> None:
        self.returncode = code
        self._exited.set()

    def wait(self, timeout=None):  # noqa: ANN001,ANN201
        if not self._exited.wait(timeout):
            raise subprocess.TimeoutExpired("fake-host", timeout)
        return self.returncode


class FakeControlOutput:
    def __init__(self, host: FakeHost) -> None:
        self.host = host
        self.index = 0

    def readline(self, size=-1):  # noqa: ANN001,ANN201
        self.index += 1
        if self.index == 1:
            return json.dumps({"event": "host_ready", "pid": self.host.pid}) + "\n"
        if self.index == 2:
            return (
                json.dumps(
                    {
                        "event": "target_started",
                        "capabilityHash": self.host.capability_hash,
                        "target": {"pid": 4343, "pgid": 4343},
                    }
                )
                + "\n"
            )
        return ""

    def close(self) -> None:
        return


class ManagerTests(unittest.TestCase):
    def make_manager(self, workspace: Path):  # noqa: ANN201
        config = create_config(workspace)
        adapter = FakeAdapter(workspace, config.state_root)
        adapter.secure_directory(config.paths.runs)
        hosts: list[FakeHost] = []

        def host_factory() -> FakeHost:
            host = FakeHost()
            hosts.append(host)
            return host

        adapter.host_factory = host_factory
        state = StateStore(config, adapter)
        state.load()
        manager = ProcessManager(config, adapter, state, "manager-instance")
        return config, adapter, state, manager, hosts

    def test_start_status_stop_hide_internal_owner_and_secret(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, state, manager, hosts = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace, from_env=["APP_TOKEN"]))
            with mock.patch.dict(os.environ, {"APP_TOKEN": "secret-value"}, clear=False):
                started = manager.start(service_path)
            self.assertEqual(started["state"], "running")
            self.assertNotIn("platform", json.dumps(started))
            self.assertNotIn("backend", json.dumps(started))
            self.assertNotIn("secret-value", json.dumps(started))
            self.assertIn("secret-value", hosts[0].stdin.getvalue())
            with self.assertRaises(ConflictError):
                with mock.patch.dict(os.environ, {"APP_TOKEN": "secret-value"}, clear=False):
                    manager.start(service_path)
            status = manager.status(service="demo")
            self.assertEqual(status["processKey"], started["processKey"])
            stopped = manager.stop(process_key=started["processKey"])
            self.assertTrue(stopped["cleanupVerified"])
            manager.shutdown()
            persisted = config.paths.processes.read_text(encoding="utf-8")
            self.assertNotIn("secret-value", persisted)
            self.assertNotIn("runCapability", persisted)

    def test_stop_rejects_run_not_owned_by_current_manager(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            state.update(
                started["processKey"],
                status="running",
                internal_updates={"managerInstanceId": "another-manager"},
            )
            with self.assertRaises(IdentityError):
                manager.stop(process_key=started["processKey"])
            state.update(
                started["processKey"],
                status="running",
                internal_updates={"managerInstanceId": "manager-instance"},
            )
            manager.stop(process_key=started["processKey"])
            manager.shutdown()

    def test_health_contract_is_platform_neutral(self) -> None:
        with workspace_directory() as directory:
            _, _, _, manager, _ = self.make_manager(Path(directory))
            value = manager.health()
            self.assertEqual(
                set(value),
                {"managerReady", "supervisorReady", "instance", "endpointHealthy"},
            )

    def test_missing_process_uses_not_found_error(self) -> None:
        with workspace_directory() as directory:
            _, _, _, manager, _ = self.make_manager(Path(directory))
            with self.assertRaises(NotFoundError) as raised:
                manager.status(process_key="missing.run-00000000000000000000000000000000")
            self.assertEqual(raised.exception.http_status, 404)

    def test_start_cleanup_failure_does_not_mask_primary_error(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            with (
                mock.patch.object(adapter, "process_identity", side_effect=IdentityError("primary identity failure")),
                mock.patch(
                    "helpers.FakeOwner.force_stop",
                    side_effect=SupervisorError("secondary cleanup failure"),
                ),
            ):
                with self.assertRaisesRegex(IdentityError, "primary identity failure"):
                    manager.start(service_path)
            record = next(iter(state.list_records()["processes"].values()))
            self.assertEqual(record["status"], "start_failed")
            self.assertEqual(record["public"]["cleanupVerified"], False)

    def test_refresh_marks_remaining_owner_as_contract_violation(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            record = state.get(key=started["processKey"])
            write_json(
                Path(record["internal"]["hostState"]),
                {
                    "capabilityHash": record["internal"]["capabilityHash"],
                    "state": "exited",
                    "exitCode": 0,
                },
            )
            with mock.patch.object(manager, "_wait_empty", side_effect=(False, True)) as wait_empty:
                refreshed = manager.status(process_key=started["processKey"])
            self.assertEqual(refreshed["state"], "contract_violation")
            self.assertEqual(refreshed["completion"]["forceRequired"], True)
            self.assertEqual(refreshed["cleanupVerified"], True)
            self.assertTrue(adapter.last_owner.empty)
            self.assertEqual(wait_empty.call_count, 2)
            manager.shutdown()

    def test_refresh_accepts_owner_that_empties_during_settlement(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            record = state.get(key=started["processKey"])
            write_json(
                Path(record["internal"]["hostState"]),
                {
                    "capabilityHash": record["internal"]["capabilityHash"],
                    "state": "exited",
                    "exitCode": 23,
                },
            )
            with mock.patch.object(manager, "_wait_empty", return_value=True) as wait_empty:
                refreshed = manager.status(process_key=started["processKey"])
            self.assertEqual(refreshed["state"], "exited")
            self.assertEqual(refreshed["completion"]["forceRequired"], False)
            self.assertFalse(adapter.last_owner.forced)
            wait_empty.assert_called_once()
            manager.shutdown()

    def test_ready_logs_restart_and_force_fallback_share_run_identity(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, _, manager, hosts = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            run_dir = Path(manager.state.get(key=started["processKey"])["runDir"])
            (run_dir / "stdout.log").write_text("first\nservice-ready\n", encoding="utf-8")
            logs = manager.logs(process_key=started["processKey"], stream="stdout", tail_lines=1)
            self.assertEqual(logs["lines"], ["service-ready"])
            ready = manager.ready(process_key=started["processKey"], timeout_seconds=1)
            self.assertTrue(ready["ready"])

            restarted = manager.restart(service_path, timeout_seconds=1)
            self.assertTrue(restarted["previous"]["cleanupVerified"])
            self.assertNotEqual(
                restarted["previous"]["processKey"],
                restarted["current"]["processKey"],
            )
            self.assertTrue(restarted["readiness"]["ready"])

            with mock.patch("helpers.FakeOwner.graceful_stop", return_value=True):
                stopped = manager.stop(process_key=restarted["current"]["processKey"])
            self.assertTrue(stopped["stopResult"]["forceRequired"])
            self.assertTrue(stopped["stopResult"]["ownerEmpty"])
            self.assertEqual(len(hosts), 2)
            manager.shutdown()

    def test_completion_watcher_persists_exit_without_status_poll(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, state, manager, hosts = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            record = state.get(key=started["processKey"])
            adapter.last_owner.empty = True
            write_json(
                Path(record["internal"]["hostState"]),
                {
                    "capabilityHash": record["internal"]["capabilityHash"],
                    "state": "exited",
                    "exitCode": 7,
                    "exitedAt": "2026-07-10T00:00:00+00:00",
                },
            )
            hosts[0].finish(7)
            deadline = time.monotonic() + 2
            while state.get(key=started["processKey"])["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            completed = state.get(key=started["processKey"])
            self.assertEqual(completed["status"], "exited")
            self.assertEqual(completed["public"]["exitCode"], 7)
            self.assertNotIn("demo", state.list_records()["active"])
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
