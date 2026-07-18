"""服务端 canonical asset 执行门禁测试。"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory  # noqa: E402
from electron_verifier.actions import ActionExecution  # noqa: E402
from electron_verifier.asset_execution import AssetExecutionService  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402
from knowledge_fixtures import action_asset, runtime_context, workflow_asset  # noqa: E402


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


class AssetExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def setUp(self) -> None:
        self.temporary = TestTemporaryDirectory(dir=TEST_ROOT)
        self.root = Path(self.temporary.name) / "state"
        KnowledgeReset(self.root).ensure()
        self.store = CanonicalStore(self.root)
        self.runs = RunService(config(self.root), FakeSessions())
        self.retriever: HybridRetriever | None = None

    def tearDown(self) -> None:
        if self.retriever is not None:
            self.retriever.close()
        self.temporary.cleanup()

    def _executor(self) -> AssetExecutionService:
        self.retriever = HybridRetriever(self.store)
        return AssetExecutionService(self.store, self.runs, self.retriever.record_outcome)

    def _prepare(self, **overrides: object) -> str:
        payload: dict[str, object] = {"session": "demo", "goal": "复用已批准资产", **runtime_context()}
        payload.update(overrides)
        return str(asyncio.run(self.runs.prepare(payload))["runId"])

    def test_action_is_loaded_bound_and_recorded_only_on_server(self) -> None:
        asset = action_asset(
            "填写名称",
            pre_state="home",
            post_state="name-filled",
            value="${name}",
            parameter_schema={"name": {"type": "string", "required": True}},
        )
        self.store.activate([asset])
        executor = self._executor()
        run_id = self._prepare()
        seen = []

        async def fake_execute(live, action):
            seen.append(action.value)
            return ActionExecution(result={"action": "fill", "postconditions": [{"passed": True}]})

        with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
            result = asyncio.run(executor.execute_action(run_id, asset.asset_id, {"name": "private-name"}, None, None))
        journal = self.runs.load(run_id)
        listing = self.retriever.list_assets("demo", "action", 10)
        self.assertTrue(result["ok"])
        self.assertEqual(["private-name"], seen)
        self.assertEqual(asset.asset_id, journal["steps"][0]["assetId"])
        self.assertEqual("name-filled", journal["steps"][0]["postState"])
        self.assertNotIn("private-name", str(journal))
        self.assertEqual(5, listing["assets"][0]["successCount"])

    def test_wrong_context_and_parameters_fail_before_any_step(self) -> None:
        asset = action_asset(
            "删除环境",
            risk="high",
            value="${name}",
            parameter_schema={"name": {"type": "string", "required": True}},
        )
        self.store.activate([asset])
        executor = self._executor()
        cases = (
            ({"appId": "other", "maxRisk": "high"}, {"name": "x"}, "asset_app_mismatch"),
            ({"appVersion": "2.0.0", "maxRisk": "high"}, {"name": "x"}, "asset_context_mismatch"),
            ({"appVersion": "1.0.0-beta", "maxRisk": "high"}, {"name": "x"}, "asset_context_mismatch"),
            ({"screenDigest": "other-screen", "maxRisk": "high"}, {"name": "x"}, "asset_context_mismatch"),
            ({"preState": "settings", "maxRisk": "high"}, {"name": "x"}, "asset_context_mismatch"),
            ({}, {"name": "x"}, "asset_context_mismatch"),
            ({"maxRisk": "high"}, {}, "parameter_binding_required"),
        )
        for overrides, bindings, code in cases:
            with self.subTest(code=code, overrides=overrides):
                run_id = self._prepare(**overrides)
                with self.assertRaises(VerifierError) as caught:
                    asyncio.run(executor.execute_action(run_id, asset.asset_id, bindings, None, None))
                self.assertEqual(code, caught.exception.code)
                self.assertEqual([], self.runs.load(run_id)["steps"])

    def test_risk_preview_uses_current_run_state(self) -> None:
        asset = action_asset("删除环境", pre_state="home", risk="high")
        self.store.activate([asset])
        executor = self._executor()
        run_id = self._prepare(preState="settings", maxRisk="high")

        with mock.patch.object(self.runs, "preview_risk") as preview:
            with self.assertRaises(VerifierError) as caught:
                executor.preview_risk(run_id, asset.asset_id)

        self.assertEqual("asset_context_mismatch", caught.exception.code)
        preview.assert_not_called()

    def test_workflow_resolves_ordered_action_ids_and_state_edges(self) -> None:
        open_settings = action_asset("打开设置", pre_state="home", post_state="settings")
        save_settings = action_asset(
            "保存设置",
            pre_state="settings",
            post_state="saved",
            value="${name}",
            parameter_schema={"name": {"type": "string", "required": True}},
        )
        workflow = workflow_asset("打开并保存设置", [open_settings, save_settings])
        self.store.activate([open_settings, save_settings, workflow])
        executor = self._executor()
        run_id = self._prepare(goal="打开并保存设置")

        async def fake_execute(live, action):
            return ActionExecution(result={"action": action.action_type, "postconditions": [{"passed": True}]})

        with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
            result = asyncio.run(
                executor.execute_workflow(run_id, workflow.asset_id, {"name": "private-name"}, {}, False, None)
            )
        journal = self.runs.load(run_id)
        self.assertTrue(result["ok"])
        self.assertEqual([open_settings.asset_id, save_settings.asset_id], [step["assetId"] for step in journal["steps"]])
        self.assertEqual(workflow.asset_id, journal["workflow"]["assetId"])
        self.assertEqual("saved", journal["steps"][-1]["postState"])
        self.assertIn("name", journal["parameterSchema"])
        self.assertNotIn("private-name", str(journal))


if __name__ == "__main__":
    unittest.main()
