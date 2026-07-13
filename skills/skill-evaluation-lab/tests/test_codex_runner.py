"""Codex adapter 的快照和 bounded process 测试。"""

from __future__ import annotations

import json
import stat
import sys
import unittest
from unittest import mock

from _helpers import temporary_workspace
from skill_evaluation_lab.budgets import RunBudget
from skill_evaluation_lab.codex_runner import (
    CodexRunner,
    _run_bounded,
    instrument_trigger_snapshot,
    prompt_skill_marker_count,
)
from skill_evaluation_lab.errors import ExecutionError, UnsupportedError
from skill_evaluation_lab.runners import RunRequest
from skill_evaluation_lab.snapshots import build_tree_manifest


class CodexRunnerTests(unittest.TestCase):
    def test_prompt_probe_uses_exact_skill_file_marker(self) -> None:
        with temporary_workspace() as root:
            skill = root / "candidate" / ".agents" / "skills" / "probe"
            skill.mkdir(parents=True)
            skill_file = (skill / "SKILL.md").resolve().as_posix()
            unrelated = json.dumps(
                [{"content": [{"text": f"workspace/{skill.name}/without-an-entry"}]}]
            )
            visible = json.dumps(
                [{"content": [{"text": f"- probe: Probe description. (file: {skill_file})"}]}]
            )

            self.assertEqual(prompt_skill_marker_count(unrelated, skill), 0)
            self.assertEqual(prompt_skill_marker_count(visible, skill), 1)
            with self.assertRaisesRegex(UnsupportedError, "合法 JSON"):
                prompt_skill_marker_count("not-json", skill)

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

    def test_bounded_process_forwards_only_managed_codex_profile(self) -> None:
        with temporary_workspace() as root, mock.patch.dict(
            "os.environ",
            {"PATH": "", "CODEX_PERMISSION_PROFILE": ":workspace"},
            clear=True,
        ):
            _run_bounded(
                [
                    sys.executable,
                    "-u",
                    "-B",
                    "-c",
                    "import os; print(os.environ.get('CODEX_PERMISSION_PROFILE'))",
                ],
                cwd=root,
                stdout_path=root / "stdout.log",
                stderr_path=root / "stderr.log",
                timeout_seconds=10,
            )
            self.assertEqual((root / "stdout.log").read_text(encoding="utf-8").strip(), ":workspace")

    def test_trigger_runner_detects_visible_snapshot_mutation(self) -> None:
        with temporary_workspace() as root:
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: probe\ndescription: Probe.\n---\n\n# Probe\n",
                encoding="utf-8",
            )
            workspace = root / "workspace"
            workspace.mkdir()
            request = RunRequest(
                run_id="run",
                case_id="trigger",
                attempt=1,
                prompt="Use the probe skill.",
                workspace=workspace,
                artifact_dir=root / "artifacts",
                model="test-model",
                sandbox="read-only",
                timeout_seconds=30,
                fingerprint="f" * 64,
                lab_tree_sha256="a" * 64,
                approved_fingerprint="f" * 64,
                live_authorized=True,
                skill_path=source,
            )

            def mutate_snapshot(*_args: object, **_kwargs: object) -> int:
                trace = request.artifact_dir / "trace.jsonl"
                trace.write_text(
                    "".join(
                        json.dumps(event) + "\n"
                        for event in (
                            {"type": "thread.started", "thread_id": "thread"},
                            {"type": "turn.started"},
                            {"type": "turn.completed", "usage": {}},
                        )
                    ),
                    encoding="utf-8",
                )
                (request.artifact_dir / "final.json").write_text(
                    '{"activation_receipt":null,"response":"ok"}\n',
                    encoding="utf-8",
                )
                visible = workspace / ".agents" / "skills" / "probe" / "SKILL.md"
                visible.chmod(visible.stat().st_mode | stat.S_IWUSR)
                visible.write_text("mutated\n", encoding="utf-8")
                return 0

            budget = RunBudget(max_agent_runs=1, max_judge_runs=0, max_wall_seconds=60)
            with mock.patch("skill_evaluation_lab.codex_runner.codex_path", return_value="codex"), mock.patch(
                "skill_evaluation_lab.codex_runner.run_capture",
                return_value="codex 1.0\n",
            ), mock.patch(
                "skill_evaluation_lab.codex_runner._run_bounded",
                side_effect=mutate_snapshot,
            ):
                with self.assertRaisesRegex(ExecutionError, "完整性"):
                    CodexRunner().run(request, budget)


if __name__ == "__main__":
    unittest.main()
