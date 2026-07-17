from __future__ import annotations

import json
import shutil
import sys
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, create_service, workspace_directory, write_json  # noqa: E402
from process_manager.client import _remember_busy  # noqa: E402, PLC2701
from process_manager.config import load_manager_config  # noqa: E402
from process_manager.errors import (  # noqa: E402
    ConflictError,
    ResourceBudgetError,
    ResourceUsageUnverifiableError,
    RuntimeCorruptError,
    RuntimeInsecureError,
    StateError,
    ValidationError,
)
from process_manager.logs import (  # noqa: E402
    RESOURCE_CAPS,
    RotatingTextLog,
    RuntimeAccountant,
    RuntimeUsage,
    write_capped_bytes,
)
from process_manager.protocol import (  # noqa: E402
    ControlRequestGate,
    control_busy_envelope,
    control_timeout_envelope,
    verify_control_busy,
)
from process_manager.resources import PruneCoordinator, ResourceGovernor  # noqa: E402
from process_manager.runtime import now_text  # noqa: E402
from process_manager.sessions import SessionController  # noqa: E402
from process_manager.state import StateStore  # noqa: E402


class FakeSocket:
    def __init__(self) -> None:
        self.timeout = None
        self.sent = b""

    def settimeout(self, value):  # noqa: ANN001,ANN201
        self.timeout = value

    def sendall(self, value):  # noqa: ANN001,ANN201
        self.sent += value

    def recv(self, size):  # noqa: ANN001,ANN201,ARG002
        raise AssertionError("saturation gate 不得读取 request body")


