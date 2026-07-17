from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory  # noqa: E402
from manager_server import require_parent_operation  # noqa: E402
from process_manager.errors import RuntimeCorruptError  # noqa: E402
from process_manager.runtime import OperationStore, initialize_runtime  # noqa: E402
from process_manager.runtime_context import resolve_runtime_context  # noqa: E402


class ManagerServerTests(unittest.TestCase):
    def test_child_revalidates_same_pending_parent_before_publish(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            context = resolve_runtime_context(config=config.config_path)
            store = OperationStore(
                config,
                adapter,
                workspace_digest=context.workspace_digest,
                expected_config_digest=context.config_digest,
            )
            operation = store.create(
                "ensure",
                timeout=30,
                expected_runtime_fingerprint="a" * 64,
                expected_work_generation=None,
            )
            operation["checkpoint"] = "runtime-verified"
            store.write(operation)
            bound = require_parent_operation(
                store,
                operation_id=operation["operationId"],
                runtime_fingerprint="a" * 64,
            )
            self.assertEqual(bound["operationId"], operation["operationId"])
            store.update(
                operation,
                state="failed",
                error={"code": "abandoned", "cleanupVerified": True},
            )
            with self.assertRaises(RuntimeCorruptError):
                require_parent_operation(
                    store,
                    operation_id=operation["operationId"],
                    runtime_fingerprint="a" * 64,
                )

    def test_child_rejects_prelaunch_checkpoint(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            context = resolve_runtime_context(config=config.config_path)
            store = OperationStore(
                config,
                adapter,
                workspace_digest=context.workspace_digest,
                expected_config_digest=context.config_digest,
            )
            operation = store.create(
                "ensure",
                timeout=30,
                expected_runtime_fingerprint="a" * 64,
                expected_work_generation=None,
            )
            store.write(operation)
            with self.assertRaises(RuntimeCorruptError):
                require_parent_operation(
                    store,
                    operation_id=operation["operationId"],
                    runtime_fingerprint="a" * 64,
                )


if __name__ == "__main__":
    unittest.main()
