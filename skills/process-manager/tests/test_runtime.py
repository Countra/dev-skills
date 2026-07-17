from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory  # noqa: E402
from process_manager.errors import IdentityError, RuntimeRebuildRequiredError  # noqa: E402
from process_manager.runtime import (  # noqa: E402
    build_manager_identity,
    initialize_runtime,
    read_manager_identity,
    read_token,
    write_manager_identity,
)


class RuntimeTests(unittest.TestCase):
    def test_runtime_token_and_manager_identity_are_separate(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            token = read_token(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id="00000000000000000000000000000000",
                instance_id="manager-instance",
                port=32123,
                bootstrap_backend="detached",
                bootstrap_selection_reason="test fixture",
                runtime_fingerprint="a" * 64,
            )
            write_manager_identity(config, adapter, identity)
            loaded = read_manager_identity(config, adapter)
            self.assertEqual(loaded["instanceId"], "manager-instance")
            self.assertNotIn(token, config.paths.manager.read_text(encoding="utf-8"))
            adapter.identity_valid = False
            with self.assertRaises(IdentityError):
                read_manager_identity(config, adapter)

    def test_legacy_manager_pid_requires_explicit_rebuild(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            (config.state_root / "manager.pid").write_text(str(os.getpid()), encoding="ascii")
            with self.assertRaises(RuntimeRebuildRequiredError):
                initialize_runtime(config, adapter)

    def test_manager_identity_rejects_unknown_fields(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id="00000000000000000000000000000000",
                instance_id="manager-instance",
                port=32123,
                bootstrap_backend="detached",
                bootstrap_selection_reason="test fixture",
                runtime_fingerprint="a" * 64,
            )
            identity["unexpected"] = "rejected"
            write_manager_identity(config, adapter, identity)
            with self.assertRaises(IdentityError):
                read_manager_identity(config, adapter)


if __name__ == "__main__":
    unittest.main()
