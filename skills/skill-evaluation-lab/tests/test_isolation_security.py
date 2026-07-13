"""快照、隔离和环境安全测试。"""

from __future__ import annotations

import os
import stat
import subprocess
import unittest

from _helpers import temporary_workspace
from skill_evaluation_lab.errors import ExecutionError, SuiteError
from skill_evaluation_lab.isolation import create_case_workspace, create_run_layout, resolve_within
from skill_evaluation_lab.security import REDACTED, build_child_env, redact_value
from skill_evaluation_lab.snapshots import build_tree_manifest, create_snapshot, verify_tree


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_complete_readonly_and_verifiable(self) -> None:
        with temporary_workspace() as root:
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("# Candidate\n", encoding="utf-8")
            nested = source / "scripts" / "run.py"
            nested.parent.mkdir()
            nested.write_text("print('ok')\n", encoding="utf-8")
            expected = create_snapshot(source, root / "snapshot")
            self.assertEqual(build_tree_manifest(root / "snapshot"), expected)
            self.assertFalse(bool((root / "snapshot" / "SKILL.md").stat().st_mode & stat.S_IWUSR))

    def test_verify_detects_source_change(self) -> None:
        with temporary_workspace() as root:
            source = root / "source"
            source.mkdir()
            skill_file = source / "SKILL.md"
            skill_file.write_text("before\n", encoding="utf-8")
            expected = build_tree_manifest(source)
            skill_file.write_text("after\n", encoding="utf-8")
            with self.assertRaisesRegex(ExecutionError, "完整性"):
                verify_tree(source, expected)

    def test_rejects_symlink_in_snapshot_tree(self) -> None:
        with temporary_workspace() as root:
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("# Test\n", encoding="utf-8")
            try:
                (source / "linked.md").symlink_to(source / "SKILL.md")
            except OSError:
                self.skipTest("当前平台不允许普通用户创建符号链接")
            with self.assertRaisesRegex(SuiteError, "链接"):
                build_tree_manifest(source)

    def test_rejects_symlink_as_snapshot_root(self) -> None:
        with temporary_workspace() as root:
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("# Test\n", encoding="utf-8")
            linked = root / "linked-source"
            try:
                linked.symlink_to(source, target_is_directory=True)
            except OSError:
                self.skipTest("当前平台不允许普通用户创建目录符号链接")
            with self.assertRaisesRegex(SuiteError, "链接"):
                build_tree_manifest(linked)


class IsolationTests(unittest.TestCase):
    def test_case_workspace_has_clean_git_baseline(self) -> None:
        with temporary_workspace() as root:
            suite_root = root / "suite"
            suite_root.mkdir()
            (suite_root / "input.txt").write_text("input\n", encoding="utf-8")
            layout = create_run_layout(root / "runs", "suite", "a" * 64, run_id="run-1")
            case = create_case_workspace(
                layout,
                case_id="case-one",
                variant="candidate",
                repetition=1,
                suite_root=suite_root,
                inputs=["input.txt"],
            )
            completed = subprocess.run(
                ["git", "status", "--porcelain"], cwd=case.root, text=True, capture_output=True, check=True
            )
            self.assertEqual(completed.stdout, "")
            self.assertEqual((case.root / "input.txt").read_text(encoding="utf-8"), "input\n")

    def test_resolve_within_rejects_escape(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(SuiteError, "不安全"):
                resolve_within(root, "../outside.txt")

    def test_run_id_rejects_path_components(self) -> None:
        with temporary_workspace() as root:
            with self.assertRaisesRegex(SuiteError, "run_id"):
                create_run_layout(root / "runs", "suite", "a" * 64, run_id="../outside")


class SecurityTests(unittest.TestCase):
    def test_child_environment_drops_secrets(self) -> None:
        child = build_child_env(
            {"PATH": os.environ.get("PATH", ""), "SKILL_GITLAB_PAT": "secret", "API_KEY": "key", "LANG": "C"}
        )
        self.assertIn("PATH", child)
        self.assertNotIn("SKILL_GITLAB_PAT", child)
        self.assertNotIn("API_KEY", child)

    def test_child_environment_rejects_explicit_secret(self) -> None:
        with self.assertRaisesRegex(SuiteError, "敏感环境变量"):
            build_child_env({}, extra={"ACCESS_TOKEN": "secret"})

    def test_redacts_sensitive_fields_and_known_values(self) -> None:
        value = {"token": "abc123", "message": "credential=abc123", "nested": [{"password": "visible"}]}
        redacted = redact_value(value, secrets=("abc123",))
        self.assertEqual(redacted["token"], REDACTED)
        self.assertEqual(redacted["message"], f"credential={REDACTED}")
        self.assertEqual(redacted["nested"][0]["password"], REDACTED)


if __name__ == "__main__":
    unittest.main()
