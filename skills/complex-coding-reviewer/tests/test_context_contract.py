from __future__ import annotations

import json
import subprocess
import unittest
from copy import deepcopy
from pathlib import Path

from helpers import (
    create_file_target,
    create_plan_target,
    finding,
    receipt_for_target,
    update_counts_and_verdict,
    writable_tempdir,
    write_json,
)

from complex_coding_reviewer.context import build_context_target
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.package import build_review_package
from complex_coding_reviewer.target import build_commit_range_target


def gap(*, severity: str = "major") -> dict[str, object]:
    return {
        "id": "GAP-001",
        "requirement_ref": "REQ-UNIT",
        "category": "correctness",
        "claim": "当前证据无法证明边界行为。",
        "needed_evidence": "需要当前 target 上的边界测试结果。",
        "owner": "caller",
        "severity": severity,
        "evidence_refs": ["review-brief.json"],
    }


def rebuild_context(receipt: dict[str, object], root: Path) -> None:
    context = receipt["context"]
    assert isinstance(context, dict)
    manifest = context["manifest"]
    assert isinstance(manifest, list)
    receipt["context"] = build_context_target(
        root,
        root_kind="workspace",
        label=str(context["identity"]["label"]),
        entries=[(str(item["path"]), str(item["role"])) for item in manifest],
    )


