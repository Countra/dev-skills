"""Session intent、健康复用和幂等清理测试。"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.driver import TargetCandidate  # noqa: E402
from electron_verifier.sessions import SessionManager  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class FakeDriver:
    def __init__(self) -> None:
        self.health_results: dict[str, dict] = {}
        self.attach_count = 0
        self.close_count = 0

    async def health(self, session_id: str) -> dict:
        return self.health_results.get(
            session_id,
            {"connected": False, "status": "stale", "reason": "live_handle_missing"},
        )

    async def attach(self, session_id: str, name: str, endpoint: str, selector: dict):
        self.attach_count += 1
        self.health_results[session_id] = {"connected": True, "status": "connected"}
        return SimpleNamespace(
            target=TargetCandidate("target-1", "Main", "app://main/private/account?secret=1")
        )

    async def close(self, session_id: str) -> list[str]:
        self.close_count += 1
        self.health_results.pop(session_id, None)
        return []


class SessionManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_restart_never_rehydrates_attached_claim(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            path = Path(folder) / "sessions.json"
            path.write_text(
                json.dumps(
                    {
                        "sessions": [
                            {
                                "sessionId": "session-1",
                                "name": "app",
                                "cdp": "http://127.0.0.1:9222",
                                "status": "attached",
                                "targetId": "target-1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manager = SessionManager(path, FakeDriver())
            asyncio.run(manager.load())
            result = asyncio.run(manager.status("app"))
            self.assertFalse(result["connected"])
            self.assertEqual("stale", result["session"]["status"])

    def test_stale_reuse_reconnects_then_live_reuse_is_health_checked(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            driver = FakeDriver()
            manager = SessionManager(Path(folder) / "sessions.json", driver)
            asyncio.run(manager.load())
            first = asyncio.run(manager.attach({"name": "app", "cdp": "http://127.0.0.1:9222"}))
            second = asyncio.run(manager.attach({"name": "app", "cdp": "http://127.0.0.1:9222"}))
            self.assertFalse(first["reused"])
            self.assertTrue(second["reused"])
            self.assertEqual(1, driver.attach_count)
            session_id = second["session"]["sessionId"]
            driver.health_results[session_id] = {"connected": False, "status": "stale", "reason": "closed"}
            third = asyncio.run(manager.attach({"name": "app", "cdp": "http://127.0.0.1:9222"}))
            self.assertTrue(third["reconnected"])
            self.assertEqual(2, driver.attach_count)
            persisted = (Path(folder) / "sessions.json").read_text(encoding="utf-8")
            self.assertNotIn("Main", persisted)
            self.assertNotIn("private/account", persisted)
            self.assertIn("app://main/[PATH]", persisted)

    def test_detach_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            manager = SessionManager(Path(folder) / "sessions.json", FakeDriver())
            asyncio.run(manager.load())
            first = asyncio.run(manager.detach("missing"))
            second = asyncio.run(manager.detach("missing"))
            self.assertTrue(first["alreadyDetached"])
            self.assertTrue(second["alreadyDetached"])


if __name__ == "__main__":
    unittest.main()
