from __future__ import annotations

import json
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, create_service, workspace_directory, write_json  # noqa: E402
from process_manager.errors import ConflictError, RuntimeRebuildRequiredError, StateError  # noqa: E402
from process_manager.run_finalization import OwnerFinalization, RunFinalizationCoordinator  # noqa: E402
from process_manager.state import StateStore  # noqa: E402


class StateTests(unittest.TestCase):
    def make_store(self, workspace: Path):  # noqa: ANN201
        config = create_config(workspace)
        adapter = FakeAdapter(workspace, config.state_root)
        adapter.secure_directory(config.paths.runs)
        store = StateStore(config, adapter)
        store.load()
        reserve = store.reserve
        store.reserve = lambda service, **kwargs: reserve(  # type: ignore[method-assign]
            service,
            ownership={"kind": "persistent", "sessionId": None},
            **kwargs,
        )
        return config, adapter, store

    def test_concurrent_reservation_creates_one_active_run(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            successes: list[str] = []
            conflicts: list[str] = []

            def reserve() -> None:
                try:
                    record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
                    successes.append(record["processKey"])
                except ConflictError as exc:
                    conflicts.append(exc.code)

            threads = [threading.Thread(target=reserve) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(successes), 1)
            self.assertEqual(conflicts, ["state_conflict"])
            self.assertEqual(store.load()["active"]["demo"], successes[0])

    def test_corrupt_index_rebuilds_from_latest_run_record(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            config.paths.processes.write_text("{broken", encoding="utf-8")
            recovered = store.load()
            self.assertIn(record["processKey"], recovered["processes"])
            self.assertEqual(recovered["active"]["demo"], record["processKey"])

    def test_pending_record_commit_is_visible_and_replayed(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            pending_path = config.state_root / "processes.pending.json"
            with mock.patch.object(
                store,
                "_apply_pending_transaction",
                side_effect=StateError("fixture interruption"),
            ):
                with self.assertRaisesRegex(StateError, "fixture interruption"):
                    store.update(record["processKey"], status="stopped", clear_active=True)

            self.assertTrue(pending_path.is_file())
            self.assertEqual(
                json.loads(Path(record["processFile"]).read_text(encoding="utf-8"))["status"],
                "starting",
            )
            recovered = StateStore(config, adapter)
            self.assertEqual(recovered.load()["processes"][record["processKey"]]["status"], "stopped")
            self.assertTrue(pending_path.is_file())
            with recovered.transaction():
                pass
            self.assertFalse(pending_path.exists())
            self.assertEqual(recovered.load()["processes"][record["processKey"]]["status"], "stopped")
            self.assertEqual(
                json.loads(Path(record["processFile"]).read_text(encoding="utf-8"))["status"],
                "stopped",
            )

    def test_record_commit_replays_after_central_write_failure(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            with mock.patch.object(store, "_save", side_effect=StateError("fixture central failure")):
                with self.assertRaisesRegex(StateError, "fixture central failure"):
                    store.update(record["processKey"], status="stopped", clear_active=True)

            recovered = StateStore(config, adapter)
            self.assertEqual(recovered.load()["processes"][record["processKey"]]["status"], "stopped")
            with recovered.transaction():
                pass
            self.assertEqual(
                json.loads(config.paths.processes.read_text(encoding="utf-8"))["processes"][
                    record["processKey"]
                ]["status"],
                "stopped",
            )

    def test_rebuild_preserves_conflicting_active_owner_evidence(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            first = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            second_run_id = "run-" + "2" * 32
            second_dir = config.paths.runs / service.name / second_run_id
            second_file = second_dir / "process.json"
            second = json.loads(json.dumps(first))
            second.update(
                {
                    "processId": second_run_id,
                    "processKey": f"{service.name}.{second_run_id}",
                    "runDir": str(second_dir.resolve()),
                    "processFile": str(second_file.resolve()),
                }
            )
            second["public"]["processKey"] = second["processKey"]
            write_json(second_file, second)
            with self.assertRaisesRegex(StateError, "多个 active owner"):
                store.rebuild()
            self.assertEqual(
                json.loads(Path(first["processFile"]).read_text(encoding="utf-8"))["status"],
                "starting",
            )
            self.assertEqual(json.loads(second_file.read_text(encoding="utf-8"))["status"], "starting")

    def test_unknown_runtime_schema_fails_closed(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            write_json(config.paths.processes, {"active": {}, "processes": {}})
            with self.assertRaises(RuntimeRebuildRequiredError):
                store.load()

    def test_state_and_run_record_do_not_persist_secret_value(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config, from_env=["APP_TOKEN"])
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash-only")
            state_text = config.paths.processes.read_text(encoding="utf-8")
            record_text = Path(record["processFile"]).read_text(encoding="utf-8")
            self.assertNotIn("secret-value", state_text + record_text)

    def test_unknown_state_field_is_rejected_and_rebuilt(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            state = json.loads(config.paths.processes.read_text(encoding="utf-8"))
            state["unexpected"] = "rejected"
            write_json(config.paths.processes, state)
            recovered = store.load()
            self.assertNotIn("unexpected", recovered)
            self.assertIn(record["processKey"], recovered["processes"])

    def test_prune_is_bounded_transactional_and_not_rebuilt(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            run_dirs: list[Path] = []
            for _ in range(3):
                record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
                run_dirs.append(Path(record["runDir"]))
                store.update(record["processKey"], status="stopped", clear_active=True)
            preview = store.prune(max_inactive=1, dry_run=True)
            self.assertEqual(preview["candidateCount"], 2)
            self.assertTrue(all(path.exists() for path in run_dirs))
            applied = store.prune(max_inactive=1, dry_run=False)
            self.assertEqual(applied["prunedCount"], 2)
            self.assertTrue(applied["cleanupVerified"])
            self.assertEqual(len(store.load()["processes"]), 1)
            self.assertEqual(len(store.rebuild()["processes"]), 1)

    def test_prune_keep_runs_archives_process_record_outside_rebuild_scan(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            store.update(record["processKey"], status="stopped", clear_active=True)
            run_dir = Path(record["runDir"])
            applied = store.prune(max_inactive=0, dry_run=False, keep_runs=True)
            self.assertTrue(applied["keepRuns"])
            self.assertTrue(run_dir.is_dir())
            self.assertFalse((run_dir / "process.json").exists())
            self.assertTrue((run_dir / "process.pruned.json").is_file())
            self.assertEqual(store.rebuild()["processes"], {})

    def test_manager_loss_finalizes_only_after_persisted_owner_is_empty(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="old-manager", capability_hash="hash")
            host = types.SimpleNamespace(pid=101, returncode=None)
            owner = adapter.create_run_owner(record["processId"], host, "hash")
            owner.bind_target({"pid": 202})
            store.update(
                record["processKey"],
                status="running",
                internal_updates={
                    "owner": owner.internal_identity(),
                    "hostIdentity": adapter.process_identity(101),
                    "targetIdentity": adapter.process_identity(202),
                },
            )
            result = RunFinalizationCoordinator(store, adapter, "new-manager").reconcile_manager_loss()
            finalized = store.get(key=record["processKey"])
            self.assertEqual(result["finalized"], [record["processKey"]])
            self.assertEqual(finalized["status"], "manager_lost")
            self.assertTrue(finalized["public"]["ownerEmpty"])
            self.assertTrue(finalized["public"]["cleanupVerified"])
            self.assertIsNotNone(finalized["public"]["finalizedAt"])
            self.assertNotIn(service.name, store.list_records()["active"])

    def test_unverifiable_owner_stays_terminating_and_active(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, adapter, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="old-manager", capability_hash="hash")
            result = RunFinalizationCoordinator(store, adapter, "new-manager").reconcile_manager_loss()
            pending = store.get(key=record["processKey"])
            self.assertEqual(result["pending"], [record["processKey"]])
            self.assertEqual(pending["status"], "terminating")
            self.assertFalse(pending["public"]["cleanupVerified"])
            self.assertEqual(pending["public"]["cleanupError"], "owner_evidence_invalid")
            self.assertEqual(store.list_records()["active"][service.name], record["processKey"])

    def test_finalization_cannot_commit_terminal_before_owner_empty(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config, _, store = self.make_store(workspace)
            service = create_service(workspace, config)
            record = store.reserve(service, manager_instance_id="manager", capability_hash="hash")
            claimed = store.claim_finalization(
                record["processKey"],
                reason="test",
                manager_instance_id="manager",
            )
            pending = store.commit_finalization(
                record["processKey"],
                terminal_status="stopped",
                result=OwnerFinalization(
                    False,
                    False,
                    False,
                    True,
                    False,
                    {},
                    "owner_not_empty",
                ),
                claim_id=claimed["cleanupClaim"]["claimId"],
            )
            self.assertEqual(pending["status"], "terminating")
            self.assertIn(service.name, store.list_records()["active"])


if __name__ == "__main__":
    unittest.main()
