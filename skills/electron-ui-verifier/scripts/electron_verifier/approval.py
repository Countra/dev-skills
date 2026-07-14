"""Pending fingerprint 校验、sealed decision 与 canonical approval。"""

from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Any, Callable

from . import SCHEMA_VERSION
from .atomic_io import resolve_under
from .canonical_store import CanonicalStore
from .errors import VerifierError
from .evidence import EvidenceStore
from .knowledge_models import CanonicalAsset
from .models import MUTATING_ACTIONS, canonical_digest
from .reports import build_pending


PENDING_FIELDS = {
    "schemaVersion",
    "pendingId",
    "runId",
    "status",
    "appId",
    "appVersion",
    "screenDigest",
    "preState",
    "proposals",
    "actionAssetIds",
    "workflowAssetId",
    "evidence",
    "risks",
    "report",
    "reportDigest",
    "bundleFingerprint",
}


def _contains_redacted_input(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_redacted_input(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_redacted_input(item) for item in value)
    return value == "[REDACTED_INPUT]"


class ApprovalService:
    def __init__(
        self,
        store: CanonicalStore,
        runs: Any,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self.runs = runs
        self.fault_injector = fault_injector

    def _pending(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
        journal = self.runs.load(run_id)
        pending_value = journal.get("pending")
        if not isinstance(pending_value, str) or not pending_value:
            raise VerifierError("pending_not_found", f"run 没有可批准 pending：{run_id}", status=404)
        path = resolve_under(self.runs.config.pending_dir, Path(pending_value), must_exist=True)
        if path.name != "pending.json":
            raise VerifierError("pending_invalid", "pending path 必须指向 pending.json", status=500)
        try:
            pending = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("pending_invalid", f"无法读取 pending bundle：{exc}", status=500) from exc
        if (
            not isinstance(pending, dict)
            or set(pending) != PENDING_FIELDS
            or pending.get("schemaVersion") != SCHEMA_VERSION
            or pending.get("status") != "pending"
            or pending.get("pendingId") != run_id
            or pending.get("runId") != run_id
        ):
            raise VerifierError("pending_invalid", "pending/run identity 不匹配", status=500)
        return journal, pending, path

    def _fingerprint(self, pending: dict[str, Any]) -> str:
        payload = dict(pending)
        supplied = str(payload.pop("bundleFingerprint", ""))
        expected = canonical_digest(payload)
        if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            raise VerifierError(
                "pending_fingerprint_invalid",
                "pending bundleFingerprint 与当前内容不匹配",
                status=409,
                details={"expectedFingerprint": expected},
            )
        return expected

    def _proposal_assets(self, pending: dict[str, Any]) -> tuple[list[CanonicalAsset], CanonicalAsset]:
        proposals = pending.get("proposals")
        if not isinstance(proposals, list) or len(proposals) < 2:
            raise VerifierError("pending_proposals_invalid", "pending 至少需要 action 与 workflow proposals")
        assets = [CanonicalAsset.decode(item) for item in proposals]
        by_id = {asset.asset_id: asset for asset in assets}
        if len(by_id) != len(assets):
            raise VerifierError("pending_proposals_invalid", "pending proposals 包含重复 assetId")
        workflows = [asset for asset in assets if asset.kind == "workflow"]
        actions = [asset for asset in assets if asset.kind == "action"]
        if len(workflows) != 1 or not actions:
            raise VerifierError("pending_proposals_invalid", "pending 必须包含一个 workflow 和至少一个 action")
        workflow = workflows[0]
        ordered_ids = pending.get("actionAssetIds")
        if (
            not isinstance(ordered_ids, list)
            or workflow.asset_id != pending.get("workflowAssetId")
            or workflow.payload.get("actionIds") != ordered_ids
            or set(ordered_ids) != {asset.asset_id for asset in actions}
        ):
            raise VerifierError("pending_proposals_invalid", "workflow/action proposal 引用图不一致")
        if any(asset.app_id != pending.get("appId") for asset in assets):
            raise VerifierError("pending_proposals_invalid", "proposal appId 与 pending 不一致")
        for asset in assets:
            compatibility = asset.payload["compatibility"]
            if (
                compatibility["appVersionMin"] != pending.get("appVersion")
                or compatibility["appVersionMax"] != pending.get("appVersion")
                or compatibility["screenDigest"] != pending.get("screenDigest")
            ):
                raise VerifierError("pending_proposals_invalid", "proposal compatibility 与 pending 现场不一致")
        if workflow.payload["compatibility"]["preState"] != pending.get("preState"):
            raise VerifierError("pending_proposals_invalid", "workflow preState 与 pending 现场不一致")
        transitions = workflow.payload["transitions"]
        merged_schema: dict[str, dict[str, Any]] = {}
        required_parameters: set[str] = set()
        for index, action_id in enumerate(ordered_ids):
            action = by_id[action_id]
            compatibility = action.payload["compatibility"]
            transition = transitions[index]
            if (
                transition["preState"] != compatibility["preState"]
                or transition["postState"] != compatibility["postState"]
            ):
                raise VerifierError("pending_proposals_invalid", "action compatibility 与 workflow transition 不一致")
            required_parameters.update(action.payload["requiredParameters"])
            for name, definition in action.payload["parameterSchema"].items():
                if name in merged_schema and merged_schema[name] != definition:
                    raise VerifierError("pending_proposals_invalid", f"action parameter schema 冲突：{name}")
                merged_schema[name] = definition
        if (
            workflow.payload["parameterSchema"] != merged_schema
            or workflow.payload["requiredParameters"] != sorted(required_parameters)
        ):
            raise VerifierError("pending_proposals_invalid", "workflow 参数契约与 action graph 不一致")
        return assets, workflow

    def validate(self, run_id: str) -> dict[str, Any]:
        journal, pending, path = self._pending(run_id)
        fingerprint = self._fingerprint(pending)
        issues: list[dict[str, Any]] = []
        report_path = Path(str(pending.get("report") or ""))
        try:
            report_result = self.runs.get_report(str(report_path))
            report = report_result["result"]
        except VerifierError as exc:
            report = {}
            issues.append({"code": exc.code, "message": exc.message})
        if report.get("status") != "passed" or journal.get("state") != "passed":
            issues.append({"code": "run_not_passed", "message": "run/report 必须通过后才能批准"})
        if report and pending.get("reportDigest") != canonical_digest(report):
            issues.append({"code": "report_digest_mismatch", "message": "pending reportDigest 已失效"})
        if report:
            expected_pending = build_pending(journal, report, str(pending.get("report") or ""))
            if expected_pending != pending:
                issues.append(
                    {
                        "code": "proposal_derivation_mismatch",
                        "message": "pending 必须与已验证 run 确定性派生的 proposal 完全一致",
                    }
                )
        try:
            artifacts = EvidenceStore(self.runs.run_dir(run_id)).verify()
        except VerifierError as exc:
            artifacts = []
            issues.append({"code": exc.code, "message": exc.message})
        expected_evidence = {
            item["artifactId"]: item["sha256"]
            for item in artifacts
        }
        pending_evidence = {
            str(item.get("artifactId")): str(item.get("sha256"))
            for item in pending.get("evidence", [])
            if isinstance(item, dict) and item.get("artifactId")
        }
        if expected_evidence != pending_evidence:
            issues.append({"code": "evidence_mismatch", "message": "pending evidence 与已提交 manifest 不一致"})
        assets: list[CanonicalAsset] = []
        try:
            assets, workflow = self._proposal_assets(pending)
            expected_asset_evidence = [
                {
                    "artifactId": item["artifactId"],
                    "sha256": item["sha256"],
                    "mediaType": item.get("mediaType"),
                }
                for item in artifacts
            ]
            expected_asset_evidence.append({"reportDigest": pending.get("reportDigest")})
            if any(list(asset.evidence) != expected_asset_evidence for asset in assets):
                issues.append({"code": "proposal_evidence_mismatch", "message": "proposal evidence 与 run 证据不一致"})
            action_assets = {asset.asset_id: asset for asset in assets if asset.kind == "action"}
            mutating = 0
            for index, action_id in enumerate(workflow.payload["actionIds"]):
                action = action_assets[action_id].payload["action"]
                if action.get("type") in MUTATING_ACTIONS:
                    mutating += 1
                if _contains_redacted_input(action):
                    issues.append({"code": "unparameterized_input", "step": index})
            if mutating == 0:
                issues.append({"code": "no_mutating_path", "message": "纯只读 run 不应批准为 executable workflow"})
        except VerifierError as exc:
            issues.append({"code": exc.code, "message": exc.message})
        for risk in pending.get("risks", []):
            if isinstance(risk, dict) and risk.get("learnable") is False and risk.get("confirmed") is not True:
                issues.append({"code": "risk_confirmation_required", "risk": risk.get("code"), "stepId": risk.get("stepId")})
        decision = self.store.get_decision(fingerprint)
        return {
            "runId": run_id,
            "pending": str(path),
            "bundleFingerprint": fingerprint,
            "approvable": not issues and decision is None,
            "sealed": decision is not None,
            "decision": decision,
            "issues": issues,
            "workflowStepCount": len(pending.get("actionAssetIds") or []),
            "proposalCount": len(assets),
            "artifactCount": len(artifacts),
        }

    def _confirm(self, preview: dict[str, Any], supplied: str) -> None:
        expected = str(preview["bundleFingerprint"])
        if not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
            raise VerifierError("approval_fingerprint_mismatch", "批准 fingerprint 与当前 pending 不一致", status=409)

    def approve(self, run_id: str, fingerprint: str, note: str) -> dict[str, Any]:
        if not note.strip():
            raise VerifierError("approval_note_required", "approve 需要非空 note")
        preview = self.validate(run_id)
        self._confirm(preview, fingerprint)
        _, pending, _ = self._pending(run_id)
        decision = preview.get("decision")
        if isinstance(decision, dict):
            if decision.get("status") == "approved" and decision.get("bundleFingerprint") == fingerprint:
                rebuilt = self.store.rebuild_index()
                persisted = [self.store.get_asset(str(asset_id)).to_dict() for asset_id in decision["assetIds"]]
                workflow = next(asset for asset in persisted if asset["kind"] == "workflow")
                actions = [asset for asset in persisted if asset["kind"] == "action"]
                return {
                    "ok": True,
                    "alreadyApproved": True,
                    "decision": decision,
                    "assets": persisted,
                    "actionAssets": actions,
                    "workflowAsset": workflow,
                    "index": rebuilt,
                }
            raise VerifierError("pending_already_sealed", "pending 已由其它决定 sealed", status=409)
        if preview["issues"]:
            raise VerifierError("pending_not_approvable", "pending bundle 未通过批准完整性检查", status=409, details={"issues": preview["issues"]})
        assets, _ = self._proposal_assets(pending)
        activation = self.store.activate(
            assets,
            bundle_fingerprint=fingerprint,
            run_id=run_id,
            message=note,
            fault_injector=self.fault_injector,
        )
        persisted = activation["assets"]
        return {
            "ok": True,
            "alreadyApproved": not activation["decisionCreated"],
            "decision": activation["decision"],
            "assets": persisted,
            "actionAssets": [asset for asset in persisted if asset["kind"] == "action"],
            "workflowAsset": next(asset for asset in persisted if asset["kind"] == "workflow"),
            "index": activation["index"],
        }

    def reject(self, run_id: str, fingerprint: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise VerifierError("rejection_reason_required", "reject 需要非空 reason")
        preview = self.validate(run_id)
        self._confirm(preview, fingerprint)
        try:
            decision, created = self.store.seal_decision(
                status="rejected",
                bundle_fingerprint=fingerprint,
                run_id=run_id,
                asset_ids=[],
                message=reason,
            )
        except VerifierError as exc:
            if exc.code == "decision_conflict":
                raise VerifierError("pending_already_sealed", "pending 已由其它决定 sealed", status=409) from exc
            raise
        return {"ok": True, "alreadyRejected": not created, "decision": decision}
