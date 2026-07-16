from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import create_file_target, receipt_for_target, writable_tempdir, write_json


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


class CliTests(unittest.TestCase):
    def run_script(self, name: str, *arguments: str) -> tuple[int, dict[str, object]]:
        result = subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-B", str(SCRIPT_DIR / name), *arguments],
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI 未返回 JSON：stdout={result.stdout!r}; stderr={result.stderr!r}; error={exc}")
        return result.returncode, payload

    def test_target_cli_writes_only_under_review_root(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            original = (root / "src" / "example.py").read_bytes()
            review_root = root / "reviews"
            output = review_root / "target.json"
            code, payload = self.run_script(
                "review_target.py",
                "files",
                "--workspace",
                str(root),
                "--file",
                "src/example.py",
                "--label",
                "unit-test",
                "--review-root",
                str(review_root),
                "--output",
                str(output),
            )
            self.assertEqual(0, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(target["digest"], payload["result"]["target"]["digest"])
            self.assertEqual(original, (root / "src" / "example.py").read_bytes())
            self.assertTrue(output.is_file())

    def test_target_cli_requires_explicit_review_root(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            create_file_target(root)
            code, payload = self.run_script(
                "review_target.py",
                "files",
                "--workspace",
                str(root),
                "--file",
                "src/example.py",
                "--output",
                str(root / "target.json"),
            )
            self.assertEqual(1, code)
            self.assertEqual("REVIEW_OUTPUT_ROOT_REQUIRED", payload["error"]["code"])

    def test_target_cli_refuses_overwrite(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            create_file_target(root)
            review_root = root / "reviews"
            review_root.mkdir()
            output = review_root / "target.json"
            output.write_text("existing\n", encoding="utf-8")
            code, payload = self.run_script(
                "review_target.py",
                "files",
                "--workspace",
                str(root),
                "--file",
                "src/example.py",
                "--review-root",
                str(review_root),
                "--output",
                str(output),
            )
            self.assertEqual(1, code)
            self.assertEqual("REVIEW_OUTPUT_EXISTS", payload["error"]["code"])

    def test_validate_and_render_cli(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            review_root = root / "reviews"
            receipt_path = review_root / "receipt.json"
            write_json(receipt_path, receipt)
            code, payload = self.run_script(
                "review_validate.py",
                "--receipt",
                str(receipt_path),
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--expected-profile",
                "code-review",
                "--expected-scope",
                "standalone",
            )
            self.assertEqual(0, code, payload)
            self.assertEqual(0, payload["result"]["agent_calls"])
            self.assertEqual(0, payload["result"]["network_calls"])
            output = review_root / "receipt.md"
            code, payload = self.run_script(
                "review_render.py",
                "--receipt",
                str(receipt_path),
                "--workspace",
                str(root),
                "--review-root",
                str(review_root),
                "--output",
                str(output),
            )
            self.assertEqual(0, code, payload)
            self.assertIn("# Review REV-CODE-001", output.read_text(encoding="utf-8"))

    def test_validate_rejects_receipt_outside_review_root(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt_path = root / "outside.json"
            review_root = root / "reviews"
            review_root.mkdir()
            write_json(receipt_path, receipt)
            code, payload = self.run_script(
                "review_validate.py",
                "--receipt",
                str(receipt_path),
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
            )
            self.assertEqual(1, code)
            self.assertEqual("REVIEW_OUTPUT_PATH_ESCAPE", payload["error"]["code"])


if __name__ == "__main__":
    unittest.main()
