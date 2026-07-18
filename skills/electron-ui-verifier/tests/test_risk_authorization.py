"""独立风险预览、批准和一次性消费契约测试。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.models import ActionSpec, canonical_digest  # noqa: E402
from electron_verifier.risk_authorization import (  # noqa: E402
    RiskAuthorizationService,
    authorization_risks,
    target_identity,
)


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class RiskAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    @staticmethod
    def _action() -> dict:
        return {
            "type": "click",
            "locator": {"role": "button", "accessibleName": "删除", "nth": 0},
            "postconditions": [{"type": "hidden", "locator": {"text": "待删除"}}],
        }

    def test_preview_approval_and_consumption_are_bound_and_one_time(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RiskAuthorizationService(root)
            action = self._action()
            risks = authorization_risks(ActionSpec.decode(action))
            run_id = str(uuid.uuid4())
            digest = canonical_digest(action)
            target = target_identity("session-1", "target-1", "demo")

            preview = service.preview(run_id=run_id, action_digest=digest, target=target, risks=risks)
            first = service.approve(preview["previewId"], preview["fingerprint"], "确认删除测试数据")
            second = service.approve(preview["previewId"], preview["fingerprint"], "确认删除测试数据")
            self.assertEqual(first["receiptId"], second["receiptId"])

            receipt_text = (service.receipts / f'{first["receiptId"]}.json').read_text(encoding="utf-8")
            self.assertNotIn("确认删除测试数据", receipt_text)
            self.assertNotIn("accessibleName", receipt_text)
            self.assertEqual(first["receiptId"], json.loads(receipt_text)["receiptId"])

            consumed = service.consume(
                first["receiptId"],
                run_id=run_id,
                action_digest=digest,
                target=target,
                risks=risks,
            )
            self.assertTrue(consumed["consumed"])
            with self.assertRaises(VerifierError) as caught:
                service.consume(
                    first["receiptId"],
                    run_id=run_id,
                    action_digest=digest,
                    target=target,
                    risks=risks,
                )
            self.assertEqual("risk_authorization_consumed", caught.exception.code)

    def test_missing_or_mismatched_receipt_is_rejected(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            service = RiskAuthorizationService(Path(folder))
            action = self._action()
            risks = authorization_risks(ActionSpec.decode(action))
            run_id = str(uuid.uuid4())
            digest = canonical_digest(action)
            target = target_identity("session-1", "target-1", "demo")

            with self.assertRaises(VerifierError) as missing:
                service.consume(None, run_id=run_id, action_digest=digest, target=target, risks=risks)
            self.assertEqual("risk_authorization_required", missing.exception.code)

            preview = service.preview(run_id=run_id, action_digest=digest, target=target, risks=risks)
            receipt = service.approve(preview["previewId"], preview["fingerprint"], "确认定位风险")
            with self.assertRaises(VerifierError) as mismatch:
                service.consume(
                    receipt["receiptId"],
                    run_id=run_id,
                    action_digest=digest,
                    target=target_identity("session-1", "other-target", "demo"),
                    risks=risks,
                )
            self.assertEqual("risk_authorization_mismatch", mismatch.exception.code)

    def test_coordinate_mutation_requires_independent_risk(self) -> None:
        action = ActionSpec.decode(
            {
                "type": "click",
                "options": {"coordinates": {"x": 10, "y": 20}},
                "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
            }
        )
        self.assertEqual([{"code": "coordinate_action", "learnable": False}], authorization_risks(action))


if __name__ == "__main__":
    unittest.main()
