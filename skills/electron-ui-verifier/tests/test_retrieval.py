"""Hybrid retrieval、硬过滤、abstain 与状态组合测试。"""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402
from knowledge_fixtures import action_asset, runtime_context  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def setUp(self) -> None:
        self.temporary = TestTemporaryDirectory(dir=TEST_ROOT)
        self.state = Path(self.temporary.name) / "state"
        KnowledgeReset(self.state).ensure()
        self.store = CanonicalStore(self.state)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_alias_cjk_and_negative_abstain(self) -> None:
        self.store.activate(
            [
                action_asset("保存设置", ["保存配置", "Save preferences"]),
                action_asset("导出报告", ["下载报告"]),
            ]
        )
        with HybridRetriever(self.store) as retriever:
            exact = retriever.search("保存设置", runtime_context())
            alias = retriever.search("Save preferences", runtime_context())
            cjk = retriever.search("保存配置", runtime_context())
            negative = retriever.search("旋转三维地球", runtime_context())
        self.assertEqual("reuse", exact["decision"])
        self.assertEqual("reuse", alias["decision"])
        self.assertEqual("reuse", cjk["decision"])
        self.assertEqual("abstain", negative["decision"])
        self.assertEqual([], negative["candidates"])

    def test_app_state_and_risk_are_hard_filters(self) -> None:
        high_risk = action_asset("删除环境", [], risk="high")
        other_app = action_asset("保存设置", [], app_id="other")
        self.store.activate([high_risk, other_app])
        with HybridRetriever(self.store) as retriever:
            risk = retriever.search("删除环境", runtime_context(), explain=True)
            state = retriever.search(
                "删除环境",
                runtime_context(pre_state="settings", max_risk="high"),
                explain=True,
            )
            app = retriever.search("保存设置", runtime_context(), explain=True)
        self.assertEqual("abstain", risk["decision"])
        self.assertIn("risk_not_allowed", risk["explain"]["rejected"][0]["reasons"])
        self.assertEqual("abstain", state["decision"])
        self.assertIn("pre_state_mismatch", state["explain"]["rejected"][0]["reasons"])
        self.assertEqual("abstain", app["decision"])

    def test_duplicate_exact_alias_abstains_on_margin(self) -> None:
        self.store.activate(
            [
                action_asset("保存编辑器", ["Save changes"]),
                action_asset("保存配置", ["Save changes"]),
            ]
        )
        with HybridRetriever(self.store) as retriever:
            result = retriever.search("Save changes", runtime_context())
        self.assertEqual("abstain", result["decision"])
        self.assertEqual("ambiguous_margin", result["abstain"]["reason"])

    def test_query_and_context_budgets_fail_closed(self) -> None:
        self.store.activate([action_asset("保存设置", [])])
        with HybridRetriever(self.store) as retriever:
            with self.assertRaises(VerifierError) as query_error:
                retriever.search("x" * 501, runtime_context())
            with self.assertRaises(VerifierError) as app_error:
                retriever.search("保存设置", {"appId": "x" * 201})
        self.assertEqual("knowledge_query_too_long", query_error.exception.code)
        self.assertEqual("invalid_retrieval_context", app_error.exception.code)

    def test_composition_requires_state_edges_and_bound_parameters(self) -> None:
        open_settings = action_asset("打开设置", [], pre_state="home", post_state="settings")
        set_name = action_asset(
            "填写名称",
            [],
            pre_state="settings",
            post_state="name-filled",
            value="${name}",
            parameter_schema={"name": {"type": "string", "required": True}},
        )
        self.store.activate([open_settings, set_name])
        with HybridRetriever(self.store) as retriever:
            result = retriever.compose(
                {
                    **runtime_context(),
                    "subgoals": ["打开设置", "填写名称"],
                    "bindings": {"name": "private-value"},
                }
            )
            with self.assertRaises(VerifierError) as missing:
                retriever.compose(
                    {**runtime_context(), "subgoals": ["打开设置", "填写名称"]}
                )
            with self.assertRaises(VerifierError) as state_missing:
                retriever.compose(
                    {
                        "appId": "demo",
                        "appVersion": "1.0.0",
                        "screenDigest": "screen-main",
                        "subgoals": ["打开设置"],
                        "bindings": {},
                    }
                )
        self.assertEqual("compose", result["decision"])
        self.assertEqual([open_settings.asset_id, set_name.asset_id], result["assetIds"])
        self.assertNotIn("workflow", result)
        self.assertNotIn("private-value", str(result))
        self.assertEqual("parameter_binding_required", missing.exception.code)
        self.assertEqual("composition_pre_state_required", state_missing.exception.code)


if __name__ == "__main__":
    unittest.main()
