"""基础领域包的隔离单元测试。"""

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

from electron_verifier.atomic_io import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    exclusive_write_json,
    resolve_under,
    sha256_file,
)
from electron_verifier.errors import VerifierError  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class AtomicIoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_atomic_json_and_digest_are_stable(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            path = Path(folder) / "nested" / "value.json"
            atomic_write_json(path, {"b": 2, "a": "中文"})
            self.assertEqual({"b": 2, "a": "中文"}, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(64, len(sha256_file(path)))
            self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), canonical_json_bytes({"a": 1, "b": 2}))

    def test_exclusive_marker_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            path = Path(folder) / "decision.json"
            self.assertTrue(exclusive_write_json(path, {"decision": "approved"}))
            self.assertFalse(exclusive_write_json(path, {"decision": "rejected"}))
            self.assertEqual("approved", json.loads(path.read_text(encoding="utf-8"))["decision"])

    def test_resolve_under_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "runtime"
            root.mkdir()
            with self.assertRaisesRegex(VerifierError, "运行根目录"):
                resolve_under(root, Path(folder) / "outside.json")


if __name__ == "__main__":
    unittest.main()
