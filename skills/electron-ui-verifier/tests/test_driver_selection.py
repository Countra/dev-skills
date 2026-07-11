"""Playwright driver 的 target 选择和连接选项测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.driver import PlaywrightCdpDriver, TargetCandidate  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402


class DriverSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = PlaywrightCdpDriver(Path.cwd())
        self.candidates = [
            (TargetCandidate("a", "Main", "app://main"), object(), object()),
            (TargetCandidate("b", "Settings", "app://settings"), object(), object()),
        ]

    def test_ambiguous_target_is_not_silently_selected(self) -> None:
        with self.assertRaisesRegex(VerifierError, "多个") as caught:
            self.driver._select(self.candidates, {})
        self.assertEqual("ambiguous_target", caught.exception.code)
        self.assertEqual(2, len(caught.exception.details["candidates"]))

    def test_explicit_selector_and_index_are_deterministic(self) -> None:
        target = self.driver._select(self.candidates, {"targetTitleContains": "Settings"})[0]
        self.assertEqual("b", target.target_id)
        target = self.driver._select(self.candidates, {"targetIndex": 0})[0]
        self.assertEqual("a", target.target_id)

    def test_connect_sets_local_and_no_defaults_when_supported(self) -> None:
        async def connect_over_cdp(endpoint_url, *, timeout=None, is_local=None, no_defaults=None, artifacts_dir=None):
            return endpoint_url

        self.driver._playwright = SimpleNamespace(
            chromium=SimpleNamespace(connect_over_cdp=connect_over_cdp)
        )
        options = self.driver._connect_options("http://127.0.0.1:9222", 5000)
        self.assertEqual(True, options["is_local"])
        self.assertEqual(True, options["no_defaults"])
        self.assertEqual(5000, options["timeout"])


if __name__ == "__main__":
    unittest.main()
