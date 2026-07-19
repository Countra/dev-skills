from __future__ import annotations

import json
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
)

from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.semantic_result import validate_semantic_result


def link_active_finding(receipt: dict[str, object]) -> None:
    check = receipt["coverage"]["requirement_checks"][0]
    check.update(
        {
            "status": "violated",
            "finding_ids": ["FIND-001"],
            "summary": "当前 requirement 存在未关闭 finding。",
        }
    )


class ReceiptContractTests(unittest.TestCase):
    def test_valid_code_receipt_passes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            result = validate_receipt(receipt, review_root=root / "reviews", workspace=root)
            self.assertEqual("passed", result["verdict"])
            self.assertEqual("code-review", result["profile"])

    def test_valid_plan_receipt_passes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_plan_target(root), root=root, profile="plan-review")
            result = validate_receipt(receipt, review_root=root / "reviews", task_dir=root)
            self.assertEqual("managed-plan", result["scope"]["kind"])

    def test_unknown_root_field_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["temporary_note"] = "not canonical"
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_FIELDS_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_profile_requires_exact_lens_sequence(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["lenses"].pop()
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_same_context_cannot_claim_independence(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["reviewer"]["independence_claim"] = True
            with self.assertRaisesRegex(ReviewError, "REVIEW_PROVENANCE_CLAIM_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_open_count_must_match_findings(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding(severity="minor")]
            link_active_finding(receipt)
            receipt["open_counts"]["minor"] = 0
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_open_major_requires_changes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding()]
            link_active_finding(receipt)
            update_counts_and_verdict(receipt)
            sync_semantic_result(receipt, root)
            result = validate_receipt(receipt, review_root=root / "reviews", workspace=root)
            self.assertEqual("changes_required", result["verdict"])
            receipt["verdict"] = "passed"
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_accepted_major_still_blocks_pass(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding(status="accepted")]
            link_active_finding(receipt)
            update_counts_and_verdict(receipt)
            self.assertEqual("changes_required", receipt["verdict"])
            sync_semantic_result(receipt, root)
            validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_open_minor_is_non_blocking_near_miss(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt["findings"] = [finding(severity="minor")]
            link_active_finding(receipt)
            update_counts_and_verdict(receipt)
            self.assertEqual("passed", receipt["verdict"])
            sync_semantic_result(receipt, root)
            validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_finding_requires_locator(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            invalid = finding()
            invalid["evidence"][0].update(
                {
                    "path": None,
                    "line": None,
                    "symbol": None,
                    "artifact_ref": None,
                    "standard_ref": None,
                }
            )
            receipt["findings"] = [invalid]
            update_counts_and_verdict(receipt)
            sync_semantic_result(receipt, root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_stale_receipt_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            (root / "src" / "example.py").write_text("changed = True\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_STALE"):
                validate_receipt(receipt, review_root=root / "reviews", workspace=root)

    def test_stage_scope_must_match_target_identity(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_PROVENANCE_MISMATCH"):
                receipt_for_target(
                    target,
                    root=root,
                    scope={"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
                )

    def test_supersedes_requires_matching_direct_predecessor(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            previous = receipt_for_target(target, root=root)
            current = receipt_for_target(
                target,
                root=root,
                review_id="REV-CODE-002",
                supersedes_review_id=previous["review_id"],
            )
            validate_receipt(
                current,
                review_root=root / "reviews",
                workspace=root,
                previous_receipt=previous,
            )
            wrong = receipt_for_target(target, root=root, review_id="REV-CODE-999")
            with self.assertRaisesRegex(ReviewError, "REVIEW_SUPERSEDES_MISMATCH"):
                validate_receipt(
                    current,
                    review_root=root / "reviews",
                    workspace=root,
                    previous_receipt=wrong,
                )

    def test_supersedes_rejects_malformed_predecessor(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            previous = receipt_for_target(target, root=root)
            current = receipt_for_target(
                target,
                root=root,
                review_id="REV-CODE-002",
                supersedes_review_id=previous["review_id"],
            )
            previous["noncanonical"] = True
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_FIELDS_INVALID"):
                validate_receipt(
                    current,
                    review_root=root / "reviews",
                    workspace=root,
                    previous_receipt=previous,
                )

    def test_template_is_not_accepted_as_evidence(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            template = (
                Path(__file__).resolve().parents[1]
                / "templates"
                / "review-semantic-result.json"
            )
            semantic = json.loads(template.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ReviewError, "REVIEW_RESULT_INVALID"):
                validate_semantic_result(
                    semantic,
                    target=receipt["target"],
                    context=receipt["context"],
                )


if __name__ == "__main__":
    unittest.main()
