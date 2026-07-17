from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import create_config, workspace_directory, write_json  # noqa: E402
from process_manager.errors import ContextInvalidError  # noqa: E402
from process_manager.runtime_context import resolve_runtime_context  # noqa: E402


class RuntimeContextTests(unittest.TestCase):
    def test_same_absolute_workspace_is_independent_from_current_directory(self) -> None:
        with workspace_directory() as directory, workspace_directory() as other:
            workspace = Path(directory)
            create_config(workspace)
            original = Path.cwd()
            try:
                os.chdir(other)
                from_workspace = resolve_runtime_context(workspace=workspace)
                from_config = resolve_runtime_context(config=from_workspace.config_path)
            finally:
                os.chdir(original)
        self.assertEqual(from_workspace.workspace_digest, from_config.workspace_digest)
        self.assertEqual(from_workspace.config_digest, from_config.config_digest)
        self.assertEqual(from_workspace.state_root, from_config.state_root)

    def test_uninitialized_context_is_read_only(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            context = resolve_runtime_context(workspace=workspace)
            self.assertFalse(context.initialized)
            self.assertEqual(context.config_path, workspace / ".harness" / "process-manager" / "config.json")
            self.assertFalse((workspace / ".harness").exists())

    def test_context_requires_one_absolute_selector(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = workspace / ".harness" / "process-manager" / "config.json"
            for kwargs in (
                {},
                {"workspace": "."},
                {"config": "config.json"},
                {"workspace": workspace, "config": config},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ContextInvalidError):
                    resolve_runtime_context(**kwargs)
            self.assertFalse((workspace / ".harness").exists())

    def test_config_workspace_mismatch_fails_closed(self) -> None:
        with workspace_directory() as first, workspace_directory() as second:
            first_root = Path(first)
            second_root = Path(second)
            config_path = second_root / ".harness" / "process-manager" / "config.json"
            write_json(
                config_path,
                {
                    "workspaceRoot": str(first_root),
                    "stateRoot": str(first_root / ".harness" / "process-manager"),
                    "control": {"host": "127.0.0.1", "port": 0, "maxRequestBytes": 65536},
                    "history": {"maxInactive": 20, "deleteRunDirs": True},
                    "logs": {"maxBytes": 10485760, "backups": 3},
                },
            )
            before = config_path.read_bytes()
            with self.assertRaises(ContextInvalidError):
                resolve_runtime_context(config=config_path)
            self.assertEqual(before, config_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
