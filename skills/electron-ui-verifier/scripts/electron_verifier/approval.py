"""Pending fingerprint 校验、sealed decision 与 canonical approval。"""

from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Any

from .atomic_io import exclusive_write_json, resolve_under
from .canonical_store import CanonicalStore
from .errors import VerifierError
from .evidence import EvidenceStore
from .knowledge_models import CanonicalAsset, normalize_parameter_schema, placeholders
from .models import MUTATING_ACTIONS, canonical_digest


def _contains_redacted_input(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_redacted_input(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_redacted_input(item) for item in value)
    return value == "[REDACTED_INPUT]"


class ApprovalService:
    def __init__(self, store: CanonicalStore, runs: Any) -> None:
        self.store = store
        self.runs = runs

    def _decision(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("decision_invalid", f"无法读取 sealed decision：{exc}", status=500) from exc
        if not isinstance(value, dict):
            raise VerifierError("decision_invalid", "sealed decision 必须是 object", status=500)
        return value

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
        if not isinstance(pending, dict) or pending.get("runId") != run_id:
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
        workflow = pending.get("workflow")
        if not isinstance(workflow, dict) or not isinstance(workflow.get("steps"), list) or not workflow["steps"]:
            issues.append({"code": "workflow_empty", "message": "pending workflow 缺少可持久化步骤"})
            workflow = {"steps": []}
        mutating = 0
        for index, action in enumerate(workflow["steps"]):
            if not isinstance(action, dict):
                issues.append({"code": "invalid_action", "step": index})
                continue
            if action.get("type") in MUTATING_ACTIONS:
                mutating += 1
                if not isinstance(action.get("postconditions"), list) or not action["postconditions"]:
                    issues.append({"code": "postcondition_required", "step": index})
            if _contains_redacted_input(action):
                issues.append({"code": "unparameterized_input", "step": index})
        if mutating == 0:
            issues.append({"code": "no_mutating_path", "message": "纯只读 run 不应批准为 executable workflow"})
        try:
            schema = normalize_parameter_schema(pending.get("parameterSchema"))
            used = placeholders(workflow)
            required = {name for name, item in schema.items() if item.get("required") is True}
            if used - set(schema):
                issues.append({"code": "undeclared_parameter", "parameters": sorted(used - set(schema))})
            if required - used:
                issues.append({"code": "unused_required_parameter", "parameters": sorted(required - used)})
        except VerifierError as exc:
            issues.append({"code": exc.code, "message": exc.message})
        for risk in pending.get("risks", []):
            if isinstance(risk, dict) and risk.get("learnable") is False and risk.get("confirmed") is not True:
                issues.append({"code": "risk_confirmation_required", "risk": risk.get("code"), "stepId": risk.get("stepId")})
        decision_path = path.parent / "decision.json"
        decision = self._decision(decision_path)
        return {
            "runId": run_id,
            "pending": str(path),
            "bundleFingerprint": fingerprint,
            "approvable": not issues and decision is None,
            "sealed": decision is not None,
            "decision": decision,
            "issues": issues,
            "workflowStepCount": len(workflow["steps"]),
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
        journal, pending, path = self._pending(run_id)
        decision_path = path.parent / "decision.json"
        if decision_path.exists():
            decision = self._decision(decision_path) or {}
            if decision.get("status") == "approved" and decision.get("bundleFingerprint") == fingerprint:
                return {"ok": True, "alreadyApproved": True, "decision": decision}
            raise VerifierError("pending_already_sealed", "pending 已由其它决定 sealed", status=409)
        if preview["issues"]:
            raise VerifierError("pending_not_approvable", "pending bundle 未通过批准完整性检查", status=409, details={"issues": preview["issues"]})
        workflow = pending["workflow"]
        report = self.runs.get_report(str(pending["report"]))["result"]
        evidence = []
        for item in pending["evidence"]:
            if item.get("artifactId"):
                evidence.append(
                    {
                        "artifactId": item["artifactId"],
                        "sha256": item["sha256"],
                        "mediaType": item.get("mediaType"),
                    }
                )
            elif item.get("reportDigest"):
                evidence.append({"reportDigest": item["reportDigest"]})
        asset = CanonicalAsset.create(
            kind="workflow",
            app_id=str(pending["appId"]),
            goal=str(workflow["goal"]),
            aliases=[str(item) for item in workflow.get("aliases", [])],
            payload={
                "workflow": workflow,
                "parameterSchema": pending.get("parameterSchema") or {},
                "risks": pending.get("risks") or [],
            },
            evidence=evidence,
            created_at=str(report.get("finalizedAt") or journal.get("updatedAt")),
        )
        persisted = self.store.persist([asset])[0]
        decision = {
            "schemaVersion": 1,
            "status": "approved",
            "runId": run_id,
            "bundleFingerprint": fingerprint,
            "assetId": asset.asset_id,
            "note": note[:1000],
        }
        if not exclusive_write_json(decision_path, decision):
            raise VerifierError("pending_already_sealed", "pending 在提交期间被其它决定 sealed", status=409)
        return {"ok": True, "alreadyApproved": False, "decision": decision, "asset": persisted}

    def reject(self, run_id: str, fingerprint: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise VerifierError("rejection_reason_required", "reject 需要非空 reason")
        preview = self.validate(run_id)
        self._confirm(preview, fingerprint)
        _, _, path = self._pending(run_id)
        decision_path = path.parent / "decision.json"
        decision = {
            "schemaVersion": 1,
            "status": "rejected",
            "runId": run_id,
            "bundleFingerprint": fingerprint,
            "reason": reason[:1000],
        }
        if not exclusive_write_json(decision_path, decision):
            existing = self._decision(decision_path) or {}
            if existing == decision:
                return {"ok": True, "alreadyRejected": True, "decision": existing}
            raise VerifierError("pending_already_sealed", "pending 已由其它决定 sealed", status=409)
        return {"ok": True, "alreadyRejected": False, "decision": decision}
