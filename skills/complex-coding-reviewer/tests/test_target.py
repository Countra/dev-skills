from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from helpers import create_file_target, create_plan_target, writable_tempdir

from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.target import (
    build_commit_range_target,
    build_file_manifest_target,
    build_working_tree_target,
    validate_target_shape,
    verify_target_freshness,
)


class FileTargetTests(unittest.TestCase):
    def test_file_order_does_not_change_digest(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            (root / "b.txt").write_text("b\n", encoding="utf-8")
            first = build_file_manifest_target(root, ["b.txt", "a.txt"])
            second = build_file_manifest_target(root, ["a.txt", "b.txt"])
            self.assertEqual(first, second)
            self.assertEqual(["a.txt", "b.txt"], [item["path"] for item in first["manifest"]])

    def test_mutation_marks_target_stale(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            verify_target_freshness(target, workspace=root)
            (root / "src" / "example.py").write_text("answer = 43\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_TARGET_STALE"):
                verify_target_freshness(target, workspace=root)

    def test_parent_traversal_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ReviewError, "REVIEW_TARGET_PATH_INVALID"):
                build_file_manifest_target(root, ["../outside.txt"])

    def test_tampered_digest_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            target = create_file_target(Path(temp))
            target["digest"] = "0" * 64
            with self.assertRaisesRegex(ReviewError, "REVIEW_TARGET_DIGEST_INVALID"):
                validate_target_shape(target)


class PlanTargetTests(unittest.TestCase):
    def test_plan_target_excludes_review_artifact(self) -> None:
        with writable_tempdir() as temp:
            target = create_plan_target(Path(temp))
            paths = [item["path"] for item in target["manifest"]]
            self.assertEqual(
                ["artifacts/architecture.md", "execution-plan.md", "plan-contract.json"],
                paths,
            )
            verify_target_freshness(target, task_dir=Path(temp))


class GitTargetTests(unittest.TestCase):
    def run_git(self, root: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
        return result.stdout.strip()

    def create_repository(self, root: Path) -> str:
        self.run_git(root, "init", "--quiet")
        self.run_git(root, "config", "user.email", "reviewer@example.invalid")
        self.run_git(root, "config", "user.name", "Reviewer Test")
        (root / "tracked.txt").write_text("before\n", encoding="utf-8")
        (root / "deleted.txt").write_text("delete\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "--quiet", "-m", "baseline")
        return self.run_git(root, "rev-parse", "HEAD")

    def test_working_tree_includes_modified_deleted_and_untracked(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            baseline = self.create_repository(root)
            (root / "tracked.txt").write_text("after\n", encoding="utf-8")
            (root / "deleted.txt").unlink()
            (root / "untracked.txt").write_text("new\n", encoding="utf-8")
            target = build_working_tree_target(
                root,
                baseline=baseline,
                stage_id="STG-01",
                attempt=1,
            )
            states = {item["path"]: item["state"] for item in target["manifest"]}
            self.assertEqual(
                {"deleted.txt": "deleted", "tracked.txt": "present", "untracked.txt": "present"},
                states,
            )
            verify_target_freshness(target, workspace=root)

    def test_stage_identity_requires_attempt_pair(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            baseline = self.create_repository(root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_TARGET_IDENTITY_INVALID"):
                build_working_tree_target(root, baseline=baseline, stage_id="STG-01")

    def test_commit_range_is_immutable_after_worktree_change(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            baseline = self.create_repository(root)
            (root / "tracked.txt").write_text("committed\n", encoding="utf-8")
            self.run_git(root, "add", "tracked.txt")
            self.run_git(root, "commit", "--quiet", "-m", "change")
            head = self.run_git(root, "rev-parse", "HEAD")
            target = build_commit_range_target(root, baseline=baseline, head=head)
            (root / "tracked.txt").write_text("uncommitted\n", encoding="utf-8")
            verify_target_freshness(target, workspace=root)


if __name__ == "__main__":
    unittest.main()
