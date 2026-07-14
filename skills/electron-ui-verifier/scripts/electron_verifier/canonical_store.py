"""Immutable knowledge objects、sealed decisions 与可重建索引。"""

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
from typing import Any, Callable

from . import KNOWLEDGE_FORMAT, SCHEMA_VERSION
from .atomic_io import atomic_write_json, canonical_json_bytes, exclusive_write_json, sha256_bytes
from .errors import VerifierError
from .knowledge_index import KnowledgeIndex
from .knowledge_models import CanonicalAsset
from .models import canonical_digest


ASSET_ID = re.compile(r"^(action|workflow)-[0-9a-f]{40}$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
DECISION_FIELDS = {
    "schemaVersion",
    "format",
    "status",
    "bundleFingerprint",
    "runId",
    "assetIds",
    "message",
    "createdAt",
    "decisionDigest",
}
FaultInjector = Callable[[str], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def knowledge_paths(state_root: Path) -> dict[str, Path]:
    root = state_root / "knowledge"
    return {
        "root": root,
        "manifest": root / "manifest.json",
        "objects": root / "objects",
        "decisions": root / "decisions",
        "derived": root / "derived",
        "index": root / "derived" / "index.sqlite3",
    }


def _base_manifest() -> dict[str, Any]:
    now = _now()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "format": KNOWLEDGE_FORMAT,
        "objectsDir": "objects",
        "decisionsDir": "decisions",
        "derivedIndex": "derived/index.sqlite3",
        "generation": 0,
        "activeAssetCount": 0,
        "activeDigest": canonical_digest([]),
        "decisionDigest": canonical_digest([]),
        "createdAt": now,
        "updatedAt": now,
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
    """只在不存在的目标上原子启用空 sealed store。"""

    if root.exists():
        raise VerifierError("knowledge_root_exists", "knowledge root 已存在", status=409)
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = root.parent / f".{root.name}.new-{uuid.uuid4()}"
    try:
        for name in ("objects", "decisions", "derived"):
            (temporary / name).mkdir(parents=True)
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
    """以 approved decision 可达图作为唯一知识真相。"""

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.paths = knowledge_paths(state_root)
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        try:
            value = json.loads(self.paths["manifest"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError(
                "knowledge_reinitialize_required",
                "knowledge manifest 缺失或无效，需要 fingerprint reset",
                status=409,
            ) from exc
        expected = {
            "schemaVersion": SCHEMA_VERSION,
            "format": KNOWLEDGE_FORMAT,
            "objectsDir": "objects",
            "decisionsDir": "decisions",
            "derivedIndex": "derived/index.sqlite3",
        }
        if not isinstance(value, dict) or any(value.get(key) != item for key, item in expected.items()):
            raise VerifierError(
                "knowledge_reinitialize_required",
                "knowledge manifest 不是当前 sealed format",
                status=409,
            )
        if not self.paths["objects"].is_dir() or not self.paths["decisions"].is_dir():
            raise VerifierError("knowledge_store_invalid", "objects 或 decisions 目录缺失", status=500)
        return value

    def _object_path(self, asset_id: str) -> Path:
        if not ASSET_ID.fullmatch(asset_id):
            raise VerifierError("invalid_asset_id", "assetId 格式无效")
        return self.paths["objects"] / f"{asset_id}.json"

    def _decision_path(self, fingerprint: str) -> Path:
        if not FINGERPRINT.fullmatch(fingerprint):
            raise VerifierError("invalid_bundle_fingerprint", "bundleFingerprint 必须是 SHA-256")
        return self.paths["decisions"] / f"{fingerprint}.json"

    def _load_object(self, asset_id: str) -> tuple[CanonicalAsset, Path]:
        path = self._object_path(asset_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VerifierError("activation_object_missing", f"decision 引用对象不存在：{asset_id}", status=500) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("knowledge_object_corrupt", f"knowledge object 无法读取：{asset_id}", status=500) from exc
        asset = CanonicalAsset.decode(value)
        if asset.asset_id != asset_id or path.name != f"{asset.asset_id}.json":
            raise VerifierError("knowledge_object_corrupt", "knowledge object identity 不匹配", status=500)
        return asset, path

    def _load_decision_path(self, path: Path) -> dict[str, Any]:
        try:
            decision = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("decision_invalid", f"sealed decision 无法读取：{path.name}", status=500) from exc
        if not isinstance(decision, dict) or set(decision) != DECISION_FIELDS:
            raise VerifierError("decision_invalid", "sealed decision 字段不完整或包含未知字段", status=500)
        if decision.get("schemaVersion") != SCHEMA_VERSION or decision.get("format") != KNOWLEDGE_FORMAT:
            raise VerifierError("decision_invalid", "sealed decision format 不匹配", status=500)
        fingerprint = str(decision.get("bundleFingerprint") or "")
        if path.name != f"{fingerprint}.json" or not FINGERPRINT.fullmatch(fingerprint):
            raise VerifierError("decision_invalid", "sealed decision identity 不匹配", status=500)
        status = decision.get("status")
        asset_ids = decision.get("assetIds")
        if status not in {"approved", "rejected"} or not isinstance(asset_ids, list):
            raise VerifierError("decision_invalid", "sealed decision status/assetIds 无效", status=500)
        if len(set(asset_ids)) != len(asset_ids) or any(not isinstance(item, str) or not ASSET_ID.fullmatch(item) for item in asset_ids):
            raise VerifierError("decision_invalid", "sealed decision assetIds 无效或重复", status=500)
        if status == "approved" and not asset_ids or status == "rejected" and asset_ids:
            raise VerifierError("decision_invalid", "sealed decision 状态与 assetIds 不一致", status=500)
        try:
            parsed_run_id = uuid.UUID(str(decision.get("runId") or ""))
            datetime.fromisoformat(str(decision.get("createdAt") or "").replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise VerifierError("decision_invalid", "sealed decision runId/createdAt 无效", status=500) from exc
        if parsed_run_id.int == 0 or not isinstance(decision.get("message"), str):
            raise VerifierError("decision_invalid", "sealed decision runId/message 无效", status=500)
        unsigned = dict(decision)
        supplied = str(unsigned.pop("decisionDigest") or "")
        expected = canonical_digest(unsigned)
        if supplied != expected:
            raise VerifierError("decision_invalid", "sealed decision digest 不匹配", status=500)
        return decision

    def get_decision(self, fingerprint: str) -> dict[str, Any] | None:
        path = self._decision_path(fingerprint)
        return self._load_decision_path(path) if path.exists() else None

    def list_decisions(self) -> list[dict[str, Any]]:
        return [self._load_decision_path(path) for path in sorted(self.paths["decisions"].glob("*.json"))]

    def stage_objects(self, assets: list[CanonicalAsset]) -> list[dict[str, Any]]:
        unique: dict[str, CanonicalAsset] = {}
        for asset in assets:
            prior = unique.get(asset.asset_id)
            if prior is not None and prior.to_dict() != asset.to_dict():
                raise VerifierError("knowledge_object_conflict", f"同批 assetId 内容冲突：{asset.asset_id}", status=409)
            unique[asset.asset_id] = asset
        writes: list[tuple[Path, dict[str, Any]]] = []
        for asset in unique.values():
            path = self._object_path(asset.asset_id)
            value = asset.to_dict()
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise VerifierError("knowledge_object_corrupt", f"knowledge object 无法读取：{asset.asset_id}", status=500) from exc
                if existing != value:
                    raise VerifierError("knowledge_object_conflict", f"assetId 内容冲突：{asset.asset_id}", status=409)
            else:
                writes.append((path, value))
        if writes:
            with ThreadPoolExecutor(max_workers=min(16, len(writes)), thread_name_prefix="knowledge-object-write") as executor:
                futures = [executor.submit(atomic_write_json, path, value, pretty=False) for path, value in writes]
                for future in futures:
                    future.result()
        return [unique[asset_id].to_dict() for asset_id in sorted(unique)]

    def seal_decision(
        self,
        *,
        status: str,
        bundle_fingerprint: str,
        run_id: str,
        asset_ids: list[str],
        message: str,
    ) -> tuple[dict[str, Any], bool]:
        path = self._decision_path(bundle_fingerprint)
        if not isinstance(asset_ids, list) or not all(isinstance(item, str) for item in asset_ids):
            raise VerifierError("decision_invalid", "decision assetIds 必须是字符串数组")
        if not isinstance(message, str) or not message.strip():
            raise VerifierError("decision_invalid", "decision message 必须是非空字符串")
        try:
            normalized_run_id = str(uuid.UUID(str(run_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise VerifierError("decision_invalid", "decision runId 必须是非零 UUID") from exc
        if uuid.UUID(normalized_run_id).int == 0:
            raise VerifierError("decision_invalid", "decision runId 必须是非零 UUID")
        normalized_ids = sorted(set(asset_ids))
        if status not in {"approved", "rejected"}:
            raise VerifierError("decision_invalid", "decision status 只允许 approved/rejected")
        if status == "approved":
            if not normalized_ids:
                raise VerifierError("decision_invalid", "approved decision 至少需要一个 assetId")
            for asset_id in normalized_ids:
                self._load_object(asset_id)
        elif normalized_ids:
            raise VerifierError("decision_invalid", "rejected decision 不允许引用 asset")
        unsigned = {
            "schemaVersion": SCHEMA_VERSION,
            "format": KNOWLEDGE_FORMAT,
            "status": status,
            "bundleFingerprint": bundle_fingerprint,
            "runId": normalized_run_id,
            "assetIds": normalized_ids,
            "message": message.strip()[:1000],
            "createdAt": _now(),
        }
        decision = {**unsigned, "decisionDigest": canonical_digest(unsigned)}
        if path.exists():
            existing = self._load_decision_path(path)
            identity = ("status", "bundleFingerprint", "runId", "assetIds")
            if any(existing.get(key) != decision.get(key) for key in identity):
                raise VerifierError("decision_conflict", "bundleFingerprint 已由不同 decision sealed", status=409)
            return existing, False
        if not exclusive_write_json(path, decision):
            existing = self._load_decision_path(path)
            identity = ("status", "bundleFingerprint", "runId", "assetIds")
            if any(existing.get(key) != decision.get(key) for key in identity):
                raise VerifierError("decision_conflict", "bundleFingerprint 并发提交冲突", status=409)
            return existing, False
        return decision, True

    def _active_asset_ids(self) -> set[str]:
        return {
            asset_id
            for decision in self.list_decisions()
            if decision["status"] == "approved"
            for asset_id in decision["assetIds"]
        }

    def _active_assets(self) -> list[tuple[CanonicalAsset, Path]]:
        return [self._load_object(asset_id) for asset_id in sorted(self._active_asset_ids())]

    def list_assets(self) -> list[tuple[CanonicalAsset, Path]]:
        return self._active_assets()

    def get_asset(self, asset_id: str) -> CanonicalAsset:
        if asset_id not in self._active_asset_ids():
            raise VerifierError("asset_not_found", f"approved asset 不存在：{asset_id}", status=404)
        return self._load_object(asset_id)[0]

    @staticmethod
    def _asset_entries(assets: list[tuple[CanonicalAsset, Path]]) -> list[dict[str, str]]:
        return [
            {"assetId": asset.asset_id, "sha256": sha256_bytes(canonical_json_bytes(asset.to_dict()))}
            for asset, _ in assets
        ]

    def _update_manifest(self, assets: list[tuple[CanonicalAsset, Path]], decisions: list[dict[str, Any]]) -> None:
        entries = self._asset_entries(assets)
        current = dict(self.manifest)
        current["generation"] = int(current.get("generation", 0)) + 1
        current["activeAssetCount"] = len(entries)
        current["activeDigest"] = canonical_digest(entries)
        current["decisionDigest"] = canonical_digest(
            [{"bundleFingerprint": item["bundleFingerprint"], "decisionDigest": item["decisionDigest"]} for item in decisions]
        )
        current["updatedAt"] = _now()
        atomic_write_json(self.paths["manifest"], current)
        self.manifest = current

    def rebuild_index(self) -> dict[str, Any]:
        assets = self._active_assets()
        decisions = self.list_decisions()
        target_journal = Path(str(self.paths["index"]) + "-journal")
        if target_journal.exists():
            stale_journal = self.paths["derived"] / f"index.stale-{uuid.uuid4()}.sqlite3-journal"
            os.replace(target_journal, stale_journal)
        reliability: dict[str, dict[str, Any]] = {}
        if self.paths["index"].exists():
            try:
                with KnowledgeIndex(self.paths["index"]) as current_index:
                    reliability = current_index.reliability_snapshot()
            except (VerifierError, sqlite3.Error, OSError):
                # 损坏或旧版索引不能成为恢复来源，回退到 canonical 资产中的保守基线。
                reliability = {}
        temporary = self.paths["derived"] / f"index.rebuild-{uuid.uuid4()}.sqlite3"
        try:
            with KnowledgeIndex(temporary) as index:
                index.upsert(assets)
                index.restore_reliability(reliability)
                verification = index.verify()
            os.replace(temporary, self.paths["index"])
        finally:
            temporary.unlink(missing_ok=True)
            Path(str(temporary) + "-journal").unlink(missing_ok=True)
        self._update_manifest(assets, decisions)
        return {
            "rebuilt": True,
            "generation": self.manifest["generation"],
            "activeAssetCount": len(assets),
            **verification,
        }

    def activate(
        self,
        assets: list[CanonicalAsset],
        *,
        bundle_fingerprint: str | None = None,
        run_id: str | None = None,
        message: str = "internal activation",
        fault_injector: FaultInjector | None = None,
    ) -> dict[str, Any]:
        unique_ids = sorted({asset.asset_id for asset in assets})
        fingerprint = bundle_fingerprint or canonical_digest({"assetIds": unique_ids})
        activation_run = run_id or str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))
        staged = self.stage_objects(assets)
        if fault_injector:
            fault_injector("after_objects")
        decision, created = self.seal_decision(
            status="approved",
            bundle_fingerprint=fingerprint,
            run_id=activation_run,
            asset_ids=unique_ids,
            message=message,
        )
        if fault_injector:
            fault_injector("after_decision")
        index = self.rebuild_index()
        if fault_injector:
            fault_injector("after_index")
        return {"assets": staged, "decision": decision, "decisionCreated": created, "index": index}

    def verify(self, repair_index: bool = True) -> dict[str, Any]:
        assets = self._active_assets()
        decisions = self.list_decisions()
        entries = self._asset_entries(assets)
        expected_ids = [item["assetId"] for item in entries]
        expected_digest = canonical_digest(entries)
        decision_digest = canonical_digest(
            [{"bundleFingerprint": item["bundleFingerprint"], "decisionDigest": item["decisionDigest"]} for item in decisions]
        )
        manifest_mismatch = any(
            (
                self.manifest.get("activeAssetCount") != len(entries),
                self.manifest.get("activeDigest") != expected_digest,
                self.manifest.get("decisionDigest") != decision_digest,
            )
        )
        try:
            with KnowledgeIndex(self.paths["index"]) as index:
                derived = index.verify()
                indexed_ids = index.asset_ids()
            if indexed_ids != expected_ids:
                raise VerifierError("knowledge_index_activation_mismatch", "derived index 与 decision 可达对象不一致", status=500)
        except (VerifierError, sqlite3.DatabaseError, OSError):
            if not repair_index:
                raise
            corrupt = self.paths["derived"] / f"index.corrupt-{uuid.uuid4()}.sqlite3"
            if self.paths["index"].exists():
                os.replace(self.paths["index"], corrupt)
            index_journal = Path(str(self.paths["index"]) + "-journal")
            if index_journal.exists():
                os.replace(index_journal, Path(str(corrupt) + "-journal"))
            derived = self.rebuild_index()
            derived["quarantined"] = corrupt.name if corrupt.exists() else None
            manifest_mismatch = False
        if manifest_mismatch:
            if not repair_index:
                raise VerifierError("knowledge_manifest_mismatch", "manifest derived metadata 不匹配", status=500)
            self._update_manifest(assets, decisions)
        active_paths = {path.name for _, path in assets}
        orphan_count = sum(1 for path in self.paths["objects"].glob("*.json") if path.name not in active_paths)
        return {
            "activeAssetCount": len(assets),
            "activeDigest": expected_digest,
            "decisionCount": len(decisions),
            "orphanObjectCount": orphan_count,
            "generation": int(self.manifest.get("generation", 0)),
            "manifestRebuilt": manifest_mismatch,
            "derived": derived,
        }
