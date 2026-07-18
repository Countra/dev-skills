"""基础领域包的隔离单元测试。"""

from __future__ import annotations

import gc
import json
import os
import shutil
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory  # noqa: E402
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

    def test_test_temporary_directory_is_writable_and_cleanup_is_idempotent(self) -> None:
        temporary = TestTemporaryDirectory(dir=TEST_ROOT)
        path = Path(temporary.name)
        try:
            marker = path / "marker.txt"
            marker.write_text("ok", encoding="utf-8")
            self.assertEqual("ok", marker.read_text(encoding="utf-8"))
        finally:
            temporary.cleanup()
        self.assertFalse(path.exists())
        temporary.cleanup()

    def test_tests_do_not_use_restrictive_stdlib_temporary_directory(self) -> None:
        test_dir = Path(__file__).resolve().parent
        forbidden = "tempfile." + "TemporaryDirectory"
        offenders = [
            path.name
            for path in sorted(test_dir.glob("test_*.py"))
            if forbidden in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], offenders)

    def test_test_temporary_directory_finalizer_removes_abandoned_directory(self) -> None:
        temporary = TestTemporaryDirectory(dir=TEST_ROOT)
        path = Path(temporary.name)
        (path / "marker.txt").write_text("ok", encoding="utf-8")
        del temporary
        gc.collect()
        self.assertFalse(path.exists())

    def test_atomic_json_and_digest_are_stable(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            path = Path(folder) / "nested" / "value.json"
            atomic_write_json(path, {"b": 2, "a": "中文"})
            self.assertEqual({"b": 2, "a": "中文"}, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(64, len(sha256_file(path)))
            self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), canonical_json_bytes({"a": 1, "b": 2}))

    def test_exclusive_marker_is_idempotent(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            path = Path(folder) / "decision.json"
            self.assertTrue(exclusive_write_json(path, {"decision": "approved"}))
            self.assertFalse(exclusive_write_json(path, {"decision": "rejected"}))
            self.assertEqual("approved", json.loads(path.read_text(encoding="utf-8"))["decision"])

    def test_resolve_under_rejects_escape(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "runtime"
            root.mkdir()
            with self.assertRaisesRegex(VerifierError, "运行根目录"):
                resolve_under(root, Path(folder) / "outside.json")


if __name__ == "__main__":
    unittest.main()
