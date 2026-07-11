"""Approved canonical JSON truth 与 derived index rebuild。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import KNOWLEDGE_FORMAT, SCHEMA_VERSION
from .atomic_io import atomic_write_json, canonical_json_bytes, sha256_bytes
from .errors import VerifierError
from .knowledge_index import KnowledgeIndex
from .knowledge_models import CanonicalAsset
from .models import canonical_digest


ASSET_ID = re.compile(r"^(action|workflow)-[0-9a-f]{40}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def knowledge_paths(state_root: Path) -> dict[str, Path]:
    root = state_root / "knowledge"
    return {
        "root": root,
        "manifest": root / "manifest.json",
        "canonical": root / "canonical",
        "derived": root / "derived",
        "index": root / "derived" / "index.sqlite3",
    }


def _base_manifest() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "format": KNOWLEDGE_FORMAT,
        "canonicalDir": "canonical",
        "derivedIndex": "derived/index.sqlite3",
        "assetCount": 0,
        "assets": [],
        "canonicalDigest": canonical_digest([]),
        "createdAt": _now(),
        "updatedAt": _now(),
    }


def replace_directory(source: Path, target: Path) -> None:
    """吸收 Windows 短暂 sharing lock，超过有限窗口后保留原错误。"""

    delay = 0.05
    for attempt in range(8):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.5)


def initialize_knowledge_root(root: Path) -> None:
    """只在不存在的目标上原子启用空 current store。"""

    if root.exists():
        raise VerifierError("knowledge_root_exists", f"knowledge root 已存在：{root}", status=409)
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = root.parent / f".{root.name}.new-{uuid.uuid4()}"
    try:
        (temporary / "canonical").mkdir(parents=True)
        (temporary / "derived").mkdir(parents=True)
        atomic_write_json(temporary / "manifest.json", _base_manifest())
        with KnowledgeIndex(temporary / "derived" / "index.sqlite3") as index:
            index.verify()
        replace_directory(temporary, root)
    except Exception:
        if temporary.exists():
            import shutil

            shutil.rmtree(temporary, ignore_errors=True)
        raise


class CanonicalStore:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.paths = knowledge_paths(state_root)
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        path = self.paths["manifest"]
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("knowledge_reinitialize_required", "knowledge manifest 缺失或无效，需要 fingerprint reset", status=409) from exc
        expected = {
            "schemaVersion": SCHEMA_VERSION,
            "format": KNOWLEDGE_FORMAT,
            "canonicalDir": "canonical",
            "derivedIndex": "derived/index.sqlite3",
        }
        if not isinstance(value, dict) or any(value.get(key) != expected_value for key, expected_value in expected.items()):
            raise VerifierError("knowledge_reinitialize_required", "knowledge manifest 不是当前 canonical format", status=409)
        return value

    def list_assets(self) -> list[tuple[CanonicalAsset, Path]]:
        if not self.paths["canonical"].is_dir():
            raise VerifierError("canonical_store_invalid", "canonical directory 缺失", status=500)
        assets = []
        for path in sorted(self.paths["canonical"].glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise VerifierError("canonical_asset_corrupt", f"canonical asset 无法读取：{path.name}", status=500) from exc
            asset = CanonicalAsset.decode(value)
            if path.name != f"{asset.asset_id}.json":
                raise VerifierError("canonical_asset_corrupt", f"canonical 文件名与 assetId 不匹配：{path.name}", status=500)
            assets.append((asset, path))
        return assets

    def get_asset(self, asset_id: str) -> CanonicalAsset:
        if not ASSET_ID.fullmatch(asset_id):
            raise VerifierError("invalid_asset_id", "assetId 格式无效")
        path = self.paths["canonical"] / f"{asset_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VerifierError("asset_not_found", f"canonical asset 不存在：{asset_id}", status=404) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("canonical_asset_corrupt", f"canonical asset 无法读取：{asset_id}", status=500) from exc
        asset = CanonicalAsset.decode(value)
        if asset.asset_id != asset_id:
            raise VerifierError("canonical_asset_corrupt", "canonical asset identity 不匹配", status=500)
        return asset

    def _update_manifest(self, assets: list[tuple[CanonicalAsset, Path]]) -> None:
        entries = [
            {"assetId": asset.asset_id, "sha256": sha256_bytes(canonical_json_bytes(asset.to_dict()))}
            for asset, _ in assets
        ]
        self._update_manifest_entries(entries)

    def _update_manifest_entries(self, entries: list[dict[str, str]]) -> None:
        entries = sorted(entries, key=lambda item: item["assetId"])
        current = dict(self.manifest)
        current["assetCount"] = len(entries)
        current["assets"] = entries
        current["canonicalDigest"] = canonical_digest(entries)
        current["updatedAt"] = _now()
        atomic_write_json(self.paths["manifest"], current)
        self.manifest = current

    def persist(self, assets: list[CanonicalAsset]) -> list[dict[str, Any]]:
        if not assets:
            return []
        unique_assets: dict[str, CanonicalAsset] = {}
        for asset in assets:
            existing_asset = unique_assets.get(asset.asset_id)
            if existing_asset is not None and existing_asset.to_dict() != asset.to_dict():
                raise VerifierError("canonical_asset_conflict", f"同批 assetId 内容冲突：{asset.asset_id}", status=409)
            unique_assets[asset.asset_id] = asset
        assets = list(unique_assets.values())
        persisted: list[tuple[CanonicalAsset, Path]] = []
        pending_writes: list[tuple[Path, dict[str, Any]]] = []
        for asset in assets:
            path = self.paths["canonical"] / f"{asset.asset_id}.json"
            value = asset.to_dict()
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != value:
                    raise VerifierError("canonical_asset_conflict", f"assetId 内容冲突：{asset.asset_id}", status=409)
            else:
                pending_writes.append((path, value))
            persisted.append((asset, path))
        if pending_writes:
            # 独立文件保持 rename 原子可见，最终 manifest 负责 durable commit；索引仍后置单事务写入。
            workers = min(32, len(pending_writes))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="canonical-write") as executor:
                futures = [
                    executor.submit(atomic_write_json, path, value, pretty=False, durable=False)
                    for path, value in pending_writes
                ]
                for future in futures:
                    future.result()
        with KnowledgeIndex(self.paths["index"]) as index:
            index.upsert(persisted)
            index.verify()
        entries = {
            str(item.get("assetId")): {"assetId": str(item.get("assetId")), "sha256": str(item.get("sha256"))}
            for item in self.manifest.get("assets", [])
            if isinstance(item, dict) and item.get("assetId") and item.get("sha256")
        }
        for asset, _ in persisted:
            entries[asset.asset_id] = {
                "assetId": asset.asset_id,
                "sha256": sha256_bytes(canonical_json_bytes(asset.to_dict())),
            }
        self._update_manifest_entries(list(entries.values()))
        return [asset.to_dict() for asset, _ in persisted]

    def rebuild_index(self) -> dict[str, Any]:
        assets = self.list_assets()
        temporary = self.paths["derived"] / f"index.rebuild-{uuid.uuid4()}.sqlite3"
        try:
            with KnowledgeIndex(temporary) as index:
                index.upsert(assets)
                verification = index.verify()
            os.replace(temporary, self.paths["index"])
        finally:
            temporary.unlink(missing_ok=True)
            Path(str(temporary) + "-journal").unlink(missing_ok=True)
        self._update_manifest(assets)
        return {"rebuilt": True, **verification}

    def verify(self, repair_index: bool = True) -> dict[str, Any]:
        assets = self.list_assets()
        expected_digest = canonical_digest(
            [{"assetId": asset.asset_id, "sha256": sha256_bytes(canonical_json_bytes(asset.to_dict()))} for asset, _ in assets]
        )
        expected_entries = [
            {"assetId": asset.asset_id, "sha256": sha256_bytes(canonical_json_bytes(asset.to_dict()))}
            for asset, _ in assets
        ]
        manifest_rebuilt = False
        if (
            self.manifest.get("assetCount") != len(assets)
            or self.manifest.get("canonicalDigest") != expected_digest
            or self.manifest.get("assets") != expected_entries
        ):
            if not repair_index:
                raise VerifierError("canonical_manifest_mismatch", "canonical manifest count/digest 不匹配", status=500)
            self._update_manifest(assets)
            manifest_rebuilt = True
        try:
            with KnowledgeIndex(self.paths["index"]) as index:
                derived = index.verify()
        except (VerifierError, sqlite3.DatabaseError, OSError):
            if not repair_index:
                raise
            corrupt = self.paths["derived"] / f"index.corrupt-{uuid.uuid4()}.sqlite3"
            if self.paths["index"].exists():
                os.replace(self.paths["index"], corrupt)
            derived = self.rebuild_index()
            derived["quarantined"] = str(corrupt) if corrupt.exists() else None
        if int(derived.get("assetCount", -1)) != len(assets):
            if not repair_index:
                raise VerifierError("knowledge_index_count_mismatch", "derived/canonical asset count 不一致", status=500)
            derived = self.rebuild_index()
        return {
            "canonicalAssetCount": len(assets),
            "canonicalDigest": expected_digest,
            "manifestRebuilt": manifest_rebuilt,
            "derived": derived,
        }
