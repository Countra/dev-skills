"""Pending fingerprint、参数、风险和 sealed approval 测试。"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.actions import ActionExecution  # noqa: E402
from electron_verifier.approval import ApprovalService  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import PendingArtifact  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class FakeSessions:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(live=lambda session_id: SimpleNamespace(page=object()))

    async def status(self, value: str) -> dict:
        return {
            "ok": True,
            "connected": True,
            "session": {"sessionId": "session-1", "name": "demo", "status": "connected", "targetTitle": "Demo"},
        }

    def intent(self, value: str):
        return SimpleNamespace(session_id="session-1")


def config(root: Path):
    return SimpleNamespace(state_root=root, runs_dir=root / "runs", pending_dir=root / "pending")


class ApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def _parameterized_run(self, root: Path) -> tuple[RunService, str, str]:
        runs = RunService(config(root), FakeSessions())
        prepared = asyncio.run(
            runs.prepare(
                {
                    "session": "demo",
                    "appId": "demo",
                    "goal": "填写用户名并保存",
                    "parameterSchema": {"username": {"type": "string", "required": True}},
                }
            )
        )
        seen = []

        async def fake_execute(live, action):
            seen.append(action.value)
            return ActionExecution(
                result={"action": "fill", "postconditions": [{"passed": True}]},
                artifacts=[PendingArtifact("application/json", b'{"verified":true}', "evidence", "json")],
            )

        action = {
            "type": "fill",
            "locator": {"label": "用户名"},
            "value": "${username}",
            "postconditions": [{"type": "value", "locator": {"label": "用户名"}, "expected": "${username}"}],
        }
        with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
            result = asyncio.run(runs.append_action(prepared["runId"], action, {"username": "alice"}))
        self.assertTrue(result["ok"])
        self.assertEqual(["alice"], seen)
        finalized = asyncio.run(runs.finalize(prepared["runId"]))
        self.assertNotIn("alice", runs._journal_path(prepared["runId"]).read_text(encoding="utf-8"))
        return runs, prepared["runId"], finalized["pending"]

    def test_exact_fingerprint_approval_is_content_addressed_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "state"
            KnowledgeReset(root).ensure()
            runs, run_id, _ = self._parameterized_run(root)
            approvals = ApprovalService(CanonicalStore(root), runs)
            preview = approvals.validate(run_id)
            self.assertTrue(preview["approvable"], preview["issues"])
            with self.assertRaises(VerifierError) as wrong:
                approvals.approve(run_id, "0" * 64, "wrong")
            self.assertEqual("approval_fingerprint_mismatch", wrong.exception.code)
            first = approvals.approve(run_id, preview["bundleFingerprint"], "用户确认")
            second = approvals.approve(run_id, preview["bundleFingerprint"], "用户确认")
            self.assertFalse(first["alreadyApproved"])
            self.assertTrue(second["alreadyApproved"])
            self.assertEqual(first["decision"]["assetId"], second["decision"]["assetId"])
            verification = CanonicalStore(root).verify()
            self.assertEqual(1, verification["canonicalAssetCount"])

    def test_modified_pending_invalidates_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "state"
            KnowledgeReset(root).ensure()
            runs, run_id, pending_path = self._parameterized_run(root)
            approvals = ApprovalService(CanonicalStore(root), runs)
            approvals.validate(run_id)
            path = Path(pending_path)
            pending = json.loads(path.read_text(encoding="utf-8"))
            pending["workflow"]["goal"] = "被修改"
            path.write_text(json.dumps(pending), encoding="utf-8")
            with self.assertRaises(VerifierError) as caught:
                approvals.validate(run_id)
            self.assertEqual("pending_fingerprint_invalid", caught.exception.code)

    def test_missing_artifact_blocks_approval(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "state"
            KnowledgeReset(root).ensure()
            runs, run_id, _ = self._parameterized_run(root)
            manifest_path = runs.run_dir(run_id) / "evidence-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            Path(manifest["artifacts"][0]["path"]).unlink()
            preview = ApprovalService(CanonicalStore(root), runs).validate(run_id)
            self.assertFalse(preview["approvable"])
            self.assertIn("path_not_found", {item["code"] for item in preview["issues"]})

    def test_consumed_high_risk_receipt_is_approvable(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "state"
            KnowledgeReset(root).ensure()
            runs = RunService(config(root), FakeSessions())
            prepared = asyncio.run(runs.prepare({"session": "demo", "appId": "demo", "goal": "坐标点击"}))

            async def fake_execute(live, action):
                return ActionExecution(
                    result={"action": "click", "postconditions": [{"passed": True}]},
                    risks=[{"code": "coordinate_action", "learnable": False}],
                )

            action = {
                "type": "click",
                "options": {"coordinates": {"x": 10, "y": 10}},
                "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
            }
            preview = runs.preview_risk(prepared["runId"], action)
            receipt = runs.approve_risk(preview["previewId"], preview["fingerprint"], "确认坐标点击测试")
            with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
                asyncio.run(
                    runs.append_action(prepared["runId"], action, risk_receipt=receipt["receiptId"])
                )
            asyncio.run(runs.finalize(prepared["runId"]))
            preview = ApprovalService(CanonicalStore(root), runs).validate(prepared["runId"])
            self.assertNotIn("risk_confirmation_required", {item["code"] for item in preview["issues"]})

    def test_reject_is_idempotent_and_seals_against_approval(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder) / "state"
            KnowledgeReset(root).ensure()
            runs, run_id, _ = self._parameterized_run(root)
            approvals = ApprovalService(CanonicalStore(root), runs)
            fingerprint = approvals.validate(run_id)["bundleFingerprint"]
            first = approvals.reject(run_id, fingerprint, "不保存")
            second = approvals.reject(run_id, fingerprint, "不保存")
            self.assertFalse(first["alreadyRejected"])
            self.assertTrue(second["alreadyRejected"])
            with self.assertRaises(VerifierError) as caught:
                approvals.approve(run_id, fingerprint, "尝试覆盖")
            self.assertEqual("pending_already_sealed", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
