"""Current canonical knowledge、direct reset 与 derived rebuild 测试。"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.knowledge_index import KnowledgeIndex  # noqa: E402
from electron_verifier.knowledge_models import CanonicalAsset  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


def sample_asset() -> CanonicalAsset:
    return CanonicalAsset.create(
        kind="workflow",
        app_id="demo",
        goal="保存设置",
        aliases=["保存配置"],
        payload={"workflow": {"goal": "保存设置", "steps": [{"type": "click"}]}},
        evidence=[{"reportDigest": "a" * 64}],
        created_at="2026-07-11T00:00:00Z",
    )


class KnowledgeResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_fresh_init_uses_current_manifest_and_rollback_journal(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            state = Path(folder) / "state"
            result = KnowledgeReset(state).ensure()
            self.assertEqual("initialized", result["status"])
            verification = CanonicalStore(state).verify()
            self.assertEqual(0, verification["canonicalAssetCount"])
            self.assertEqual("delete", verification["derived"]["journalMode"])

    def test_legacy_layout_requires_exact_fingerprint_and_is_retired_without_reading(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            state = Path(folder) / "state"
            legacy = state / "knowledge"
            legacy.mkdir(parents=True)
            (legacy / "knowledge.db").write_bytes(b"not-a-sqlite-database")
            (legacy / "workflow.json").write_text("{not-json", encoding="utf-8")
            reset = KnowledgeReset(state)
            with self.assertRaises(VerifierError) as caught:
                reset.ensure()
            self.assertEqual("knowledge_reinitialize_required", caught.exception.code)
            preview = reset.preview()
            with self.assertRaises(VerifierError) as wrong:
                reset.apply("0" * 64)
            self.assertEqual("knowledge_reset_fingerprint_mismatch", wrong.exception.code)
            self.assertTrue((legacy / "knowledge.db").exists())
            applied = reset.apply(preview["confirmationFingerprint"])
            retired = Path(applied["retired"])
            self.assertTrue((retired / "knowledge.db").exists())
            self.assertEqual([], CanonicalStore(state).list_assets())
            self.assertEqual(1, len(list((state / "retired").iterdir())))

    def test_missing_current_root_recovers_without_scanning_retired(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            state = Path(folder) / "state"
            reset = KnowledgeReset(state)
            reset.ensure()
            retired = state / "retired" / "crash-snapshot"
            retired.parent.mkdir()
            os.replace(state / "knowledge", retired)
            (retired / "canonical" / "untrusted.json").write_text("{broken", encoding="utf-8")
            result = reset.ensure()
            self.assertEqual("initialized", result["status"])
            self.assertEqual([], CanonicalStore(state).list_assets())

    def test_canonical_assets_rebuild_corrupt_derived_index(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            state = Path(folder) / "state"
            KnowledgeReset(state).ensure()
            store = CanonicalStore(state)
            store.persist([sample_asset()])
            store.paths["index"].write_bytes(b"corrupt-derived-index")
            verification = CanonicalStore(state).verify()
            self.assertEqual(1, verification["canonicalAssetCount"])
            self.assertEqual(1, verification["derived"]["assetCount"])
            self.assertTrue(verification["derived"].get("quarantined"))

    def test_wal_index_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            path = Path(folder) / "index.sqlite3"
            with KnowledgeIndex(path):
                pass
            connection = sqlite3.connect(path)
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            connection.close()
            self.assertEqual("wal", str(mode).lower())
            with self.assertRaises(VerifierError) as caught:
                KnowledgeIndex(path)
            self.assertEqual("wal_not_allowed", caught.exception.code)

    def test_canonical_first_write_survives_index_failure_and_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            state = Path(folder) / "state"
            KnowledgeReset(state).ensure()
            store = CanonicalStore(state)
            asset = sample_asset()
            with mock.patch(
                "electron_verifier.canonical_store.KnowledgeIndex.upsert",
                side_effect=VerifierError("simulated_index_failure", "simulated"),
            ):
                with self.assertRaises(VerifierError):
                    store.persist([asset])
            canonical_path = store.paths["canonical"] / f"{asset.asset_id}.json"
            self.assertTrue(canonical_path.exists())
            self.assertEqual(0, store.manifest["assetCount"])
            CanonicalStore(state).persist([asset])
            self.assertEqual(1, CanonicalStore(state).verify()["canonicalAssetCount"])


if __name__ == "__main__":
    unittest.main()
