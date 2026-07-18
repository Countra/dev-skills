"""PNG 质量与 evidence manifest 提交测试。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from pathlib import Path


TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory, make_png  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import EvidenceStore, PendingArtifact, validate_png  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_valid_png_has_dimensions_and_variation(self) -> None:
        metrics = validate_png(make_png())
        self.assertEqual((2, 2), (metrics["width"], metrics["height"]))
        self.assertGreater(metrics["pixelVariation"], 1)

    def test_blank_or_corrupt_png_is_rejected(self) -> None:
        with self.assertRaisesRegex(VerifierError, "单色"):
            validate_png(make_png(solid=True))
        corrupt = bytearray(make_png())
        corrupt[-5] ^= 1
        with self.assertRaises(VerifierError):
            validate_png(bytes(corrupt))

    def test_failed_screenshot_never_enters_manifest(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            store = EvidenceStore(Path(folder))
            store.initialize("run")
            committed = store.commit(PendingArtifact("image/png", make_png(), "valid", "png"), "step-1")
            with self.assertRaises(VerifierError):
                store.commit(PendingArtifact("image/png", make_png(solid=True), "blank", "png"), "step-2")
            manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual([committed["artifactId"]], [item["artifactId"] for item in manifest["artifacts"]])
            self.assertEqual(1, len(list(store.artifacts_dir.iterdir())))


if __name__ == "__main__":
    unittest.main()
