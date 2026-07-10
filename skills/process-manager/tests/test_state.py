from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, create_service, workspace_directory, write_json  # noqa: E402
from process_manager.errors import ConflictError, RuntimeRebuildRequiredError  # noqa: E402
from process_manager.state import StateStore  # noqa: E402


class StateTests(unittest.TestCase):
    def make_store(self, workspace: Path):  # noqa: ANN201
        config = create_config(workspace)
        adapter = FakeAdapter(workspace, config.state_root)
        adapter.secure_directory(config.paths.runs)
        store = StateStore(config, adapter)
        store.load()
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


if __name__ == "__main__":
    unittest.main()
