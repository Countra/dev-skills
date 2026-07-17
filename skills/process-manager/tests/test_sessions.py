from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, create_service, workspace_directory  # noqa: E402
import pm_session  # noqa: E402
from process_manager.errors import (  # noqa: E402
    ConflictError,
    OperationConflictError,
    SessionCleanupPendingError,
    SessionExpiredError,
    StateError,
    SupervisorError,
    ValidationError,
)
from process_manager.sessions import SessionController  # noqa: E402
from process_manager.state import StateStore  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.wall = datetime(2026, 7, 17, tzinfo=timezone.utc)
        self.monotonic = 1000.0

    def wall_now(self) -> datetime:
        return self.wall

    def monotonic_now(self) -> float:
        return self.monotonic

    def advance(self, *, wall: float, monotonic: float) -> None:
        self.wall += timedelta(seconds=wall)
        self.monotonic += monotonic


class SessionTests(unittest.TestCase):
    def make_fixture(
        self,
        workspace: Path,
        *,
        manager_id: str = "1" * 32,
        clock: FakeClock | None = None,
    ):  # noqa: ANN201
        config = create_config(workspace)
        adapter = FakeAdapter(workspace, config.state_root)
        adapter.secure_directory(config.paths.runs)
        store = StateStore(config, adapter)
        store.load()
        current_clock = clock or FakeClock()
        calls: list[str] = []
        failures: set[str] = set()

        def finalize(record, **kwargs):  # noqa: ANN001,ANN003,ANN201
            del kwargs
            key = str(record["processKey"])
            calls.append(key)
            if key in failures:
                raise SupervisorError("fixture cleanup failure")
            return store.update(
                key,
                status="stopped",
                public_updates={"ownerEmpty": True, "cleanupVerified": True},
                clear_active=True,
            )

        digest = hashlib.sha256(
            os.path.normcase(str(workspace.resolve())).encode("utf-8")
        ).hexdigest()
        controller = SessionController(
            store,
            manager_instance_id=manager_id,
            workspace_digest=digest,
            finalize_record=finalize,
            wall_clock=current_clock.wall_now,
            monotonic=current_clock.monotonic_now,
        )
        return config, adapter, store, controller, current_clock, calls, failures

    def test_open_renew_and_status_preserve_closed_schema(self) -> None:
        with workspace_directory() as directory:
            config, _, store, controller, clock, _, _ = self.make_fixture(Path(directory))
            opened = controller.open(kind="validation", ttl_seconds=1800, holder="VAL-04")
            generation = store.work_summary()["workGeneration"]
            clock.advance(wall=30, monotonic=30)
            renewed = controller.renew(opened["sessionId"], ttl_seconds=3600)
            status = controller.status(opened["sessionId"])
            self.assertEqual(renewed["revision"], 2)
            self.assertEqual(status["state"], "open")
            self.assertFalse(status["leaseExpired"])
            self.assertEqual(store.work_summary()["workGeneration"], generation)
            persisted = json.loads(
                (config.paths.sessions / f"{opened['sessionId']}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted, store.load()["sessions"][opened["sessionId"]])
            self.assertNotIn("token", json.dumps(persisted).lower())

    def test_failed_renew_does_not_extend_monotonic_deadline(self) -> None:
        with workspace_directory() as directory:
            _, _, _, controller, clock, _, _ = self.make_fixture(Path(directory))
            opened = controller.open(kind="validation", ttl_seconds=60, holder="renew-failure")
            session_id = opened["sessionId"]
            original_deadline = controller._deadlines[session_id]  # noqa: SLF001
            clock.advance(wall=10, monotonic=10)
            with (
                mock.patch.object(
                    controller,
                    "_commit_session",
                    side_effect=StateError("fixture commit failure"),
                ),
                self.assertRaisesRegex(StateError, "fixture commit failure"),
            ):
                controller.renew(session_id, ttl_seconds=1800)
            self.assertEqual(controller._deadlines[session_id], original_deadline)  # noqa: SLF001

    def test_start_requires_explicit_ownership(self) -> None:
        with self.assertRaises(ValidationError):
            SessionController.ownership(None, False)
        with self.assertRaises(ValidationError):
            SessionController.ownership("1" * 32, True)
        self.assertEqual(
            SessionController.ownership(None, True),
            {"kind": "persistent", "sessionId": None},
        )

    def test_close_isolates_other_sessions_and_persistent_runs(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store, controller, _, calls, _ = self.make_fixture(workspace)
            first = controller.open(kind="validation", ttl_seconds=1800, holder="first")
            second = controller.open(kind="task", ttl_seconds=1800, holder="second")
            first_run = controller.reserve_run(
                create_service(workspace, store.config, name="first"),
                capability_hash="a" * 64,
                session_id=first["sessionId"],
                persistent=False,
            )
            second_run = controller.reserve_run(
                create_service(workspace, store.config, name="second"),
                capability_hash="b" * 64,
                session_id=second["sessionId"],
                persistent=False,
            )
            persistent = controller.reserve_run(
                create_service(workspace, store.config, name="persistent"),
                capability_hash="c" * 64,
                session_id=None,
                persistent=True,
            )
            closed = controller.close(first["sessionId"])
            state = store.load()
            self.assertTrue(closed["cleanup"]["cleanupVerified"])
            self.assertEqual(calls, [first_run["processKey"]])
            self.assertNotIn("first", state["active"])
            self.assertIn(second_run["processKey"], state["processes"])
            self.assertIn(persistent["processKey"], state["processes"])
            self.assertEqual(state["sessions"][second["sessionId"]]["state"], "open")
            self.assertEqual(state["processes"][persistent["processKey"]]["ownership"]["kind"], "persistent")

    def test_monotonic_and_wall_clock_anomalies_cannot_extend_lease(self) -> None:
        scenarios = ((61, 61), (61, 1), (-10, 10))
        for wall_delta, monotonic_delta in scenarios:
            with self.subTest(wall=wall_delta, monotonic=monotonic_delta):
                with workspace_directory() as directory:
                    _, _, store, controller, clock, _, _ = self.make_fixture(Path(directory))
                    session = controller.open(kind="validation", ttl_seconds=60, holder="clock")
                    clock.advance(wall=wall_delta, monotonic=monotonic_delta)
                    swept = controller.sweep_once()
                    self.assertEqual(swept["closedSessionIds"], [session["sessionId"]])
                    state = store.load()
                    self.assertNotIn(session["sessionId"], state["sessions"])
                    self.assertIn(f"session:{session['sessionId']}", state["tombstones"])
                    with self.assertRaises(SessionExpiredError):
                        controller.renew(session["sessionId"], ttl_seconds=60)

    def test_sweeper_rechecks_expiry_before_committing_intent(self) -> None:
        with workspace_directory() as directory:
            _, _, store, controller, _, _, _ = self.make_fixture(Path(directory))
            session = controller.open(kind="validation", ttl_seconds=1800, holder="recheck")
            with mock.patch.object(
                controller,
                "_expiry_reason",
                side_effect=["clock_anomaly", None],
            ) as expiry:
                swept = controller.sweep_once()
            self.assertEqual(expiry.call_count, 2)
            self.assertEqual(swept["closedSessionIds"], [])
            self.assertEqual(store.load()["sessions"][session["sessionId"]]["state"], "open")

    def test_new_manager_invalidates_old_instance_session(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store, first, clock, calls, failures = self.make_fixture(workspace)
            session = first.open(kind="task", ttl_seconds=1800, holder="old-manager")
            record = first.reserve_run(
                create_service(workspace, store.config, name="owned"),
                capability_hash="d" * 64,
                session_id=session["sessionId"],
                persistent=False,
            )
            _, _, _, second, _, _, _ = self.make_fixture(
                workspace,
                manager_id="2" * 32,
                clock=clock,
            )
            second.finalize_record = first.finalize_record
            reconciled = second.reconcile_startup()
            self.assertEqual(reconciled["closedSessionIds"], [session["sessionId"]])
            self.assertIn(f"session:{session['sessionId']}", store.load()["tombstones"])
            self.assertEqual(calls, [record["processKey"]])
            self.assertEqual(failures, set())

    def test_cleanup_failure_remains_recoverable_and_never_claims_closed(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store, controller, _, calls, failures = self.make_fixture(workspace)
            session = controller.open(kind="validation", ttl_seconds=1800, holder="retry")
            record = controller.reserve_run(
                create_service(workspace, store.config, name="retry"),
                capability_hash="e" * 64,
                session_id=session["sessionId"],
                persistent=False,
            )
            failures.add(record["processKey"])
            with self.assertRaises(SessionCleanupPendingError):
                controller.close(session["sessionId"])
            pending = store.load()["sessions"][session["sessionId"]]
            self.assertEqual(pending["state"], "cleanup_failed")
            self.assertFalse(pending["cleanup"]["cleanupVerified"])
            failures.clear()
            closed = controller.close(session["sessionId"])
            self.assertEqual(closed["state"], "closed")
            self.assertEqual(calls, [record["processKey"], record["processKey"]])

    def test_renew_close_race_is_linearized(self) -> None:
        with workspace_directory() as directory:
            _, _, store, controller, _, _, _ = self.make_fixture(Path(directory))
            session = controller.open(kind="validation", ttl_seconds=1800, holder="race")
            barrier = threading.Barrier(2)
            outcomes: list[str] = []

            def renew() -> None:
                barrier.wait()
                try:
                    controller.renew(session["sessionId"], ttl_seconds=1800)
                    outcomes.append("renewed")
                except SessionExpiredError:
                    outcomes.append("expired")

            thread = threading.Thread(target=renew)
            thread.start()
            barrier.wait()
            controller.close(session["sessionId"])
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertIn(outcomes, (["renewed"], ["expired"]))
            self.assertIn(f"session:{session['sessionId']}", store.load()["tombstones"])

    def test_joint_run_session_transaction_replays_after_interruption(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store, controller, _, _, _ = self.make_fixture(workspace)
            session = controller.open(kind="validation", ttl_seconds=1800, holder="journal")
            service = create_service(workspace, config, name="journal")
            with mock.patch.object(
                store,
                "_apply_pending_transaction",
                side_effect=StateError("fixture interruption"),
            ):
                with self.assertRaisesRegex(StateError, "fixture interruption"):
                    controller.reserve_run(
                        service,
                        capability_hash="f" * 64,
                        session_id=session["sessionId"],
                        persistent=False,
                    )
            recovered = StateStore(config, adapter)
            pending = recovered.load()
            run_key = pending["sessions"][session["sessionId"]]["runKeys"][0]
            self.assertIn(run_key, pending["processes"])
            with recovered.transaction():
                pass
            disk_session = json.loads(
                (config.paths.sessions / f"{session['sessionId']}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(disk_session["runKeys"], [run_key])
            self.assertTrue(Path(pending["processes"][run_key]["processFile"]).is_file())

    def test_rebuild_restores_session_and_run_bidirectional_index(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store, controller, _, _, _ = self.make_fixture(workspace)
            session = controller.open(kind="validation", ttl_seconds=1800, holder="rebuild")
            record = controller.reserve_run(
                create_service(workspace, config, name="rebuild"),
                capability_hash="a" * 64,
                session_id=session["sessionId"],
                persistent=False,
            )
            config.paths.processes.write_text("{broken", encoding="utf-8")
            recovered = StateStore(config, adapter).load()
            self.assertEqual(
                recovered["sessions"][session["sessionId"]]["runKeys"],
                [record["processKey"]],
            )
            self.assertEqual(
                recovered["processes"][record["processKey"]]["ownership"]["sessionId"],
                session["sessionId"],
            )

    def test_rebuild_prefers_session_only_records_over_stale_backup(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, _, controller, _, _, _ = self.make_fixture(workspace)
            session = controller.open(kind="validation", ttl_seconds=1800, holder="session-only")
            config.paths.processes.write_text("{broken", encoding="utf-8")
            recovered = StateStore(config, adapter).load()
            self.assertEqual(
                recovered["sessions"][session["sessionId"]]["holder"],
                "session-only",
            )

    def test_rebuild_rejects_session_record_above_closed_cap(self) -> None:
        with workspace_directory() as directory:
            _, _, store, _, _, _, _ = self.make_fixture(Path(directory))
            path = store.schema.session_path("f" * 32)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * (64 * 1024 + 1))
            with self.assertRaisesRegex(StateError, "读取上限"):
                store.rebuild()

    def test_session_schema_rejects_invalid_time_and_state_combinations(self) -> None:
        with workspace_directory() as directory:
            _, _, store, controller, _, _, _ = self.make_fixture(Path(directory))
            session = controller.open(kind="validation", ttl_seconds=1800, holder="schema")
            persisted = store.load()["sessions"][session["sessionId"]]
            invalid_time = dict(persisted)
            invalid_time["expiresAt"] = "not-a-time"
            with self.assertRaisesRegex(StateError, "RFC3339"):
                store.schema.validate_session(session["sessionId"], invalid_time)
            invalid_state = dict(persisted)
            invalid_state["closingReason"] = "unexpected"
            with self.assertRaisesRegex(StateError, "open session"):
                store.schema.validate_session(session["sessionId"], invalid_state)

    def test_sweeper_isolates_one_cleanup_failure(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store, controller, clock, _, failures = self.make_fixture(workspace)
            sessions = []
            run_keys = []
            for name in ("bad", "good"):
                session = controller.open(kind="validation", ttl_seconds=60, holder=name)
                record = controller.reserve_run(
                    create_service(workspace, store.config, name=name),
                    capability_hash=name * 16,
                    session_id=session["sessionId"],
                    persistent=False,
                )
                sessions.append(session)
                run_keys.append(record["processKey"])
            failures.add(run_keys[0])
            clock.advance(wall=61, monotonic=61)
            result = controller.sweep_once()
            state = store.load()
            states = {}
            for session in sessions:
                record = state["sessions"].get(session["sessionId"])
                states[session["holder"]] = record["state"] if record else "closed"
            self.assertEqual(states, {"bad": "cleanup_failed", "good": "closed"})
            self.assertEqual(result["closedSessionIds"], [sessions[1]["sessionId"]])
            self.assertTrue(result["errors"])

    def test_idle_stop_generation_rejects_concurrent_new_session(self) -> None:
        with workspace_directory() as directory:
            _, _, store, controller, _, _, _ = self.make_fixture(Path(directory))
            first = controller.open(kind="validation", ttl_seconds=1800, holder="first")
            generation = controller.close(first["sessionId"])["workGeneration"]
            second = controller.open(kind="task", ttl_seconds=1800, holder="second")
            with self.assertRaises(ConflictError):
                store.install_intake_fence(
                    operation_id="3" * 32,
                    kind="stop",
                    expected_generation=generation,
                    require_idle=True,
                )
            current = controller.close(second["sessionId"])["workGeneration"]
            fence = store.install_intake_fence(
                operation_id="4" * 32,
                kind="stop",
                expected_generation=current,
                require_idle=True,
            )
            self.assertEqual(fence["expectedWorkGeneration"], current)
            store.clear_intake_fence("4" * 32)

    def test_session_cli_retains_manager_when_conditional_stop_loses_race(self) -> None:
        value = {
            "ok": True,
            "operation": "sessions.close",
            "data": {"sessionId": "1" * 32, "state": "closed", "workGeneration": 7},
            "error": None,
            "meta": {},
        }
        client = mock.Mock()
        client.request.return_value = (200, value)
        converger = mock.Mock()
        converger.stop.side_effect = OperationConflictError("generation changed")
        with (
            mock.patch.object(pm_session, "make_client", return_value=client),
            mock.patch.object(pm_session, "resolve_runtime_context", return_value=object()),
            mock.patch.object(pm_session, "ManagerConverger", return_value=converger),
            mock.patch.object(pm_session, "print_json") as output,
        ):
            result = pm_session.main(
                [
                    "close",
                    "--config",
                    "manager.json",
                    "--session-id",
                    "1" * 32,
                    "--stop-manager-if-idle",
                ]
            )
        self.assertEqual(result, 0)
        converger.stop.assert_called_once_with(
            timeout=12.0,
            expected_work_generation=7,
            require_idle=True,
        )
        self.assertTrue(value["data"]["managerRetained"])
        self.assertEqual(value["data"]["idleStop"]["state"], "precondition_changed")
        output.assert_called_once_with(value, pretty=False)


if __name__ == "__main__":
    unittest.main()
