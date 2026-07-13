"""Codex adapter 的快照和 bounded process 测试。"""

from __future__ import annotations

import sys
import unittest

from _helpers import temporary_workspace
from skill_evaluation_lab.codex_runner import _run_bounded, instrument_trigger_snapshot
from skill_evaluation_lab.errors import ExecutionError
from skill_evaluation_lab.snapshots import build_tree_manifest


class CodexRunnerTests(unittest.TestCase):
    def test_instrumentation_changes_only_snapshot_body(self) -> None:
        with temporary_workspace() as root:
            source = root / "source"
            source.mkdir()
            original = "---\nname: probe\ndescription: Probe skill.\n---\n\n# Probe\n"
            (source / "SKILL.md").write_text(original, encoding="utf-8")
            before = build_tree_manifest(source)
            instrument_trigger_snapshot(source, root / "instrumented", "nonce-123")
            self.assertEqual(build_tree_manifest(source), before)
            self.assertEqual((source / "SKILL.md").read_text(encoding="utf-8"), original)
            instrumented = (root / "instrumented" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("nonce-123", instrumented)
            self.assertIn("description: Probe skill.", instrumented)

    def test_bounded_process_rejects_excess_output(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(ExecutionError, "大小上限"):
                _run_bounded(
                    [sys.executable, "-u", "-B", "-c", "print('x' * 10000)"],
                    cwd=root,
                    stdout_path=root / "stdout.log",
                    stderr_path=root / "stderr.log",
                    timeout_seconds=10,
                    stream_limit=128,
                )

    def test_bounded_process_rejects_timeout(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(ExecutionError, "timeout"):
                _run_bounded(
                    [sys.executable, "-u", "-B", "-c", "import time; time.sleep(5)"],
                    cwd=root,
                    stdout_path=root / "stdout.log",
                    stderr_path=root / "stderr.log",
                    timeout_seconds=1,
                )


if __name__ == "__main__":
    unittest.main()
