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
from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402


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
                    CanonicalAsset.create(
                        kind="workflow",
                        app_id="demo",
                        goal=f"打开面板 {index}",
                        aliases=[f"Open panel {index}"],
                        payload={"workflow": {"goal": f"打开面板 {index}", "steps": [{"type": "snapshot"}]}},
                        evidence=[{"reportDigest": f"{index:x}" * 64}],
                        created_at="2026-07-11T00:00:00Z",
                    )
                )
            store.activate(assets)
            store.activate([assets[0], assets[0]])
            with HybridRetriever(store) as retriever:
                result = retriever.search("Please open panel 3", {"appId": "demo"})
                detail = retriever.get_asset(assets[3].asset_id)
                listing = retriever.list_assets("demo", "workflow", 20)
                stats = retriever.stats()
            encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.assertLessEqual(len(result["candidates"]), 3)
            self.assertLessEqual(len(encoded), 16 * 1024)
            self.assertEqual(assets[3].to_dict(), detail["asset"])
            self.assertEqual(8, listing["count"])
            self.assertEqual({"workflow": 8}, stats["kinds"])


if __name__ == "__main__":
    unittest.main()
