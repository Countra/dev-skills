"""Knowledge asset API、紧凑输出与 canonical truth 测试。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402
from knowledge_fixtures import action_asset, runtime_context  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class KnowledgeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_get_list_stats_and_compact_search_use_canonical_identity(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            state = Path(folder) / "state"
            KnowledgeReset(state).ensure()
            store = CanonicalStore(state)
            assets = []
            for index in range(8):
                assets.append(
                    action_asset(
                        f"打开面板 {index}",
                        [f"Open panel {index}"],
                        evidence_digest=f"{index:x}" * 64,
                    )
                )
            store.activate(assets)
            store.activate([assets[0], assets[0]])
            with HybridRetriever(store) as retriever:
                result = retriever.search("Please open panel 3", runtime_context())
                detail = retriever.get_asset(assets[3].asset_id)
                listing = retriever.list_assets("demo", "action", 20)
                stats = retriever.stats()
            encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.assertLessEqual(len(result["candidates"]), 3)
            self.assertLessEqual(len(encoded), 16 * 1024)
            self.assertEqual(assets[3].asset_id, detail["asset"]["assetId"])
            self.assertNotIn("payload", detail["asset"])
            self.assertNotIn("action", detail["asset"])
            self.assertEqual(8, listing["count"])
            self.assertEqual({"action": 8}, stats["kinds"])

    def test_created_at_is_part_of_content_addressed_identity(self) -> None:
        asset = action_asset("保存设置", ["保存配置", "Save settings"])
        changed = asset.to_dict()
        changed["createdAt"] = "2026-07-12T00:00:00Z"
        with self.assertRaises(VerifierError) as caught:
            CanonicalAsset.decode(changed)
        self.assertEqual("invalid_asset", caught.exception.code)
        aliases = asset.to_dict()
        aliases["aliases"] = list(reversed(aliases["aliases"]))
        with self.assertRaises(VerifierError) as noncanonical:
            CanonicalAsset.decode(aliases)
        self.assertEqual("invalid_asset", noncanonical.exception.code)


if __name__ == "__main__":
    unittest.main()
