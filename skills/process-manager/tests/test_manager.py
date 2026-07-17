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
from process_manager.errors import (  # noqa: E402
    ConflictError,
    IdentityError,
    NotFoundError,
    SupervisorError,
    ValidationError,
)
from process_manager.manager import ProcessManager  # noqa: E402
from process_manager.run_finalization import OwnerFinalization  # noqa: E402
from process_manager.state import ACTIVE_STATES, StateStore  # noqa: E402


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
                        "event": "target_spawned",
                        "capabilityHash": self.host.capability_hash,
                        "target": {"pid": 4343, "pgid": 4343},
                    }
                )
                + "\n"
            )
        if self.index == 3:
            identity = json.loads(self.host.stdin.getvalue().splitlines()[-1])
            return (
                json.dumps(
                    {
                        "event": "target_started",
                        "capabilityHash": self.host.capability_hash,
                        "target": {"pid": 4343, "pgid": 4343},
                        "targetIdentity": identity["targetIdentity"],
                        "ownerIdentity": identity["ownerIdentity"],
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
        manager = ProcessManager(
            config,
            adapter,
            state,
            "1" * 32,
            operation_id="00000000000000000000000000000000",
            session_sweeper=False,
        )
        start = manager.start

        def persistent_start(path, **kwargs):  # noqa: ANN001,ANN003,ANN201
            kwargs.setdefault("persistent", True)
            return start(path, **kwargs)

        manager.start = persistent_start  # type: ignore[method-assign]
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

    def test_stop_reconciles_run_from_prior_manager_identity(self) -> None:
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
            stopped = manager.stop(process_key=started["processKey"])
            self.assertTrue(stopped["cleanupVerified"])
            self.assertEqual(stopped["state"], "stopped")
            manager.shutdown()

    def test_health_contract_is_platform_neutral(self) -> None:
        with workspace_directory() as directory:
            _, _, _, manager, _ = self.make_manager(Path(directory))
            value = manager.health()
            self.assertEqual(
                set(value),
            {
                "managerReady",
                "supervisorReady",
                "instance",
                "operationId",
                "runtimeFingerprint",
                "endpointHealthy",
            },
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
            _, adapter, state, manager, hosts = self.make_manager(workspace)
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
            self.assertEqual(record["status"], "terminating")
            self.assertEqual(record["public"]["cleanupVerified"], False)
            self.assertEqual(record["public"]["cleanupError"], "start_cleanup_failed")
            adapter.last_owner.empty = True
            hosts[0].finish(1)

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
            with mock.patch.object(
                manager._finalization.owner_finalizer,  # noqa: SLF001
                "_wait_live",
                side_effect=(False, True),
            ) as wait_empty:
                refreshed = manager.status(process_key=started["processKey"])
            self.assertEqual(refreshed["state"], "contract_violation")
            self.assertEqual(refreshed["stopResult"]["forceRequired"], True)
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
            with mock.patch.object(
                manager._finalization.owner_finalizer,  # noqa: SLF001
                "_wait_live",
                return_value=True,
            ) as wait_empty:
                refreshed = manager.status(process_key=started["processKey"])
            self.assertEqual(refreshed["state"], "exited")
            self.assertEqual(refreshed["stopResult"]["forceRequired"], False)
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

    def test_start_requires_ownership_and_restart_preserves_it(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            with self.assertRaises(ValidationError):
                ProcessManager.start(manager, service_path)
            session = manager.open_session(
                kind="validation",
                ttl_seconds=1800,
                holder="manager-ownership-test",
            )
            started = ProcessManager.start(
                manager,
                service_path,
                session_id=session["sessionId"],
            )
            self.assertEqual(
                state.get(key=started["processKey"])["ownership"],
                {"kind": "session", "sessionId": session["sessionId"]},
            )
            with self.assertRaises(ValidationError):
                manager.restart(service_path, persistent=True)
            restarted = manager.restart(service_path)
            self.assertEqual(
                state.get(key=restarted["current"]["processKey"])["ownership"],
                {"kind": "session", "sessionId": session["sessionId"]},
            )
            closed = manager.close_session(session["sessionId"])
            self.assertTrue(closed["cleanup"]["cleanupVerified"])
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
            while (
                state.get(key=started["processKey"])["status"] in ACTIVE_STATES
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            completed = state.get(key=started["processKey"])
            self.assertEqual(completed["status"], "exited")
            self.assertEqual(completed["public"]["exitCode"], 7)
            self.assertNotIn("demo", state.list_records()["active"])
            manager.shutdown()

    def test_manager_shutdown_cleans_persisted_run_missing_from_memory(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            with manager._lock:  # noqa: SLF001
                manager._runs.pop(started["processKey"])  # noqa: SLF001
            shutdown = manager.shutdown()
            self.assertEqual(shutdown["stoppedRunKeys"], [started["processKey"]])
            self.assertTrue(shutdown["cleanupVerified"])
            persisted = state.get(key=started["processKey"])
            self.assertEqual(persisted["status"], "stopped")
            self.assertTrue(persisted["public"]["ownerEmpty"])

    def test_persisted_finalization_is_serialized_per_run(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, _, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            with manager._lock:  # noqa: SLF001
                manager._runs.pop(started["processKey"])  # noqa: SLF001
            entered = threading.Event()
            release = threading.Event()
            calls = 0

            def finalize_persisted(*args, **kwargs):  # noqa: ANN002,ANN003,ANN201
                nonlocal calls
                del args, kwargs
                calls += 1
                entered.set()
                release.wait(2)
                return OwnerFinalization(True, True, True, False, False, {}, None)

            results: list[dict[str, object]] = []
            errors: list[BaseException] = []

            def stop() -> None:
                try:
                    results.append(manager.stop(process_key=started["processKey"]))
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            with mock.patch.object(
                manager._finalization.owner_finalizer,  # noqa: SLF001
                "finalize_persisted",
                side_effect=finalize_persisted,
            ):
                first = threading.Thread(target=stop)
                second = threading.Thread(target=stop)
                first.start()
                self.assertTrue(entered.wait(1))
                second.start()
                time.sleep(0.05)
                self.assertEqual(calls, 1)
                release.set()
                first.join(timeout=2)
                second.join(timeout=2)
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertEqual(calls, 1)

    def test_new_manager_reconciles_old_persisted_owner_before_accepting_start(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, state, manager, _ = self.make_manager(workspace)
            service_path = workspace / "service.json"
            write_json(service_path, service_value(workspace))
            started = manager.start(service_path)
            with manager._lock:  # noqa: SLF001
                manager._runs.pop(started["processKey"])  # noqa: SLF001
            replacement = ProcessManager(
                config,
                adapter,
                state,
                "2" * 32,
                operation_id="11111111111111111111111111111111",
                session_sweeper=False,
            )
            persisted = state.get(key=started["processKey"])
            self.assertEqual(persisted["status"], "manager_lost")
            self.assertTrue(persisted["public"]["cleanupVerified"])
            self.assertEqual(
                replacement.reconciled_records["finalized"],
                [started["processKey"]],
            )
            replacement.shutdown()

    def test_shutdown_waits_for_an_already_admitted_start(self) -> None:
        with workspace_directory() as directory:
            _, _, _, manager, _ = self.make_manager(Path(directory))
            entered = threading.Event()
            release = threading.Event()
            start_result: list[dict[str, object]] = []
            shutdown_result: list[dict[str, object]] = []

            def blocked_start(service_path: Path, ownership: dict[str, object]) -> dict[str, object]:
                del service_path, ownership
                entered.set()
                release.wait(2)
                return {"state": "running"}

            with mock.patch.object(manager, "_start", side_effect=blocked_start):
                start_thread = threading.Thread(
                    target=lambda: start_result.append(manager.start(Path("service.json")))
                )
                start_thread.start()
                self.assertTrue(entered.wait(1))
                manager.accept_shutdown(operation_id="0" * 32, timeout_seconds=2)
                shutdown_thread = threading.Thread(target=lambda: shutdown_result.append(manager.shutdown()))
                shutdown_thread.start()
                time.sleep(0.05)
                self.assertTrue(shutdown_thread.is_alive())
                release.set()
                start_thread.join(timeout=2)
                shutdown_thread.join(timeout=2)

            self.assertFalse(start_thread.is_alive())
            self.assertFalse(shutdown_thread.is_alive())
            self.assertEqual(start_result, [{"state": "running"}])
            self.assertTrue(shutdown_result[0]["cleanupVerified"])

    def test_shutdown_rejects_a_live_completion_watcher(self) -> None:
        class StubbornWatcher:
            name = "pm-watch-stubborn"

            @staticmethod
            def join(timeout=None) -> None:  # noqa: ANN001
                del timeout

            @staticmethod
            def is_alive() -> bool:
                return True

        with workspace_directory() as directory:
            _, _, _, manager, _ = self.make_manager(Path(directory))
            with manager._lock:  # noqa: SLF001
                manager._watchers["fixture"] = StubbornWatcher()  # type: ignore[assignment]  # noqa: SLF001
            manager.accept_shutdown(operation_id="0" * 32, timeout_seconds=1)
            with self.assertRaises(SupervisorError) as raised:
                manager.shutdown()
            self.assertEqual(
                raised.exception.diagnostics["liveWatchers"],
                ["pm-watch-stubborn"],
            )


if __name__ == "__main__":
    unittest.main()