class ContextContractTests(unittest.TestCase):
    def test_context_order_has_stable_digest(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            create_file_target(root)
            write_json(
                root / "review-brief.json",
                {
                    "profile": "code-review",
                    "scope": {"kind": "standalone"},
                    "summary": "检查稳定 context digest。",
                    "requirement_refs": ["REQ-UNIT"],
                    "constraint_refs": [],
                    "claim_refs": [],
                    "requested_risk_focus": [],
                    "created_at": "2026-07-16T00:00:00+00:00",
                },
            )
            entries = [("review-brief.json", "brief"), ("src/example.py", "adjacent-code")]
            first = build_context_target(root, root_kind="workspace", label="stable", entries=entries)
            second = build_context_target(root, root_kind="workspace", label="stable", entries=reversed(entries))
            self.assertEqual(first["digest"], second["digest"])

    def test_context_mutation_makes_receipt_stale(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            brief = root / "review-brief.json"
            brief.write_text(brief.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTEXT_STALE"):
                validate_receipt(receipt, workspace=root)

    def test_sensitive_context_path_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt_for_target(create_file_target(root), root=root)
            (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTEXT_SECRET_PATH"):
                build_context_target(
                    root,
                    root_kind="workspace",
                    label="unsafe",
                    entries=[("review-brief.json", "brief"), (".env", "config")],
                )

    def test_target_coverage_must_match_manifest(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["coverage"]["target_paths"].clear()
            with self.assertRaisesRegex(ReviewError, "REVIEW_COVERAGE_TARGET_MISMATCH"):
                validate_receipt(receipt, workspace=root)

    def test_not_verifiable_requirement_requires_gap(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            check = receipt["coverage"]["requirement_checks"][0]
            check.update({"status": "not-verifiable", "finding_ids": [], "gap_ids": []})
            with self.assertRaisesRegex(ReviewError, "REVIEW_COVERAGE_GAP_MISSING"):
                validate_receipt(receipt, workspace=root)

    def test_major_gap_derives_blocked_verdict(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["verification_gaps"] = [gap()]
            check = receipt["coverage"]["requirement_checks"][0]
            check.update(
                {
                    "status": "not-verifiable",
                    "finding_ids": [],
                    "gap_ids": ["GAP-001"],
                    "summary": "当前要求缺少可观察证据。",
                }
            )
            update_counts_and_verdict(receipt)
            self.assertEqual("blocked", validate_receipt(receipt, workspace=root)["verdict"])
            receipt["verdict"] = "passed"
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_VERDICT_MISMATCH"):
                validate_receipt(receipt, workspace=root)

    def test_requested_risk_cannot_be_marked_not_triggered(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            brief_path = root / "review-brief.json"
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["requested_risk_focus"] = ["security-privacy"]
            write_json(brief_path, brief)
            rebuild_context(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_COVERAGE_RISK_UNREVIEWED"):
                validate_receipt(receipt, workspace=root)

    def test_finding_evidence_must_be_in_target_or_context(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            invalid = finding()
            invalid["evidence"][0]["path"] = "outside.py"
            receipt["findings"] = [invalid]
            update_counts_and_verdict(receipt)
            with self.assertRaisesRegex(ReviewError, "REVIEW_FINDING_EVIDENCE_INVALID"):
                validate_receipt(receipt, workspace=root)

    def test_lens_evidence_must_be_in_target_or_context(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["lenses"][0]["evidence_refs"] = ["outside.py"]
            with self.assertRaisesRegex(ReviewError, "REVIEW_COVERAGE_EVIDENCE_INVALID"):
                validate_receipt(receipt, workspace=root)

    def test_brief_claim_must_reference_present_context_entry(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            brief_path = root / "review-brief.json"
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["claim_refs"] = ["validation.txt"]
            write_json(brief_path, brief)
            validation = root / "validation.txt"
            validation.write_text("passed\n", encoding="utf-8")
            receipt["context"] = build_context_target(
                root,
                root_kind="workspace",
                label="deleted-claim",
                entries=[
                    ("review-brief.json", "brief"),
                    ("src/example.py", "adjacent-code"),
                    ("validation.txt", "validation"),
                ],
            )
            validation.unlink()
            claim_entry = next(
                item
                for item in receipt["context"]["manifest"]
                if item["path"] == "validation.txt"
            )
            claim_entry.update({"state": "deleted", "sha256": None, "size": None})
            from complex_coding_reviewer.context import _finalize

            receipt["context"] = _finalize(
                "workspace",
                "deleted-claim",
                receipt["context"]["manifest"],
            )
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTEXT_CLAIM_UNBOUND"):
                validate_receipt(receipt, workspace=root)

    def test_every_finding_must_be_linked_from_coverage(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding(severity="minor")]
            update_counts_and_verdict(receipt)
            with self.assertRaisesRegex(ReviewError, "REVIEW_COVERAGE_LINK_INCOMPLETE"):
                validate_receipt(receipt, workspace=root)

    def test_superseding_attempt_accounts_for_open_findings(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            previous = receipt_for_target(create_file_target(root), root=root)
            previous["findings"] = [finding()]
            previous_check = previous["coverage"]["requirement_checks"][0]
            previous_check.update(
                {
                    "status": "violated",
                    "finding_ids": ["FIND-001"],
                    "gap_ids": [],
                    "summary": "当前实现违反边界要求。",
                }
            )
            update_counts_and_verdict(previous)
            validate_receipt(previous, workspace=root)

            current = deepcopy(previous)
            current["review_id"] = "REV-CODE-002"
            current["supersedes_review_id"] = previous["review_id"]
            current["findings"] = []
            current_check = current["coverage"]["requirement_checks"][0]
            current_check.update(
                {
                    "status": "satisfied",
                    "finding_ids": [],
                    "summary": "边界要求现已满足。",
                }
            )
            update_counts_and_verdict(current)
            with self.assertRaisesRegex(ReviewError, "REVIEW_LINEAGE_ACCOUNTING_INCOMPLETE"):
                validate_receipt(current, workspace=root, previous_receipt=previous)

            inherited = finding(status="resolved")
            inherited["origin"] = {
                "review_id": previous["review_id"],
                "finding_id": "FIND-001",
            }
            current["findings"] = [inherited]
            update_counts_and_verdict(current)
            result = validate_receipt(current, workspace=root, previous_receipt=previous)
            self.assertEqual(1, result["lineage_summary"]["accounted_finding_count"])

    def test_package_binds_both_digests_without_execution(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            package = build_review_package(
                receipt["target"],
                receipt["context"],
                workspace=root,
                generated_at="2026-07-16T00:00:00+00:00",
            )
            self.assertEqual(receipt["target"]["digest"], package["target_digest"])
            self.assertEqual(receipt["context"]["digest"], package["context_digest"])
            self.assertFalse(package["truncated"])
            self.assertGreater(package["path_count"], 0)

    def test_commit_range_package_reads_head_object_not_worktree(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)

            def git(*arguments: str) -> str:
                completed = subprocess.run(
                    ["git", "-C", str(root), *arguments],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )
                return completed.stdout.strip()

            git("init", "--quiet")
            git("config", "user.email", "reviewer@example.invalid")
            git("config", "user.name", "Reviewer Test")
            tracked = root / "tracked.txt"
            tracked.write_text("baseline\n", encoding="utf-8")
            git("add", "tracked.txt")
            git("commit", "--quiet", "-m", "baseline")
            baseline = git("rev-parse", "HEAD")
            tracked.write_text("committed-head\n", encoding="utf-8")
            git("add", "tracked.txt")
            git("commit", "--quiet", "-m", "head")
            head = git("rev-parse", "HEAD")
            target = build_commit_range_target(
                root,
                baseline=baseline,
                head=head,
                paths=["tracked.txt"],
            )
            receipt = receipt_for_target(target, root=root)
            receipt["context"] = build_context_target(
                root,
                root_kind="workspace",
                label="commit-range-context",
                entries=[("review-brief.json", "brief")],
            )
            tracked.write_text("working-tree-only\n", encoding="utf-8")
            package = build_review_package(
                target,
                receipt["context"],
                workspace=root,
                generated_at="2026-07-16T00:00:00+00:00",
            )
            entry = next(
                item
                for item in package["entries"]
                if item["source"] == "target" and item["path"] == "tracked.txt"
            )
            self.assertIn("committed-head", entry["content"])
            self.assertNotIn("working-tree-only", entry["content"])

    def test_plan_package_only_requires_task_directory(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(
                create_plan_target(root),
                root=root,
                profile="plan-review",
            )
            package = build_review_package(
                receipt["target"],
                receipt["context"],
                task_dir=root,
                generated_at="2026-07-16T00:00:00+00:00",
            )
            self.assertEqual(receipt["target"]["digest"], package["target_digest"])
            self.assertIsNone(package["git"])


if __name__ == "__main__":
    unittest.main()
