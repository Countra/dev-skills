from __future__ import annotations

import json
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
)

from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.errors import ReviewError


class ReceiptContractTests(unittest.TestCase):
    def test_valid_code_receipt_passes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            result = validate_receipt(receipt, workspace=root)
            self.assertEqual("passed", result["verdict"])
            self.assertEqual("code-review", result["profile"])

    def test_valid_plan_receipt_passes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_plan_target(root), profile="plan-review")
            result = validate_receipt(receipt, task_dir=root)
            self.assertEqual("managed-plan", result["scope"]["kind"])

    def test_unknown_root_field_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["temporary_note"] = "not canonical"
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_FIELDS_INVALID"):
                validate_receipt(receipt, workspace=root)

    def test_profile_requires_exact_lens_sequence(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["lenses"].pop()
            with self.assertRaisesRegex(ReviewError, "REVIEW_PROFILE_LENSES_INCOMPLETE"):
                validate_receipt(receipt, workspace=root)

    def test_same_context_cannot_claim_independence(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["reviewer"]["independence_claim"] = True
            with self.assertRaisesRegex(ReviewError, "REVIEW_PROVENANCE_CLAIM_INVALID"):
                validate_receipt(receipt, workspace=root)

    def test_open_count_must_match_findings(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["findings"] = [finding(severity="minor")]
            receipt["open_counts"]["minor"] = 0
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_COUNT_MISMATCH"):
                validate_receipt(receipt, workspace=root)

    def test_open_major_requires_changes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["findings"] = [finding()]
            update_counts_and_verdict(receipt)
            result = validate_receipt(receipt, workspace=root)
            self.assertEqual("changes_required", result["verdict"])
            receipt["verdict"] = "passed"
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_VERDICT_MISMATCH"):
                validate_receipt(receipt, workspace=root)

    def test_accepted_major_still_blocks_pass(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["findings"] = [finding(status="accepted")]
            update_counts_and_verdict(receipt)
            self.assertEqual("changes_required", receipt["verdict"])
            validate_receipt(receipt, workspace=root)

    def test_open_minor_is_non_blocking_near_miss(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            receipt["findings"] = [finding(severity="minor")]
            update_counts_and_verdict(receipt)
            self.assertEqual("passed", receipt["verdict"])
            validate_receipt(receipt, workspace=root)

    def test_finding_requires_locator(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
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
            with self.assertRaisesRegex(ReviewError, "REVIEW_FINDING_EVIDENCE_INVALID"):
                validate_receipt(receipt, workspace=root)

    def test_stale_receipt_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root))
            (root / "src" / "example.py").write_text("changed = True\n", encoding="utf-8")
            with self.assertRaisesRegex(ReviewError, "REVIEW_TARGET_STALE"):
                validate_receipt(receipt, workspace=root)

    def test_stage_scope_must_match_target_identity(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            receipt = receipt_for_target(
                target,
                scope={"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
            )
            with self.assertRaisesRegex(ReviewError, "REVIEW_PROFILE_SCOPE_MISMATCH"):
                validate_receipt(receipt, workspace=root)

    def test_supersedes_requires_matching_direct_predecessor(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            previous = receipt_for_target(target)
            current = deepcopy(previous)
            current["review_id"] = "REV-CODE-002"
            current["supersedes_review_id"] = previous["review_id"]
            validate_receipt(current, workspace=root, previous_receipt=previous)
            wrong = deepcopy(previous)
            wrong["review_id"] = "REV-CODE-999"
            with self.assertRaisesRegex(ReviewError, "REVIEW_SUPERSEDES_MISMATCH"):
                validate_receipt(current, workspace=root, previous_receipt=wrong)

    def test_supersedes_rejects_malformed_predecessor(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            previous = receipt_for_target(target)
            current = deepcopy(previous)
            current["review_id"] = "REV-CODE-002"
            current["supersedes_review_id"] = previous["review_id"]
            previous["noncanonical"] = True
            with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_FIELDS_INVALID"):
                validate_receipt(current, workspace=root, previous_receipt=previous)

    def test_template_is_not_accepted_as_evidence(self) -> None:
        template = Path(__file__).resolve().parents[1] / "templates" / "review-report.json"
        receipt = json.loads(template.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ReviewError, "REVIEW_CONTRACT_PLACEHOLDER"):
            validate_receipt(receipt, check_freshness=False)


if __name__ == "__main__":
    unittest.main()
