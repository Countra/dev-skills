from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))

import run_platform_smoke
from helpers import workspace_directory


class PlatformSmokeCleanupTests(unittest.TestCase):
    def test_manager_crash_workspace_is_removed_when_helper_is_not_ready(self) -> None:
        with workspace_directory() as directory:
            parent = Path(directory)
            process = mock.Mock(spec=subprocess.Popen)
            process.poll.return_value = 1

            def create_workspace(command, **_kwargs):  # noqa: ANN001,ANN202
                workspace = Path(command[command.index("--workspace") + 1])
                workspace.mkdir(parents=True)
                (workspace / "marker.txt").write_text("owned", encoding="utf-8")
                return process

            with (
                mock.patch.object(
                    run_platform_smoke.subprocess,
                    "Popen",
                    side_effect=create_workspace,
                ),
                mock.patch.object(run_platform_smoke, "wait_for_file", return_value=False),
            ):
                ok, error = run_platform_smoke.run_manager_crash_smoke(
                    parent,
                    mock.Mock(),
                    "secret",
                )

            self.assertFalse(ok)
            self.assertIn("未就绪", error or "")
            self.assertEqual([], list(parent.iterdir()))


if __name__ == "__main__":
    unittest.main()