class ResourceTests(unittest.TestCase):
    def make_store(self, workspace: Path):  # noqa: ANN201
        config = create_config(workspace)
        adapter = FakeAdapter(workspace, config.state_root)
        store = StateStore(config, adapter)
        store.load()
        return config, adapter, store

    @staticmethod
    def set_limits(store: StateStore, **updates: int) -> None:
        limits = {**store.config.limits, **updates}
        store.config = replace(store.config, limits=limits)

    def terminal(self, store: StateStore, workspace: Path, name: str):  # noqa: ANN201
        service = create_service(workspace, store.config, name=name)
        record = store.reserve(
            service,
            manager_instance_id="manager",
            capability_hash="a" * 64,
            ownership={"kind": "persistent", "sessionId": None},
        )
        return store.update(
            record["processKey"],
            status="stopped",
            clear_active=True,
            public_updates={
                "ownerEmpty": True,
                "cleanupVerified": True,
                "finalizedAt": now_text(),
            },
        )

    def controller(self, store: StateStore):  # noqa: ANN201
        def finalize(record, **kwargs):  # noqa: ANN001,ANN003,ANN202
            return store.update(
                record["processKey"],
                status=kwargs["terminal_status"],
                clear_active=True,
                public_updates={
                    "ownerEmpty": True,
                    "cleanupVerified": True,
                    "finalizedAt": now_text(),
                },
            )

        return SessionController(
            store,
            manager_instance_id="1" * 32,
            workspace_digest="2" * 64,
            finalize_record=finalize,
        )

    def test_default_config_closes_resource_limits(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            self.assertEqual(config.limits["maxActiveRuns"], 16)
            self.assertEqual(config.history_max_age_seconds, 604800)
            value = json.loads(config.config_path.read_text(encoding="utf-8"))
            value["limits"]["maxSessionRecords"] = 1
            value["limits"]["maxOpenSessions"] = 2
            write_json(config.config_path, value)
            with self.assertRaises(ValidationError):
                load_manager_config(config.config_path)

    def test_resource_summary_uses_one_total_reservation(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            governor = ResourceGovernor(store)
            summary = governor.summary()
            self.assertEqual(
                set(summary),
                {
                    "activeRuns", "terminatingRuns", "openSessions", "expiredSessions",
                    "sessionRecords", "inactiveRuns", "pendingPrunes",
                    "activeControlRequests", "usedBytes", "reservedBytes", "limitBytes",
                    "cleanupPending", "overBudget",
                },
            )
            self.assertLessEqual(summary["usedBytes"], summary["reservedBytes"])
            service = create_service(workspace, store.config, name="budget")
            capacity = governor.start_capacity(service)
            self.set_limits(store, maxRetainedBytes=summary["reservedBytes"] + capacity - 1)
            with self.assertRaises(ResourceBudgetError):
                store.reserve(
                    service,
                    manager_instance_id="manager",
                    capability_hash="b" * 64,
                    ownership={"kind": "persistent", "sessionId": None},
                )

    def test_count_admission_rejects_without_mutating_state(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            self.set_limits(store, maxActiveRuns=1)
            first = create_service(workspace, store.config, name="first")
            second = create_service(workspace, store.config, name="second")
            store.reserve(
                first,
                manager_instance_id="manager",
                capability_hash="c" * 64,
                ownership={"kind": "persistent", "sessionId": None},
            )
            before = store.load()["stateRevision"]
            with self.assertRaises(ResourceBudgetError):
                store.reserve(
                    second,
                    manager_instance_id="manager",
                    capability_hash="d" * 64,
                    ownership={"kind": "persistent", "sessionId": None},
                )
            self.assertEqual(store.load()["stateRevision"], before)

    def test_terminal_actual_and_active_capacity_share_one_limit(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            terminal = self.terminal(store, workspace, "terminal")
            terminal = store.update(
                terminal["processKey"],
                status="stopped",
                public_updates={
                    "ownerEmpty": False,
                    "cleanupVerified": False,
                    "finalizedAt": None,
                },
            )
            (Path(terminal["runDir"]) / "retained.bin").write_bytes(b"x" * 128)
            governor = ResourceGovernor(store)
            current = governor.summary()
            service = create_service(workspace, store.config, name="candidate")
            self.set_limits(
                store,
                maxRetainedBytes=current["reservedBytes"] + governor.start_capacity(service) - 1,
            )
            with self.assertRaises(ResourceBudgetError):
                store.reserve(
                    service,
                    manager_instance_id="manager",
                    capability_hash="e" * 64,
                    ownership={"kind": "persistent", "sessionId": None},
                )
            self.assertIn(terminal["processKey"], store.load()["processes"])

    def test_session_count_admission_and_compact_tombstone(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            self.set_limits(store, maxOpenSessions=1)
            controller = self.controller(store)
            opened = controller.open(kind="validation", ttl_seconds=60, holder="first")
            with self.assertRaises(ResourceBudgetError):
                controller.open(kind="validation", ttl_seconds=60, holder="second")
            closed = controller.close(opened["sessionId"])
            state = store.load()
            self.assertEqual(closed["state"], "closed")
            self.assertNotIn(opened["sessionId"], state["sessions"])
            self.assertIn(f"session:{opened['sessionId']}", state["tombstones"])
            self.assertIsInstance(
                state["tombstones"][f"session:{opened['sessionId']}"]["updatedAt"],
                str,
            )
            self.assertFalse(store.schema.session_path(opened["sessionId"]).exists())
            self.assertEqual(controller.status(opened["sessionId"])["state"], "closed")
            self.assertEqual(controller.close(opened["sessionId"])["state"], "closed")

    def test_heavy_session_record_cap_rejects_new_session(self) -> None:
        with workspace_directory() as directory:
            _, _, store = self.make_store(Path(directory))
            self.set_limits(store, maxOpenSessions=1, maxSessionRecords=1)
            controller = self.controller(store)
            opened = controller.open(kind="validation", ttl_seconds=60, holder="heavy")
            with store.transaction():
                state = store.load()
                session = dict(state["sessions"][opened["sessionId"]])
                session.update(
                    {
                        "revision": int(session["revision"]) + 1,
                        "state": "terminating",
                        "closingReason": "fixture_pending_cleanup",
                    }
                )
                state["sessions"][opened["sessionId"]] = session
                state["workGeneration"] += 1
                store.commit_repository(state, sessions=[session])
            with self.assertRaises(ResourceBudgetError):
                controller.open(kind="validation", ttl_seconds=60, holder="rejected")
            self.assertEqual(set(store.load()["sessions"]), {opened["sessionId"]})

    def test_session_deletion_replays_after_interruption(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store = self.make_store(workspace)
            controller = self.controller(store)
            opened = controller.open(kind="task", ttl_seconds=60, holder="replay")
            session_path = store.schema.session_path(opened["sessionId"])
            original = store._apply_pending_transaction  # noqa: SLF001

            def interrupt(value):  # noqa: ANN001,ANN202
                if value["deleteSessions"]:
                    raise StateError("fixture deletion interruption")
                return original(value)

            with mock.patch.object(store, "_apply_pending_transaction", side_effect=interrupt):
                with self.assertRaisesRegex(StateError, "deletion interruption"):
                    controller.close(opened["sessionId"])
            self.assertTrue(session_path.is_file())
            recovered = StateStore(config, adapter)
            self.assertIn(f"session:{opened['sessionId']}", recovered.load()["tombstones"])
            pending = ResourceGovernor(recovered).diagnostics()
            self.assertEqual(pending["cleanupPending"], 1)
            self.assertGreaterEqual(pending["fixedActualBytes"], session_path.stat().st_size)
            with recovered.transaction():
                pass
            self.assertFalse(session_path.exists())
            self.assertFalse(config.paths.state_root.joinpath("processes.pending.json").exists())

    def test_used_over_reserved_and_unverifiable_fail_closed(self) -> None:
        with workspace_directory() as directory:
            _, _, store = self.make_store(Path(directory))
            governor = ResourceGovernor(store)
            usage = RuntimeUsage(used=101, fixed=100)
            with mock.patch("process_manager.resources.RuntimeAccountant.measure", return_value=usage):
                details = governor.measure(store.load())
                self.assertTrue(details["overBudget"])
                with self.assertRaises(ResourceBudgetError):
                    governor._admit(store.load(), 1, kind="fixture")  # noqa: SLF001
            error = ResourceUsageUnverifiableError("fixture")
            public_keys = set(governor.summary())
            with mock.patch("process_manager.resources.RuntimeAccountant.measure", side_effect=error):
                summary = governor.summary(strict=False)
                self.assertEqual(set(summary), public_keys)
                self.assertIsNone(summary["usedBytes"])
                self.assertTrue(summary["overBudget"])

    def test_prune_never_selects_active_or_unverified_terminal(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            active_service = create_service(workspace, store.config, name="active")
            active = store.reserve(
                active_service,
                manager_instance_id="manager",
                capability_hash="e" * 64,
                ownership={"kind": "persistent", "sessionId": None},
            )
            eligible = self.terminal(store, workspace, "eligible")
            unverified_service = create_service(workspace, store.config, name="unverified")
            unverified = store.reserve(
                unverified_service,
                manager_instance_id="manager",
                capability_hash="f" * 64,
                ownership={"kind": "persistent", "sessionId": None},
            )
            unverified = store.update(
                unverified["processKey"], status="stopped", clear_active=True
            )
            result = store.prune(max_inactive=0, dry_run=False)
            state = store.load()
            self.assertEqual(result["prunedCount"], 1)
            self.assertIn(active["processKey"], state["processes"])
            self.assertIn(unverified["processKey"], state["processes"])
            self.assertNotIn(eligible["processKey"], state["processes"])
            self.assertIsInstance(
                state["tombstones"][f"run:{eligible['processKey']}"]["updatedAt"],
                str,
            )

    def test_prune_recovers_every_persisted_phase(self) -> None:
        for phase in ("intent", "moved-intent", "quarantined", "committed"):
            with self.subTest(phase=phase), workspace_directory() as directory:
                workspace = Path(directory)
                _, _, store = self.make_store(workspace)
                record = self.terminal(store, workspace, phase)
                coordinator = PruneCoordinator(store)
                size = coordinator._tree_bytes(record)  # noqa: SLF001
                journal = coordinator._save_intent(record, size, False)  # noqa: SLF001
                if phase != "intent":
                    coordinator._move(journal)  # noqa: SLF001
                if phase in {"quarantined", "committed"}:
                    journal = coordinator._phase(  # noqa: SLF001
                        journal["transactionId"], "quarantined"
                    )
                if phase == "committed":
                    coordinator._commit(journal)  # noqa: SLF001
                self.assertIsInstance(ResourceGovernor(store).summary()["usedBytes"], int)
                recovered = coordinator.recover_pending()
                state = store.load()
                self.assertTrue(recovered["cleanupVerified"])
                self.assertEqual(state["pendingPrunes"], {})
                self.assertNotIn(record["processKey"], state["processes"])
                self.assertIn(f"run:{record['processKey']}", state["tombstones"])
                self.assertFalse(Path(record["runDir"]).exists())
                prune_root = store.paths.tmp / "prune"
                self.assertEqual(list(prune_root.iterdir()) if prune_root.exists() else [], [])

    def test_dry_run_does_not_recover_pending_journal(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "dry")
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                record, coordinator._tree_bytes(record), False  # noqa: SLF001
            )
            result = coordinator.run(max_inactive=0, dry_run=True, keep_runs=False)
            self.assertFalse(result["recovery"]["cleanupVerified"])
            self.assertIn(journal["transactionId"], store.load()["pendingPrunes"])

    def test_pending_prune_cap_preserves_existing_evidence(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            first = self.terminal(store, workspace, "first")
            second = self.terminal(store, workspace, "second")
            self.set_limits(store, maxPendingPrunes=1)
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                first, coordinator._tree_bytes(first), False  # noqa: SLF001
            )
            with self.assertRaises(ResourceBudgetError):
                coordinator._save_intent(  # noqa: SLF001
                    second, coordinator._tree_bytes(second), False  # noqa: SLF001
                )
            self.assertEqual(set(store.load()["pendingPrunes"]), {journal["transactionId"]})

    def test_prune_cleanup_failure_keeps_recoverable_receipt(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "cleanup-failure")
            with mock.patch(
                "process_manager.resources.shutil.rmtree",
                side_effect=OSError("fixture"),
            ):
                result = store.prune(max_inactive=0, dry_run=False)
            self.assertFalse(result["cleanupVerified"])
            state = store.load()
            journal = next(iter(state["pendingPrunes"].values()))
            self.assertEqual(journal["phase"], "committed")
            self.assertTrue(journal["cleanupPending"])
            self.assertIn(f"run:{record['processKey']}", state["tombstones"])
            recovered = PruneCoordinator(store).recover_pending()
            self.assertTrue(recovered["cleanupVerified"])
            self.assertEqual(store.load()["pendingPrunes"], {})
            prune_root = store.paths.tmp / "prune"
            self.assertEqual(list(prune_root.iterdir()) if prune_root.exists() else [], [])

    def test_prune_move_failure_keeps_intent_for_recovery(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "move-failure")
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                record, coordinator._tree_bytes(record), False  # noqa: SLF001
            )
            with (
                mock.patch("pathlib.Path.replace", side_effect=OSError("fixture")),
                self.assertRaisesRegex(OSError, "fixture"),
            ):
                coordinator._move(journal)  # noqa: SLF001
            self.assertTrue(Path(record["runDir"]).is_dir())
            self.assertEqual(
                store.load()["pendingPrunes"][journal["transactionId"]]["phase"], "intent"
            )
            self.assertTrue(coordinator.recover_pending()["cleanupVerified"])
            self.assertFalse(Path(record["runDir"]).exists())

    def test_resource_schema_binds_journal_to_exact_paths(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "bound")
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                record, coordinator._tree_bytes(record), False  # noqa: SLF001
            )
            state = store.load()
            state["pendingPrunes"][journal["transactionId"]]["source"] = "logs"
            with self.assertRaisesRegex(StateError, "exact transaction/process identity"):
                store.schema.validate_state(state)

    def test_resource_schema_closes_journal_phase_evidence(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "phase-bound")
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                record, coordinator._tree_bytes(record), False  # noqa: SLF001
            )
            state = store.load()
            state["pendingPrunes"][journal["transactionId"]].update(
                {"phase": "committed", "cleanupPending": True}
            )
            with self.assertRaisesRegex(StateError, "唯一 tombstone"):
                store.schema.validate_state(state)
            state = store.load()
            state["pendingPrunes"][journal["transactionId"]]["cleanupPending"] = True
            with self.assertRaisesRegex(StateError, "cleanupPending"):
                store.schema.validate_state(state)

    def test_automatic_gc_compacts_completed_tombstones_after_limit_drop(self) -> None:
        with workspace_directory() as directory:
            _, _, store = self.make_store(Path(directory))
            controller = self.controller(store)
            for holder in ("first", "second"):
                opened = controller.open(kind="validation", ttl_seconds=60, holder=holder)
                controller.close(opened["sessionId"])
            self.assertEqual(len(store.load()["tombstones"]), 2)
            store.config = replace(store.config, history_max_tombstones=1)
            result = ResourceGovernor(store).automatic_gc()
            self.assertEqual(result["tombstonesCompacted"], 1)
            self.assertEqual(len(store.load()["tombstones"]), 1)

    def test_history_count_and_age_are_hard_budget_signals(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            records = [self.terminal(store, workspace, name) for name in ("old", "new-a", "new-b")]
            old_stamp = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            store.update(
                records[0]["processKey"],
                status="stopped",
                public_updates={"finalizedAt": old_stamp},
            )
            store.config = replace(
                store.config,
                history_max_inactive=2,
                history_max_age_seconds=7 * 24 * 60 * 60,
            )
            before = ResourceGovernor(store).diagnostics()
            self.assertEqual(before["expiredHistoryRuns"], 1)
            self.assertTrue(before["overBudget"])
            result = ResourceGovernor(store).automatic_gc()
            state = store.load()
            self.assertEqual(result["prunedCount"], 1)
            self.assertNotIn(records[0]["processKey"], state["processes"])
            self.assertFalse(ResourceGovernor(store).diagnostics()["overBudget"])
            prune_root = store.paths.tmp / "prune"
            self.assertEqual(list(prune_root.iterdir()) if prune_root.exists() else [], [])

    def test_gc_limits_tree_measurements_to_candidate_batch(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            for index in range(6):
                self.terminal(store, workspace, f"bounded-{index}")
            coordinator = PruneCoordinator(store)
            with mock.patch.object(coordinator, "_tree_bytes", return_value=1) as measure:
                selected = coordinator._plan(  # noqa: SLF001
                    store.load(), limit=0, required_bytes=100, max_candidates=3
                )
            self.assertEqual(len(selected), 3)
            self.assertEqual(measure.call_count, 3)

    def test_tree_accounting_fails_closed_at_entry_limit(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            root = store.paths.tmp / "bounded-tree"
            root.mkdir(parents=True)
            for index in range(5):
                (root / f"{index}.txt").write_text("x", encoding="utf-8")
            accountant = RuntimeAccountant(
                store,
                {"processes": {}, "sessions": {}, "pendingPrunes": {}, "tombstones": {}},
            )
            with self.assertRaisesRegex(ResourceUsageUnverifiableError, "bounded limit"):
                accountant.tree_bytes(root, max_entries=4)

    def test_tree_accounting_closes_depth_deadline_link_and_global_budget(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, adapter, store = self.make_store(workspace)
            root = store.paths.tmp / "bounded-shapes"
            nested = root / "one" / "two"
            nested.mkdir(parents=True)
            (nested / "value.txt").write_text("x", encoding="utf-8")
            state = {"processes": {}, "sessions": {}, "pendingPrunes": {}, "tombstones": {}}
            with self.assertRaisesRegex(ResourceUsageUnverifiableError, "bounded limit"):
                RuntimeAccountant(store, state).tree_bytes(root, max_depth=1)
            with mock.patch("process_manager.logs.time.monotonic", side_effect=[0.0, 0.0, 1.0]):
                with self.assertRaisesRegex(ResourceUsageUnverifiableError, "bounded limit"):
                    RuntimeAccountant(store, state).tree_bytes(root)
            linked = root / "linked"
            linked.write_text("x", encoding="utf-8")
            validate = adapter.validate_runtime_path

            def reject_link(path):  # noqa: ANN001,ANN202
                if Path(path).name == "linked":
                    raise RuntimeInsecureError("fixture reparse point")
                return validate(path)

            with mock.patch.object(adapter, "validate_runtime_path", side_effect=reject_link):
                with self.assertRaises(RuntimeInsecureError):
                    RuntimeAccountant(store, state).tree_bytes(root)
            accountant = RuntimeAccountant(store, state)
            accountant._deadline = -1  # noqa: SLF001
            with self.assertRaisesRegex(ResourceUsageUnverifiableError, "全局工作预算"):
                accountant.measure()

    def test_launchd_residue_is_counted_and_capped(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            governor = ResourceGovernor(store)
            before = governor.summary()["usedBytes"]
            path = store.paths.state_root / "manager-launchd.plist"
            write_capped_bytes(path, b"launchd", RESOURCE_CAPS["bootstrap"])
            store.adapter.secure_file(path)
            self.assertEqual(governor.summary()["usedBytes"], before + 7)
            with self.assertRaisesRegex(StateError, "写入上限"):
                write_capped_bytes(path, b"oversized", 4)

    def test_manager_config_is_counted_and_capped(self) -> None:
        with workspace_directory() as directory:
            _, _, store = self.make_store(Path(directory))
            governor = ResourceGovernor(store)
            before = governor.summary()["usedBytes"]
            original = store.config.config_path.read_bytes()
            store.config.config_path.write_bytes(original + b" \n")
            self.assertEqual(governor.summary()["usedBytes"], before + 2)
            store.config.config_path.write_bytes(b"x" * (RESOURCE_CAPS["config"] + 1))
            with self.assertRaisesRegex(ResourceUsageUnverifiableError, "metadata cap"):
                governor.summary()

    def test_committed_prune_recovers_after_quarantine_was_deleted(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "deleted-before-journal-clear")
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                record, coordinator._tree_bytes(record), False  # noqa: SLF001
            )
            coordinator._move(journal)  # noqa: SLF001
            journal = coordinator._phase(  # noqa: SLF001
                journal["transactionId"], "quarantined"
            )
            journal = coordinator._commit(journal)  # noqa: SLF001
            _, quarantine = coordinator._paths(journal)  # noqa: SLF001
            shutil.rmtree(quarantine)
            self.assertIsInstance(ResourceGovernor(store).summary()["usedBytes"], int)
            self.assertTrue(coordinator.recover_pending()["cleanupVerified"])
            self.assertEqual(store.load()["pendingPrunes"], {})

    def test_manager_log_rotation_and_generation_limit(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, _ = self.make_store(workspace)
            path = config.paths.logs / "manager-stdout.log"
            writer = RotatingTextLog(path, 8, 1, adapter)
            writer.write("12345678")
            writer.write("abcdef")
            writer.close()
            self.assertEqual(path.read_text(encoding="utf-8"), "abcdef")
            self.assertEqual(path.with_name(path.name + ".1").read_text(encoding="utf-8"), "12345678")
            path.with_name(path.name + ".2").write_text("overflow", encoding="utf-8")
            with self.assertRaisesRegex(StateError, "generation"):
                RotatingTextLog(path, 8, 1, adapter)

    def test_manager_log_rotation_failure_closes_writer(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, _ = self.make_store(workspace)
            writer = RotatingTextLog(config.paths.logs / "manager-stderr.log", 8, 1, adapter)
            writer.write("12345678")
            with (
                mock.patch.object(adapter, "secure_file", side_effect=StateError("fixture")),
                self.assertRaisesRegex(StateError, "fixture"),
            ):
                writer.write("x")
            self.assertTrue(writer._handle.closed)  # noqa: SLF001
            with self.assertRaisesRegex(StateError, "失败状态"):
                writer.write("y")
            writer.close()

    def test_manager_log_rotation_fault_never_appends_past_limit(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, _ = self.make_store(workspace)
            path = config.paths.logs / "manager-fault.log"
            writer = RotatingTextLog(path, 8, 1, adapter)
            writer.write("12345678")
            with (
                mock.patch(
                    "process_manager.logs.retry_windows_file_operation",
                    side_effect=StateError("fixture rotate failure"),
                ),
                self.assertRaisesRegex(StateError, "rotate failure"),
            ):
                writer.write("x")
            self.assertEqual(path.read_text(encoding="utf-8"), "12345678")
            self.assertLessEqual(path.stat().st_size, 8)
            writer.close()

    def test_busy_signature_expiry_mismatch_replay_and_gate(self) -> None:
        token, instance = "secret-token", "instance-a"
        now = time.time_ns() // 1_000_000
        envelope = control_busy_envelope(
            token, instance, issued_at_ms=now, nonce="1" * 32
        )
        evidence = verify_control_busy(envelope, token, instance, now_ms=now + 1)
        _remember_busy(instance, evidence)
        with self.assertRaisesRegex(RuntimeCorruptError, "重放"):
            _remember_busy(instance, evidence)
        with self.assertRaisesRegex(RuntimeCorruptError, "过期"):
            verify_control_busy(envelope, token, instance, now_ms=now + 6000)
        with self.assertRaises(RuntimeCorruptError):
            verify_control_busy(envelope, token, "instance-b", now_ms=now + 1)
        tampered = json.loads(json.dumps(envelope))
        tampered["busy"]["retryAfterMs"] = 999
        with self.assertRaisesRegex(RuntimeCorruptError, "HMAC"):
            verify_control_busy(tampered, token, instance, now_ms=now + 1)
        unsigned = json.loads(json.dumps(envelope))
        unsigned["busy"].pop("signature")
        with self.assertRaises(RuntimeCorruptError):
            verify_control_busy(unsigned, token, instance, now_ms=now + 1)
        gate = ControlRequestGate(1, token, instance)
        first, second = FakeSocket(), FakeSocket()
        self.assertTrue(gate.acquire(first))
        self.assertFalse(gate.acquire(second))
        self.assertIn(b"503 Service Unavailable", second.sent)
        self.assertEqual(second.timeout, 5.0)
        self.assertEqual(gate.active_count(), 1)
        gate.release(first)
        self.assertTrue(gate.drain(0.1))
        timed_out = FakeSocket()
        gate.reject_timeout(timed_out)
        self.assertIn(b"408 Request Timeout", timed_out.sent)
        body = json.loads(timed_out.sent.split(b"\r\n\r\n", 1)[1])
        self.assertEqual(body, control_timeout_envelope(instance))
        failing = FakeSocket()
        failing.settimeout = mock.Mock(side_effect=OSError("fixture"))
        with self.assertRaisesRegex(OSError, "fixture"):
            gate.acquire(failing)
        replacement = FakeSocket()
        self.assertTrue(gate.acquire(replacement))
        gate.release(replacement)
        out_of_range = control_busy_envelope(
            token, instance, retry_after_ms=1001, issued_at_ms=now, nonce="2" * 32
        )
        with self.assertRaisesRegex(RuntimeCorruptError, "evidence"):
            verify_control_busy(out_of_range, token, instance, now_ms=now + 1)

    def test_busy_replay_cache_never_evicts_live_evidence(self) -> None:
        now = time.time_ns() // 1_000_000
        with mock.patch("process_manager.client._BUSY_NONCES", {}):
            for index in range(1024):
                _remember_busy(
                    "instance",
                    {
                        "nonce": f"{index:032x}",
                        "issuedAtUnixMs": now,
                        "validForMs": 5000,
                    },
                )
            with self.assertRaisesRegex(RuntimeCorruptError, "安全上限"):
                _remember_busy(
                    "instance",
                    {
                        "nonce": "f" * 32,
                        "issuedAtUnixMs": now,
                        "validForMs": 5000,
                    },
                )
            with self.assertRaisesRegex(RuntimeCorruptError, "重放"):
                _remember_busy(
                    "instance",
                    {
                        "nonce": f"{0:032x}",
                        "issuedAtUnixMs": now,
                        "validForMs": 5000,
                    },
                )

    def test_prune_candidate_revision_race_requires_fresh_admission(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "cas-race")
            coordinator = PruneCoordinator(store)
            size = coordinator._tree_bytes(record)  # noqa: SLF001
            store.update(
                record["processKey"],
                status="stopped",
                public_updates={"finalizedAt": now_text()},
            )
            with self.assertRaisesRegex(StateError, "已变化"):
                coordinator._save_intent(record, size, False)  # noqa: SLF001
            self.assertEqual(store.load()["pendingPrunes"], {})
            fresh = store.get(key=record["processKey"])
            journal = coordinator._save_intent(  # noqa: SLF001
                fresh, coordinator._tree_bytes(fresh), False  # noqa: SLF001
            )
            self.assertTrue(coordinator._resume(journal))  # noqa: SLF001

    def test_pending_prune_freezes_record_mutation_until_recovery(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            record = self.terminal(store, workspace, "prune-freeze")
            coordinator = PruneCoordinator(store)
            journal = coordinator._save_intent(  # noqa: SLF001
                record, coordinator._tree_bytes(record), False  # noqa: SLF001
            )
            with self.assertRaisesRegex(StateError, "quarantined phase"):
                coordinator._commit(journal)  # noqa: SLF001
            with self.assertRaisesRegex(ConflictError, "prune transaction"):
                store.update(record["processKey"], status="stopped")
            self.assertEqual(
                store.load()["pendingPrunes"][journal["transactionId"]]["phase"],
                "intent",
            )
            self.assertTrue(coordinator.recover_pending()["cleanupVerified"])

    def test_repository_intent_precedes_run_directory_creation(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            service = create_service(workspace, store.config, name="pending-first")
            with (
                mock.patch(
                    "process_manager.protocol.write_capped_json",
                    side_effect=StateError("fixture pending write"),
                ),
                self.assertRaisesRegex(StateError, "pending write"),
            ):
                store.reserve(
                    service,
                    manager_instance_id="manager",
                    capability_hash="1" * 64,
                    ownership={"kind": "persistent", "sessionId": None},
                )
            self.assertFalse((store.paths.runs / service.name).exists())

    def test_gc_count_uses_all_inactive_records_not_only_eligible_records(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            blocked = self.terminal(store, workspace, "blocked-history")
            eligible = self.terminal(store, workspace, "eligible-history")
            store.update(
                blocked["processKey"],
                status="stopped",
                public_updates={
                    "ownerEmpty": False,
                    "cleanupVerified": False,
                    "finalizedAt": None,
                },
            )
            store.config = replace(store.config, history_max_inactive=1)
            result = ResourceGovernor(store).automatic_gc()
            state = store.load()
            self.assertEqual(result["prunedCount"], 1)
            self.assertIn(blocked["processKey"], state["processes"])
            self.assertNotIn(eligible["processKey"], state["processes"])
            self.assertFalse(ResourceGovernor(store).diagnostics()["overBudget"])

    def test_manual_and_automatic_gc_share_candidate_order(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            for name in ("oldest", "middle", "newest"):
                self.terminal(store, workspace, name)
            store.config = replace(store.config, history_max_inactive=1)
            manual = store.prune(max_inactive=None, dry_run=True)
            automatic = ResourceGovernor(store).automatic_gc()
            self.assertEqual(
                [item["processKey"] for item in automatic["candidates"]],
                [item["processKey"] for item in manual["candidates"]],
            )

    def test_metadata_writer_rejects_oversized_session(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            _, _, store = self.make_store(workspace)
            controller = self.controller(store)
            opened = controller.open(kind="validation", ttl_seconds=60, holder="cap")
            state = store.load()
            session = dict(state["sessions"][opened["sessionId"]])
            session["holder"] = "x" * RESOURCE_CAPS["session"]
            with self.assertRaises(StateError):
                store.commit_repository(state, sessions=[session])


if __name__ == "__main__":
    unittest.main()
