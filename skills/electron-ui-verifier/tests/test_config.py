"""Service config 的受控路径边界测试。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.config import ServiceConfig  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


def config_value(workspace: Path) -> dict:
    state = workspace / ".harness" / "electron-ui-verifier"
    return {
        "host": "127.0.0.1",
        "port": 18180,
        "workspaceRoot": str(workspace),
        "stateRoot": str(state),
        "tokenFile": str(state / "token"),
        "serverFile": str(state / "server.json"),
        "sessionsFile": str(state / "sessions.json"),
        "reportsDir": str(state / "reports"),
        "pendingDir": str(state / "pending"),
        "workflowsDir": str(state / "workflows"),
        "artifactsDir": str(state / "artifacts"),
        "logsDir": str(state / "logs"),
        "tmpDir": str(state / "tmp"),
        "runsDir": str(state / "runs"),
    }


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_runtime_paths_must_stay_under_state_root(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            workspace = Path(folder)
            path = workspace / "config.json"
            value = config_value(workspace)
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(workspace.resolve(), ServiceConfig.load(path).workspace_root.resolve())
            value["reportsDir"] = str(workspace.parent / "outside")
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(VerifierError, "stateRoot"):
                ServiceConfig.load(path)


if __name__ == "__main__":
    unittest.main()
