from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import WritableTemporaryDirectory


EXECUTOR_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REVIEWER_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "complex-coding-reviewer"
    / "scripts"
)
sys.path.insert(0, str(EXECUTOR_SCRIPTS))
sys.path.insert(0, str(REVIEWER_SCRIPTS))

from complex_coding_reviewer.target import build_working_tree_target  # noqa: E402
from harness_commit_equivalence import (  # noqa: E402
    CommitEquivalenceError,
    create_commit_equivalence,
    validate_commit_equivalence,
)
from harness_task_bundle import resolve_task_bundle  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class CommitEquivalenceTest(unittest.TestCase):
    def run_git(self, workspace: Path, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        return completed.stdout.strip()

    def setUp(self) -> None:
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.run_git(self.workspace, "init", "--quiet")
        source_dir = self.workspace / "src"
        source_dir.mkdir()
        (source_dir / "existing.py").write_text("answer = 1\n", encoding="utf-8")
        (source_dir / "deleted.py").write_text("obsolete = True\n", encoding="utf-8")
        self.run_git(self.workspace, "add", "src")
        self.run_git(
            self.workspace,
            "-c",
            "user.name=Equivalence Test",
            "-c",
            "user.email=equivalence@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        )
        (source_dir / "existing.py").write_text("answer = 2\n", encoding="utf-8")
        (source_dir / "deleted.py").unlink()
        (source_dir / "added.py").write_text("added = True\n", encoding="utf-8")
        target = build_working_tree_target(self.workspace, paths=["src"])

        task_dir = self.workspace / ".harness" / "tasks" / "equivalence"
        task_dir.mkdir(parents=True)
        (task_dir / "execution-plan.md").write_text("# plan\n", encoding="utf-8")
        write_json(
            task_dir / "plan-contract.json",
            {
                "task_id": "equivalence",
                "plan_revision": 1,
                "stages": [
                    {
                        "id": "STG-01",
                        "depends_on": [],
                        "validation_ids": [],
                        "allowed_changes": ["src/**"],
                        "risk": "low",
                        "commit_expectation": "final",
                    }
                ],
                "validations": [],
            },
        )
        self.bundle = resolve_task_bundle(
            self.workspace,
            ".harness/tasks/equivalence",
        )
        self.dispatch_ref = "dispatches/final.json"
        self.dispatch_path = task_dir / "artifacts" / "reviews" / self.dispatch_ref
        write_json(
            self.dispatch_path,
            {
                "dispatch_id": "DSP-CODE-FINAL-001",
                "review_id": "REV-CODE-FINAL-001",
                "policy": "strict",
                "lifecycle": {
                    "status": "completed",
                    "close": {"status": "closed"},
                },
            },
        )
        self.report_ref = "artifacts/reviews/final.json"
        self.report_path = task_dir / self.report_ref
        write_json(
            self.report_path,
            {
                "review_id": "REV-CODE-FINAL-001",
                "profile": "code-review",
                "scope": {"kind": "final-integration"},
                "target": target,
                "reviewer": {
                    "mode": "external-agent",
                    "independence_claim": True,
                    "dispatch_id": "DSP-CODE-FINAL-001",
                    "dispatch_ref": self.dispatch_ref,
                    "dispatch_digest": hashlib.sha256(
                        self.dispatch_path.read_bytes()
                    ).hexdigest(),
                },
            },
        )
        self.review_record = {
            "result": "passed",
            "review_id": "REV-CODE-FINAL-001",
            "profile": "code-review",
            "scope": {"kind": "final-integration"},
            "target_digest": target["digest"],
            "context_digest": "c" * 64,
            "verdict": "passed",
            "report_ref": self.report_ref,
            "report_digest": hashlib.sha256(self.report_path.read_bytes()).hexdigest(),
            "open_counts": {
                "blocking": 0,
                "major": 0,
                "minor": 0,
                "advisory": 0,
                "total": 0,
            },
            "gap_counts": {"blocking": 0, "major": 0, "minor": 0, "total": 0},
            "coverage_summary": {
                "target_paths": 3,
                "requirements": 1,
                "risks": 0,
                "context_expansions": 0,
            },
            "lineage_summary": {
                "predecessor_review_id": None,
                "accounted_finding_count": 0,
            },
            "strength_count": 0,
            "summary": "提交前 final review 已通过。",
            "reviewer_mode": "external-agent",
            "independence_claim": True,
            "dispatch_id": "DSP-CODE-FINAL-001",
        }

    def commit_source(self) -> str:
        self.run_git(self.workspace, "add", "-A", "--", "src")
        self.run_git(
            self.workspace,
            "-c",
            "user.name=Equivalence Test",
            "-c",
            "user.email=equivalence@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "final",
        )
        return self.run_git(self.workspace, "rev-parse", "HEAD")

    def create(self) -> dict[str, object]:
        return create_commit_equivalence(
            self.bundle,
            self.review_record,
            created_at="2026-07-21T00:00:00+00:00",
        )

    def test_equivalent_commit_generates_and_validates_proof(self) -> None:
        commit = self.commit_source()
        result = self.create()
        validated = validate_commit_equivalence(
            self.bundle,
            self.review_record,
            result["commit_payload"],
            result["evidence_refs"],
        )
        self.assertTrue(validated["equivalent"])
        self.assertEqual(commit, validated["commit"])
        proof = json.loads((self.bundle.task_dir / result["proof_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {"path": "src/added.py", "status": "A"},
                {"path": "src/deleted.py", "status": "D"},
                {"path": "src/existing.py", "status": "M"},
            ],
            proof["file_statuses"],
        )

    def test_untracked_source_disables_fast_path(self) -> None:
        self.commit_source()
        (self.workspace / "unexpected.txt").write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(
            CommitEquivalenceError,
            "RUN_STATE_REVIEW_EQUIVALENCE_DIRTY",
        ):
            self.create()

    def test_hook_like_content_change_disables_fast_path(self) -> None:
        (self.workspace / "src" / "existing.py").write_text(
            "answer = 999\n",
            encoding="utf-8",
        )
        self.commit_source()
        with self.assertRaisesRegex(
            CommitEquivalenceError,
            "RUN_STATE_REVIEW_EQUIVALENCE_MISMATCH",
        ):
            self.create()

    def test_legacy_review_without_report_digest_falls_back(self) -> None:
        self.commit_source()
        self.review_record.pop("report_digest")
        with self.assertRaisesRegex(
            CommitEquivalenceError,
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
        ):
            self.create()

    def test_conditional_dispatch_cannot_use_strict_fast_path(self) -> None:
        self.commit_source()
        dispatch = json.loads(self.dispatch_path.read_text(encoding="utf-8"))
        dispatch["policy"] = "conditional"
        write_json(self.dispatch_path, dispatch)
        receipt = json.loads(self.report_path.read_text(encoding="utf-8"))
        receipt["reviewer"]["dispatch_digest"] = hashlib.sha256(
            self.dispatch_path.read_bytes()
        ).hexdigest()
        write_json(self.report_path, receipt)
        self.review_record["report_digest"] = hashlib.sha256(
            self.report_path.read_bytes()
        ).hexdigest()
        with self.assertRaisesRegex(
            CommitEquivalenceError,
            "RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE",
        ):
            self.create()

    def test_tampered_proof_is_rejected(self) -> None:
        self.commit_source()
        result = self.create()
        proof_path = self.bundle.task_dir / result["proof_ref"]
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        proof["checks"]["manifest_match"] = False
        write_json(proof_path, proof)
        with self.assertRaisesRegex(
            CommitEquivalenceError,
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
        ):
            validate_commit_equivalence(
                self.bundle,
                self.review_record,
                result["commit_payload"],
                result["evidence_refs"],
            )

    def test_partial_proof_reference_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            CommitEquivalenceError,
            "RUN_STATE_REVIEW_EQUIVALENCE_INVALID",
        ):
            validate_commit_equivalence(
                self.bundle,
                self.review_record,
                {
                    "commit": "a" * 40,
                    "repository": ".",
                    "review_equivalence_ref": "artifacts/reviews/equivalences/x.json",
                },
                [],
            )


if __name__ == "__main__":
    unittest.main()
