"""显式、引用安全且可审计的 verifier 状态保留清理。"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json, resolve_under, sha256_file
from .canonical_store import CanonicalStore
from .errors import VerifierError
from .knowledge_models import CanonicalAsset
from .models import canonical_digest
from .retention_policy import RetentionPolicy


FINAL_RUN_STATES = {"passed", "failed", "aborted"}
OPEN_RUN_STATES = {"prepared", "running", "finalizing"}
FINAL_OPERATION_STATES = {"succeeded", "failed", "cancelled", "deadline_exceeded", "unknown"}
OPEN_OPERATION_STATES = {"queued", "running"}
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifierError("retention_reference_invalid", f"{label} 无法读取：{path}", status=500) from exc
    if not isinstance(value, dict):
        raise VerifierError("retention_reference_invalid", f"{label} 根节点必须是 object", status=500)
    return value


def _timestamp(value: Any, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerifierError("retention_reference_invalid", f"{label} 时间无效", status=500) from exc
    if result.tzinfo is None:
        raise VerifierError("retention_reference_invalid", f"{label} 时间缺少时区", status=500)
    return result.astimezone(timezone.utc)


def _age_seconds(now: datetime, value: Any, label: str) -> int:
    return max(0, int((now - _timestamp(value, label)).total_seconds()))


class RetentionService:
    """以完整引用快照生成候选，并在每次删除前重新证明候选仍安全。"""

    def __init__(self, state_root: Path, *, now: datetime | None = None) -> None:
        self.state_root = state_root.resolve()
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.runs_dir = self.state_root / "runs"
        self.operations_dir = self.state_root / "operations"
        self.pending_dir = self.state_root / "pending"
        self.receipts_dir = self.state_root / "retention" / "applications"

    def _state_json(self, path: Path, label: str) -> dict[str, Any]:
        resolved = resolve_under(self.state_root, path, must_exist=True)
        if path.is_symlink() or resolved.is_symlink():
            raise VerifierError("retention_symlink_rejected", f"retention 不读取符号链接：{path}")
        return _read_json(resolved, label)

    def _guard_knowledge_layout(self) -> None:
        root = self.state_root / "knowledge"
        for path in (root, root / "manifest.json", root / "objects", root / "decisions"):
            resolved = resolve_under(self.state_root, path, must_exist=True)
            if path.is_symlink() or resolved.is_symlink():
                raise VerifierError("retention_symlink_rejected", f"knowledge 路径不能是符号链接：{path}")
        for path in (root / "decisions").glob("*.json"):
            resolve_under(self.state_root, path, must_exist=True)
            if path.is_symlink():
                raise VerifierError("retention_symlink_rejected", f"decision 不能是符号链接：{path}")

    def _relative(self, path: Path) -> str:
        resolved = resolve_under(self.state_root, path)
        return resolved.relative_to(self.state_root).as_posix()

    def _tree_snapshot(self, paths: list[Path]) -> tuple[int, str]:
        entries: list[dict[str, Any]] = []
        total = 0
        for target in paths:
            resolved = resolve_under(self.state_root, target, must_exist=True)
            if resolved.is_symlink():
                raise VerifierError("retention_symlink_rejected", f"retention 不处理符号链接：{resolved}")
            members = [resolved] if resolved.is_file() else sorted(resolved.rglob("*"))
            for member in members:
                if member.is_symlink():
                    raise VerifierError("retention_symlink_rejected", f"retention 不处理符号链接：{member}")
                if not member.is_file():
                    continue
                size = member.stat().st_size
                total += size
                entries.append(
                    {
                        "path": self._relative(member),
                        "bytes": size,
                        "sha256": sha256_file(member),
                    }
                )
        return total, canonical_digest(entries)

    def _candidate(
        self,
        kind: str,
        identity: str,
        paths: list[Path],
        updated_at: str,
        reasons: list[str],
    ) -> dict[str, Any]:
        existing = [path for path in paths if path.exists()]
        total, digest = self._tree_snapshot(existing)
        return {
            "key": f"{kind}:{identity}",
            "kind": kind,
            "id": identity,
            "paths": [self._relative(path) for path in existing],
            "updatedAt": updated_at,
            "reasons": sorted(set(reasons)),
            "bytes": total,
            "contentDigest": digest,
        }

    def _pending_graph(self, decisions: dict[str, dict[str, Any]]) -> tuple[set[str], set[str]]:
        unsealed_runs: set[str] = set()
        asset_ids: set[str] = set()
        if not self.pending_dir.exists():
            return unsealed_runs, asset_ids
        for path in sorted(self.pending_dir.glob("*/pending.json")):
            value = self._state_json(path, "pending")
            run_id = str(value.get("runId") or "")
            fingerprint = str(value.get("bundleFingerprint") or "")
            try:
                normalized_run = str(uuid.UUID(run_id))
            except ValueError as exc:
                raise VerifierError("retention_reference_invalid", "pending runId 无效", status=500) from exc
            if path.parent.name != normalized_run or not FINGERPRINT.fullmatch(fingerprint):
                raise VerifierError("retention_reference_invalid", "pending identity 无效", status=500)
            proposals = value.get("proposals")
            if not isinstance(proposals, list):
                raise VerifierError("retention_reference_invalid", "pending proposals 无效", status=500)
            for proposal in proposals:
                if not isinstance(proposal, dict) or not isinstance(proposal.get("assetId"), str):
                    raise VerifierError("retention_reference_invalid", "pending proposal assetId 无效", status=500)
                asset_ids.add(str(proposal["assetId"]))
            if fingerprint not in decisions:
                unsealed_runs.add(normalized_run)
        return unsealed_runs, asset_ids

    def _operations(
        self,
        policy: RetentionPolicy,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, set[str]]]:
        candidates: list[dict[str, Any]] = []
        protected: list[dict[str, Any]] = []
        run_refs: dict[str, set[str]] = {}
        if not self.operations_dir.exists():
            return candidates, protected, run_refs
        for path in sorted(self.operations_dir.glob("*.json")):
            value = self._state_json(path, "operation")
            operation_id = str(value.get("operationId") or "")
            run_id = str(value.get("runId") or "")
            try:
                operation_id = str(uuid.UUID(operation_id))
                run_id = str(uuid.UUID(run_id))
            except ValueError as exc:
                raise VerifierError("retention_reference_invalid", "operation identity 无效", status=500) from exc
            if path.stem != operation_id:
                raise VerifierError("retention_reference_invalid", "operation 文件名与 identity 不一致", status=500)
            state = str(value.get("state") or "")
            if state not in FINAL_OPERATION_STATES | OPEN_OPERATION_STATES:
                raise VerifierError("retention_reference_invalid", f"operation state 无效：{state}", status=500)
            run_refs.setdefault(run_id, set()).add(operation_id)
            request_id = str(value.get("requestId") or "")
            try:
                request_id = str(uuid.UUID(request_id))
            except ValueError as exc:
                raise VerifierError("retention_reference_invalid", "operation requestId 无效", status=500) from exc
            request_name = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
            request_path = self.operations_dir / "requests" / request_name
            paths = [path]
            if request_path.exists():
                request = self._state_json(request_path, "operation request index")
                if request.get("operationId") != operation_id or request.get("requestId") != request_id:
                    raise VerifierError("retention_reference_invalid", "operation request index 引用不一致", status=500)
                paths.append(request_path)
            updated_at = str(value.get("finishedAt") or value.get("updatedAt") or "")
            age = _age_seconds(self.now, updated_at, "operation.updatedAt")
            if state in OPEN_OPERATION_STATES:
                protected.append({"kind": "operation", "id": operation_id, "reasons": ["nonterminal"]})
            elif age < policy.operation_expiration_seconds:
                protected.append({"kind": "operation", "id": operation_id, "reasons": ["within_operation_expiration"]})
            else:
                candidates.append(self._candidate("operation", operation_id, paths, updated_at, ["operation_expired"]))
        return candidates, protected, run_refs

    def _runs(
        self,
        policy: RetentionPolicy,
        approved_runs: set[str],
        unsealed_pending_runs: set[str],
        operation_refs: dict[str, set[str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        eligible: list[dict[str, Any]] = []
        age_by_key: dict[str, int] = {}
        protected: list[dict[str, Any]] = []
        managed_bytes = 0
        if not self.runs_dir.exists():
            return eligible, protected, managed_bytes
        for run_dir in sorted(path for path in self.runs_dir.iterdir() if path.is_dir()):
            if run_dir.is_symlink():
                raise VerifierError("retention_symlink_rejected", f"run 目录不能是符号链接：{run_dir}")
            journal = self._state_json(run_dir / "journal.json", "run journal")
            run_id = str(journal.get("runId") or "")
            try:
                run_id = str(uuid.UUID(run_id))
            except ValueError as exc:
                raise VerifierError("retention_reference_invalid", "runId 无效", status=500) from exc
            if run_dir.name != run_id:
                raise VerifierError("retention_reference_invalid", "run 目录与 identity 不一致", status=500)
            state = str(journal.get("state") or "")
            if state not in FINAL_RUN_STATES | OPEN_RUN_STATES:
                raise VerifierError("retention_reference_invalid", f"run state 无效：{state}", status=500)
            updated_at = str(journal.get("updatedAt") or journal.get("createdAt") or "")
            paths = [run_dir]
            pending_path = self.pending_dir / run_id
            if pending_path.exists():
                paths.append(pending_path)
            item = self._candidate("run", run_id, paths, updated_at, [])
            managed_bytes += int(item["bytes"])
            reasons = []
            if state in OPEN_RUN_STATES:
                reasons.append("nonterminal")
            if run_id in approved_runs:
                reasons.append("approved_decision_evidence")
            if run_id in unsealed_pending_runs:
                reasons.append("unsealed_pending")
            if operation_refs.get(run_id):
                reasons.append("operation_reference")
            if reasons:
                protected.append(
                    {"kind": "run", "id": run_id, "reasons": sorted(reasons), "bytes": item["bytes"]}
                )
            else:
                age_by_key[item["key"]] = _age_seconds(self.now, updated_at, "run.updatedAt")
                eligible.append(item)
        newest = sorted(eligible, key=lambda item: (item["updatedAt"], item["id"]), reverse=True)
        reasons_by_key: dict[str, set[str]] = {item["key"]: set() for item in eligible}
        for index, item in enumerate(newest):
            if age_by_key[item["key"]] >= policy.terminal_age_seconds:
                reasons_by_key[item["key"]].add("terminal_age")
            if index >= policy.max_runs:
                reasons_by_key[item["key"]].add("max_runs")
        selected_bytes = sum(item["bytes"] for item in eligible if reasons_by_key[item["key"]])
        projected = max(0, managed_bytes - selected_bytes)
        for item in sorted(eligible, key=lambda value: (value["updatedAt"], value["id"])):
            if projected <= policy.max_total_bytes:
                break
            if not reasons_by_key[item["key"]]:
                reasons_by_key[item["key"]].add("max_total_bytes")
                projected = max(0, projected - int(item["bytes"]))
        candidates = []
        for item in eligible:
            reasons = sorted(reasons_by_key[item["key"]])
            if reasons:
                item["reasons"] = reasons
                candidates.append(item)
            else:
                protected.append(
                    {"kind": "run", "id": item["id"], "reasons": ["within_policy"], "bytes": item["bytes"]}
                )
        return candidates, protected, managed_bytes

    def _objects(
        self,
        policy: RetentionPolicy,
        store: CanonicalStore,
        decision_assets: set[str],
        pending_assets: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        assets: dict[str, tuple[CanonicalAsset, Path]] = {}
        object_refs: set[str] = set()
        for path in sorted(store.paths["objects"].glob("*.json")):
            asset = CanonicalAsset.decode(self._state_json(path, "knowledge object"))
            if path.name != f"{asset.asset_id}.json":
                raise VerifierError("retention_reference_invalid", "knowledge object identity 无效", status=500)
            assets[asset.asset_id] = (asset, path)
            if asset.kind == "workflow":
                object_refs.update(asset.payload["actionIds"])
        candidates = []
        protected = []
        for asset_id, (asset, path) in assets.items():
            reasons = []
            if asset_id in decision_assets:
                reasons.append("sealed_decision_reference")
            if asset_id in pending_assets:
                reasons.append("pending_reference")
            if asset_id in object_refs:
                reasons.append("object_reference")
            age = _age_seconds(self.now, asset.created_at, "asset.createdAt")
            if reasons:
                protected.append({"kind": "orphanObject", "id": asset_id, "reasons": sorted(reasons)})
            elif not policy.include_orphans:
                protected.append({"kind": "orphanObject", "id": asset_id, "reasons": ["orphans_not_requested"]})
            elif age < policy.orphan_grace_seconds:
                protected.append({"kind": "orphanObject", "id": asset_id, "reasons": ["orphan_grace"]})
            else:
                candidates.append(
                    self._candidate("orphanObject", asset_id, [path], asset.created_at, ["unreferenced_orphan"])
                )
        return candidates, protected

    def preview(self, policy: RetentionPolicy) -> dict[str, Any]:
        self._guard_knowledge_layout()
        store = CanonicalStore(self.state_root)
        decisions_list = store.list_decisions()
        decisions = {str(item["bundleFingerprint"]): item for item in decisions_list}
        approved_runs = {str(item["runId"]) for item in decisions_list if item["status"] == "approved"}
        decision_assets = {str(asset_id) for item in decisions_list for asset_id in item["assetIds"]}
        unsealed_pending, pending_assets = self._pending_graph(decisions)
        operation_candidates, operation_protected, operation_refs = self._operations(policy)
        run_candidates, run_protected, managed_bytes = self._runs(
            policy,
            approved_runs,
            unsealed_pending,
            operation_refs,
        )
        object_candidates, object_protected = self._objects(policy, store, decision_assets, pending_assets)
        order = {"operation": 0, "run": 1, "orphanObject": 2}
        candidates = sorted(
            [*operation_candidates, *run_candidates, *object_candidates],
            key=lambda item: (order[item["kind"]], item["updatedAt"], item["id"]),
        )
        protected = sorted(
            [*operation_protected, *run_protected, *object_protected],
            key=lambda item: (str(item["kind"]), str(item["id"])),
        )
        fingerprint = canonical_digest({"schemaVersion": 1, "policy": policy.to_dict(), "candidates": candidates})
        return {
            "ok": True,
            "mode": "preview",
            "schemaVersion": 1,
            "policy": policy.to_dict(),
            "fingerprint": fingerprint,
            "candidateCount": len(candidates),
            "estimatedBytes": sum(int(item["bytes"]) for item in candidates),
            "managedRunBytes": managed_bytes,
            "candidates": candidates,
            "protected": protected,
        }

    def _assert_target(self, candidate: dict[str, Any], relative: str) -> Path:
        path = resolve_under(self.state_root, self.state_root / relative)
        kind = candidate["kind"]
        identity = candidate["id"]
        allowed = {
            "run": {f"runs/{identity}", f"pending/{identity}"},
            "operation": {f"operations/{identity}.json"},
            "orphanObject": {f"knowledge/objects/{identity}.json"},
        }[kind]
        if kind == "operation" and re.fullmatch(r"operations/requests/[0-9a-f]{64}\.json", relative):
            allowed.add(relative)
        if relative not in allowed:
            raise VerifierError("retention_path_invalid", f"candidate 路径不属于允许删除集合：{relative}")
        if path.exists() and path.is_symlink():
            raise VerifierError("retention_symlink_rejected", f"retention 不处理符号链接：{path}")
        return path

    def _remove_candidate(self, candidate: dict[str, Any]) -> list[str]:
        removed = []
        for relative in candidate["paths"]:
            path = self._assert_target(candidate, relative)
            if not path.exists():
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError as exc:
                raise VerifierError(
                    "retention_delete_failed",
                    f"删除失败：{relative}: {exc}",
                    status=500,
                    details={"removedPaths": removed, "failedPath": relative},
                ) from exc
            removed.append(relative)
        return removed

    def apply(self, policy: RetentionPolicy, fingerprint: str, *, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise VerifierError("retention_confirmation_required", "apply 需要显式 --confirm")
        if not FINGERPRINT.fullmatch(str(fingerprint or "")):
            raise VerifierError("retention_fingerprint_invalid", "retention fingerprint 必须是 SHA-256")
        receipt_path = self.receipts_dir / f"{fingerprint}.json"
        resolve_under(self.state_root, receipt_path)
        if receipt_path.exists():
            receipt = self._state_json(receipt_path, "retention apply receipt")
            if receipt.get("fingerprint") != fingerprint or receipt.get("policy") != policy.to_dict():
                raise VerifierError("retention_receipt_invalid", "retention apply receipt identity 不匹配", status=500)
            if isinstance(receipt.get("result"), dict):
                result = dict(receipt["result"])
                result["alreadyApplied"] = True
                return result
            preview = receipt.get("preview")
            if not isinstance(preview, dict) or preview.get("fingerprint") != fingerprint:
                raise VerifierError("retention_receipt_invalid", "未完成 receipt 缺少原始 preview", status=500)
        else:
            preview = self.preview(policy)
            if not hmac.compare_digest(preview["fingerprint"], fingerprint):
                raise VerifierError(
                    "retention_fingerprint_stale",
                    "retention 候选已变化，请重新 preview",
                    status=409,
                    details={"expectedFingerprint": preview["fingerprint"]},
                )
            receipt = {
                "schemaVersion": 1,
                "fingerprint": fingerprint,
                "policy": policy.to_dict(),
                "status": "applying",
                "preview": preview,
                "results": [],
            }
            atomic_write_json(receipt_path, receipt)
        processed = {str(item.get("key")) for item in receipt["results"] if isinstance(item, dict)}
        for candidate in preview["candidates"]:
            if candidate["key"] in processed:
                continue
            fresh = self.preview(policy)
            current = next((item for item in fresh["candidates"] if item["key"] == candidate["key"]), None)
            if current is None:
                receipt["results"].append(
                    {"key": candidate["key"], "status": "skipped", "reason": "no_longer_candidate"}
                )
                atomic_write_json(receipt_path, receipt)
                continue
            if current["contentDigest"] != candidate["contentDigest"] or current["paths"] != candidate["paths"]:
                receipt["results"].append(
                    {"key": candidate["key"], "status": "failed", "code": "candidate_changed"}
                )
                break
            try:
                removed = self._remove_candidate(candidate)
                receipt["results"].append(
                    {"key": candidate["key"], "status": "deleted", "removedPaths": removed, "bytes": candidate["bytes"]}
                )
            except VerifierError as exc:
                receipt["results"].append(
                    {
                        "key": candidate["key"],
                        "status": "failed",
                        "code": exc.code,
                        "error": exc.message,
                        "details": exc.details,
                    }
                )
                atomic_write_json(receipt_path, receipt)
                break
            atomic_write_json(receipt_path, receipt)
        failures = [item for item in receipt["results"] if item["status"] == "failed"]
        deleted = [item for item in receipt["results"] if item["status"] == "deleted"]
        result = {
            "ok": not failures,
            "mode": "apply",
            "fingerprint": fingerprint,
            "alreadyApplied": False,
            "deletedCount": len(deleted),
            "releasedBytes": sum(int(item.get("bytes") or 0) for item in deleted),
            "results": receipt["results"],
            "failures": failures,
        }
        receipt["status"] = "completed" if not failures else "failed"
        receipt["result"] = result
        atomic_write_json(receipt_path, receipt)
        return result
