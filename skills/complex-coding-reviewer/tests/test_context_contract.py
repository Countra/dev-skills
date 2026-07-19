from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from helpers import (
    create_file_target,
    create_plan_target,
    finding,
    receipt_for_target,
    sync_semantic_result,
    update_counts_and_verdict,
    writable_tempdir,
    write_json,
)

from complex_coding_reviewer.context import (
    build_context_target,
    load_context_brief,
    validate_review_brief,
)
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.package import build_review_package
from complex_coding_reviewer.target import build_commit_range_target


def brief_relative(receipt: dict[str, object]) -> str:
    context = receipt["context"]
    assert isinstance(context, dict)
    return next(
        str(item["path"])
        for item in context["manifest"]
        if item["role"] == "brief"
    )


def gap(evidence_ref: str, *, severity: str = "major") -> dict[str, object]:
    return {
        "id": "GAP-001",
        "requirement_ref": "REQ-UNIT",
        "category": "correctness",
        "claim": "当前证据无法证明边界行为。",
        "needed_evidence": "需要当前 target 上的边界测试结果。",
        "owner": "caller",
        "severity": severity,
        "evidence_refs": [evidence_ref],
    }


class ContextContractTests(unittest.TestCase):
    def test_multiple_requested_risks_use_domain_order(self) -> None:
        brief = {
            "profile": "code-review",
            "scope": {"kind": "standalone"},
            "summary": "验证多个风险焦点的业务顺序。",
            "requirement_refs": ["REQ-UNIT"],
            "constraint_refs": [],
            "claim_refs": [],
            "requested_risk_focus": [
                "security-privacy",
                "api-data-compatibility",
                "removal-dependencies",
            ],
            "created_at": "2026-07-16T00:00:00+00:00",
        }
        validated = validate_review_brief(brief)
        self.assertEqual(brief["requested_risk_focus"], validated["requested_risk_focus"])
        brief["requested_risk_focus"] = list(reversed(brief["requested_risk_focus"]))
        with self.assertRaisesRegex(ReviewError, "REVIEW_CONTEXT_ORDER_INVALID"):
            validate_review_brief(brief)

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
            brief = root / brief_relative(receipt)
            brief.write_text(brief.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_STALE"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_sensitive_context_path_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTEXT_SECRET_PATH"):
                build_context_target(
                    root,
                    root_kind="workspace",
                    label="unsafe",
                    entries=[(brief_relative(receipt), "brief"), (".env", "config")],
                )

    def test_target_coverage_must_match_manifest(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["coverage"]["target_paths"].clear()
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_not_verifiable_requirement_requires_gap(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            check = receipt["coverage"]["requirement_checks"][0]
            check.update({"status": "not-verifiable", "finding_ids": [], "gap_ids": []})
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_major_gap_derives_blocked_verdict(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["verification_gaps"] = [gap(brief_relative(receipt))]
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
            sync_semantic_result(receipt, root)
            self.assertEqual(
                "blocked",
                validate_receipt(
                    receipt,
                    review_root=root / "reviews",
                    workspace=root,
                )["verdict"],
            )
            receipt["verdict"] = "passed"
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_requested_risk_cannot_be_marked_not_triggered(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            brief_path = root / brief_relative(receipt)
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["requested_risk_focus"] = ["security-privacy"]
            write_json(brief_path, brief)
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_STALE"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_finding_evidence_must_be_in_target_or_context(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            invalid = finding()
            invalid["evidence"][0]["path"] = "outside.py"
            receipt["findings"] = [invalid]
            update_counts_and_verdict(receipt)
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_lens_evidence_must_be_in_target_or_context(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["lenses"][0]["evidence_refs"] = ["outside.py"]
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_brief_claim_must_reference_present_context_entry(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            brief_ref = brief_relative(receipt)
            brief_path = root / brief_ref
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["claim_refs"] = ["validation.txt"]
            write_json(brief_path, brief)
            validation = root / "validation.txt"
            validation.write_text("passed\n", encoding="utf-8")
            context = build_context_target(
                root,
                root_kind="workspace",
                label="deleted-claim",
                entries=[
                    (brief_ref, "brief"),
                    ("src/example.py", "adjacent-code"),
                    ("validation.txt", "validation"),
                ],
            )
            validation.unlink()
            claim_entry = next(
                item
                for item in context["manifest"]
                if item["path"] == "validation.txt"
            )
            claim_entry.update({"state": "deleted", "sha256": None, "size": None})
            from complex_coding_reviewer.context import _finalize

            context = _finalize(
                "workspace",
                "deleted-claim",
                context["manifest"],
            )
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTEXT_CLAIM_UNBOUND"):
                load_context_brief(context, workspace=root)

    def test_every_finding_must_be_linked_from_coverage(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding(severity="minor")]
            update_counts_and_verdict(receipt)
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

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
            sync_semantic_result(previous, root)
            validate_receipt(
                previous,
                review_root=root / "reviews",
                workspace=root,
            )

            current = receipt_for_target(
                previous["target"],
                root=root,
                review_id="REV-CODE-002",
                supersedes_review_id=previous["review_id"],
            )
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
            sync_semantic_result(current, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_LINEAGE_ACCOUNTING_INCOMPLETE"):
                validate_receipt(
                    current,
                    review_root=root / "reviews",
                    workspace=root,
                    previous_receipt=previous,
                )

            inherited = finding(status="resolved")
            inherited["origin"] = {
                "review_id": previous["review_id"],
                "finding_id": "FIND-001",
            }
            current["findings"] = [inherited]
            update_counts_and_verdict(current)
            sync_semantic_result(current, root)
            result = validate_receipt(
                current,
                review_root=root / "reviews",
                workspace=root,
                previous_receipt=previous,
            )
            self.assertEqual(1, result["lineage_summary"]["accounted_finding_count"])

    def test_unresolved_lineage_cannot_downgrade_severity(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            previous = receipt_for_target(create_file_target(root), root=root)
            previous["findings"] = [finding(severity="major")]
            previous["coverage"]["requirement_checks"][0].update(
                {
                    "status": "violated",
                    "finding_ids": ["FIND-001"],
                    "gap_ids": [],
                    "summary": "当前实现存在 major finding。",
                }
            )
            update_counts_and_verdict(previous)
            sync_semantic_result(previous, root)
            current = receipt_for_target(
                previous["target"],
                root=root,
                review_id="REV-CODE-002",
                supersedes_review_id=previous["review_id"],
            )
            current["findings"] = [finding(severity="major")]
            current["findings"][0]["severity"] = "minor"
            current["findings"][0]["origin"] = {
                "review_id": previous["review_id"],
                "finding_id": "FIND-001",
            }
            current["coverage"]["requirement_checks"][0].update(
                {
                    "status": "violated",
                    "finding_ids": ["FIND-001"],
                    "gap_ids": [],
                    "summary": "当前 finding 尚未关闭。",
                }
            )
            update_counts_and_verdict(current)
            sync_semantic_result(current, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_LINEAGE_SEVERITY_DOWNGRADE"):
                validate_receipt(
                    current,
                    review_root=root / "reviews",
                    workspace=root,
                    previous_receipt=previous,
                )

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

    def test_package_rejects_stale_file_target(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            (root / "src" / "example.py").write_text("changed = True\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_TARGET_STALE"):
                build_review_package(
                    receipt["target"],
                    receipt["context"],
                    workspace=root,
                )

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
            context = build_context_target(
                root,
                root_kind="workspace",
                label="commit-range-context",
                entries=[(brief_relative(receipt), "brief")],
            )
            tracked.write_text("working-tree-only\n", encoding="utf-8")
            package = build_review_package(
                target,
                context,
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
