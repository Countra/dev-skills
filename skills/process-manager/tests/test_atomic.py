from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import workspace_directory  # noqa: E402
from process_manager.atomic import atomic_write_bytes  # noqa: E402
from process_manager.errors import StateError  # noqa: E402


class AtomicWriteTests(unittest.TestCase):
    def test_cleanup_failure_does_not_mask_primary_write_error(self) -> None:
        with workspace_directory() as directory:
            target = Path(directory) / "state.json"
            with (
                mock.patch("process_manager.atomic.os.replace", side_effect=OSError("primary")),
                mock.patch("process_manager.atomic.Path.unlink", side_effect=OSError("cleanup")),
            ):
                with self.assertRaisesRegex(StateError, "原子写入失败"):
                    atomic_write_bytes(target, b"{}\n")


if __name__ == "__main__":
    unittest.main()
