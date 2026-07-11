"""Prepare/append/finalize run journal 与 crash recovery。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions import DIAGNOSTIC_ACTIONS, execute_action
from .atomic_io import atomic_write_json, atomic_write_text, resolve_under
from .config import ServiceConfig
from .errors import VerifierError
from .evidence import EvidenceStore
from .knowledge_models import bind_parameters, normalize_parameter_schema, placeholder_name
from .models import ActionSpec, RunState, monotonic_ms
from .reports import build_pending, build_report, summary_markdown
from .security import redact
from .sessions import SessionManager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_action(raw_action: Any) -> Any:
    value = redact(raw_action)
    if not isinstance(value, dict):
        return value
    if value.get("type") == "fill" and "value" in value:
        text = value.get("value")
        if placeholder_name(text) is None:
            value["value"] = "[REDACTED_INPUT]"
            value["inputCharacters"] = len(text) if isinstance(text, str) else None
    postconditions = value.get("postconditions")
    if isinstance(postconditions, list):
        for assertion in postconditions:
            if isinstance(assertion, dict) and assertion.get("type") == "value" and "expected" in assertion:
                if placeholder_name(assertion.get("expected")) is None:
                    assertion["expected"] = "[REDACTED_INPUT]"
    return value


class RunService:
    def __init__(self, config: ServiceConfig, sessions: SessionManager) -> None:
        self.config = config
        self.sessions = sessions

    def _run_dir(self, run_id: str) -> Path:
        try:
            normalized = str(uuid.UUID(run_id))
        except ValueError as exc:
            raise VerifierError("invalid_run_id", f"runId 不是 UUID：{run_id}") from exc
        return self.config.runs_dir / normalized

    def run_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id)

    def _journal_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "journal.json"

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._journal_path(run_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VerifierError("run_not_found", f"run 不存在：{run_id}", status=404) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("run_journal_invalid", f"无法读取 run journal：{exc}", status=500) from exc
        if not isinstance(value, dict) or value.get("runId") != run_id:
            raise VerifierError("run_journal_invalid", "run journal identity 不匹配", status=500)
        return value

    def _save(self, journal: dict[str, Any]) -> None:
        journal["updatedAt"] = _now()
        atomic_write_json(self._journal_path(journal["runId"]), journal)

    async def recover(self) -> dict[str, Any]:
        recovered = []
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)
        for path in self.config.runs_dir.glob("*/journal.json"):
            try:
                journal = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if journal.get("state") not in {RunState.PREPARED.value, RunState.RUNNING.value, RunState.FINALIZING.value}:
                continue
            inflight = [step for step in journal.get("steps", []) if step.get("status") == "running"]
            if inflight:
                for step in inflight:
                    step["status"] = "unknown"
                    step["error"] = {"code": "service_interrupted", "outcome": "unknown"}
                    step["finishedAt"] = _now()
                journal["state"] = RunState.ABORTED.value
                journal["recovery"] = "inflight_step_aborted"
                self._save(journal)
                recovered.append(journal["runId"])
        return {"recovered": recovered}

    async def abort_open(self) -> None:
        for path in self.config.runs_dir.glob("*/journal.json"):
            try:
                journal = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if journal.get("state") in {RunState.PREPARED.value, RunState.RUNNING.value}:
                journal["state"] = RunState.ABORTED.value
                journal["abortReason"] = "service_shutdown"
                self._save(journal)

    async def prepare(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_name = str(payload.get("session") or payload.get("name") or "").strip()
        if not session_name:
            raise VerifierError("session_name_required", "prepare 需要 session name")
        if payload.get("cdp"):
            attach_payload = {
                key: payload[key]
                for key in (
                    "cdp",
                    "targetType",
                    "targetUrlContains",
                    "targetTitleContains",
                    "targetIndex",
                    "targetId",
                    "appId",
                )
                if payload.get(key) not in (None, "")
            }
            attach_payload["name"] = session_name
            attach_payload["reuse"] = payload.get("reuse", True)
            session_result = await self.sessions.attach(attach_payload)
        else:
            session_result = await self.sessions.status(session_name)
            if session_result.get("connected") is not True:
                raise VerifierError("stale_session", f"session 不可用：{session_name}", status=409)
        session = session_result["session"]
        run_id = str(uuid.uuid4())
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=False)
        now = _now()
        journal = {
            "schemaVersion": 1,
            "runId": run_id,
            "sessionId": session["sessionId"],
            "sessionName": session["name"],
            "appId": str(payload.get("appId")) if payload.get("appId") else None,
            "goal": str(payload.get("goal"))[:500] if payload.get("goal") else None,
            "parameterSchema": normalize_parameter_schema(payload.get("parameterSchema")),
            "state": RunState.PREPARED.value,
            "createdAt": now,
            "updatedAt": now,
            "steps": [],
            "artifacts": [],
        }
        EvidenceStore(run_dir).initialize(run_id)
        self._save(journal)
        return {
            "ok": True,
            "runId": run_id,
            "state": journal["state"],
            "session": {
                "sessionId": session["sessionId"],
                "name": session["name"],
                "status": session["status"],
                "targetTitle": session.get("targetTitle"),
            },
            "journal": str(self._journal_path(run_id)),
        }

    async def append_action(
        self,
        run_id: str,
        raw_action: Any,
        bindings: Any = None,
        parameter_schema: Any = None,
    ) -> dict[str, Any]:
        journal = self.load(run_id)
        if journal.get("state") not in {RunState.PREPARED.value, RunState.RUNNING.value}:
            raise VerifierError("run_not_appendable", f"run 当前状态不可追加：{journal.get('state')}", status=409)
        asset_schema = normalize_parameter_schema(parameter_schema)
        current_schema = normalize_parameter_schema(journal.get("parameterSchema"))
        if asset_schema and current_schema and asset_schema != current_schema:
            raise VerifierError("parameter_schema_conflict", "action asset 与 prepared run 的 parameterSchema 不一致", status=409)
        if asset_schema and not current_schema:
            if journal.get("steps"):
                raise VerifierError("parameter_schema_late_binding", "已有步骤后不能再修改 parameterSchema", status=409)
            journal["parameterSchema"] = asset_schema
            self._save(journal)
        session_status = await self.sessions.status(journal["sessionId"])
        if session_status.get("connected") is not True:
            raise VerifierError("stale_session", "run 对应 session 已失效", status=409)
        intent = self.sessions.intent(journal["sessionId"])
        live = self.sessions.driver.live(intent.session_id)
        if live is None:
            raise VerifierError("stale_session", "run 缺少 live Playwright handle", status=409)
        bound_action, bound_names = bind_parameters(raw_action, bindings, journal.get("parameterSchema") or {})
        action = ActionSpec.decode(bound_action)
        step_id = str(uuid.uuid4())
        label = str(raw_action.get("id") or step_id) if isinstance(raw_action, dict) else step_id
        step = {
            "stepId": step_id,
            "label": label[:200],
            "status": "running",
            "optional": bool(isinstance(raw_action, dict) and raw_action.get("continueOnFailure") is True),
            "detour": bool(isinstance(raw_action, dict) and raw_action.get("detour") is True),
            "action": _safe_action(raw_action),
            "boundParameters": sorted(bound_names),
            "startedAt": _now(),
        }
        journal["state"] = RunState.RUNNING.value
        journal["steps"].append(step)
        self._save(journal)
        started_ms = monotonic_ms()
        try:
            execution = await execute_action(live, action)
            committed = []
            evidence = EvidenceStore(self._run_dir(run_id))
            for artifact in execution.artifacts:
                committed.append(evidence.commit(artifact, step_id))
            step.update(
                {
                    "status": "passed",
                    "result": execution.result,
                    "risks": execution.risks,
                    "artifacts": [item["artifactId"] for item in committed],
                }
            )
        except VerifierError as exc:
            unknown = exc.code in {"action_outcome_unknown", "operation_timeout"} or exc.details.get("outcome") == "unknown"
            step["status"] = "unknown" if unknown else "failed"
            step["error"] = exc.envelope()
            if unknown:
                journal["state"] = RunState.ABORTED.value
        except Exception as exc:
            step["status"] = "unknown" if action.action_type in {"click", "doubleClick", "fill", "select", "check", "uncheck", "press", "keyChord"} else "failed"
            step["error"] = {"ok": False, "code": "internal_action_error", "error": type(exc).__name__}
            if step["status"] == "unknown":
                journal["state"] = RunState.ABORTED.value
        step["durationMs"] = max(0, monotonic_ms() - started_ms)
        step["finishedAt"] = _now()
        self._save(journal)
        return {
            "ok": step["status"] == "passed",
            "runId": run_id,
            "state": journal["state"],
            "step": step,
            "report": None,
            "pending": None,
        }

    async def execute_workflow(
        self,
        run_id: str,
        workflow: Any,
        auto_finalize: bool = True,
        bindings: Any = None,
    ) -> dict[str, Any]:
        if not isinstance(workflow, dict) or not isinstance(workflow.get("steps"), list):
            raise VerifierError("invalid_workflow", "workflow.steps 必须是数组")
        if not workflow["steps"] or len(workflow["steps"]) > 200:
            raise VerifierError("invalid_workflow", "workflow.steps 数量必须在 1..200")
        journal = self.load(run_id)
        workflow_schema = normalize_parameter_schema(workflow.get("parameterSchema"))
        current_schema = normalize_parameter_schema(journal.get("parameterSchema"))
        if workflow_schema and current_schema and workflow_schema != current_schema:
            raise VerifierError("parameter_schema_conflict", "workflow 与 prepared run 的 parameterSchema 不一致", status=409)
        if workflow_schema and not current_schema:
            if journal.get("steps"):
                raise VerifierError("parameter_schema_late_binding", "已有步骤后不能再修改 parameterSchema", status=409)
            journal["parameterSchema"] = workflow_schema
        workflow_app = str(workflow.get("appId") or "").strip()
        journal_app = str(journal.get("appId") or "").strip()
        if workflow_app and journal_app and workflow_app != journal_app:
            raise VerifierError("workflow_app_mismatch", "workflow appId 与 prepared run 不一致", status=409)
        journal["workflow"] = {
            "goal": workflow.get("goal"),
            "expectedSteps": len(workflow["steps"]),
        }
        self._save(journal)
        results = []
        for raw_action in workflow["steps"]:
            result = await self.append_action(run_id, raw_action, bindings)
            results.append(result["step"])
            if not result["ok"]:
                action_type = raw_action.get("type") if isinstance(raw_action, dict) else None
                may_continue = raw_action.get("continueOnFailure") is True and action_type in DIAGNOSTIC_ACTIONS
                if not may_continue:
                    break
        if auto_finalize:
            return await self.finalize(run_id)
        return {"ok": all(step["status"] == "passed" for step in results), "runId": run_id, "steps": results}

    async def finalize(self, run_id: str) -> dict[str, Any]:
        journal = self.load(run_id)
        run_dir = self._run_dir(run_id)
        report_path = run_dir / "report.json"
        summary_path = run_dir / "summary.md"
        if report_path.exists() and journal.get("state") in {RunState.PASSED.value, RunState.FAILED.value, RunState.ABORTED.value}:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return self._finalize_result(journal, report, report_path, summary_path)
        for step in journal.get("steps", []):
            if step.get("status") == "running":
                step["status"] = "unknown"
                step["error"] = {"code": "finalized_inflight_step", "outcome": "unknown"}
                journal["state"] = RunState.ABORTED.value
        if journal.get("state") not in {RunState.ABORTED.value, RunState.FINALIZING.value}:
            journal["state"] = RunState.FINALIZING.value
        self._save(journal)
        artifacts = EvidenceStore(run_dir).verify()
        report = build_report(journal, artifacts)
        atomic_write_json(report_path, report)
        pending = build_pending(journal, report, str(report_path))
        pending_path = None
        if pending is not None:
            pending_path = self.config.pending_dir / run_id / "pending.json"
            if pending_path.exists():
                existing = json.loads(pending_path.read_text(encoding="utf-8"))
                if existing.get("bundleFingerprint") != pending.get("bundleFingerprint"):
                    raise VerifierError("pending_fingerprint_conflict", "已存在不同 fingerprint 的 pending bundle", status=409)
            else:
                atomic_write_json(pending_path, pending)
        atomic_write_text(summary_path, summary_markdown(report, str(pending_path) if pending_path else None))
        journal["report"] = str(report_path)
        journal["pending"] = str(pending_path) if pending_path else None
        if journal.get("state") != RunState.ABORTED.value:
            journal["state"] = RunState.PASSED.value if report["status"] == "passed" else RunState.FAILED.value
        self._save(journal)
        return self._finalize_result(journal, report, report_path, summary_path)

    def _finalize_result(
        self,
        journal: dict[str, Any],
        report: dict[str, Any],
        report_path: Path,
        summary_path: Path,
    ) -> dict[str, Any]:
        return {
            "ok": report.get("status") == "passed",
            "runId": journal["runId"],
            "state": journal["state"],
            "report": str(report_path),
            "summary": str(summary_path),
            "pending": journal.get("pending"),
            "result": report,
        }

    def latest_report(self, session: str) -> dict[str, Any]:
        candidates = []
        for path in self.config.runs_dir.glob("*/journal.json"):
            try:
                journal = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if session not in {journal.get("sessionId"), journal.get("sessionName")} or not journal.get("report"):
                continue
            candidates.append(journal)
        if not candidates:
            raise VerifierError("report_not_found", f"session 尚无 finalized report：{session}", status=404)
        latest = max(candidates, key=lambda item: str(item.get("updatedAt") or ""))
        return self.get_report(str(latest["report"]))

    def get_report(self, value: str) -> dict[str, Any]:
        path = resolve_under(self.config.state_root, Path(value), must_exist=True)
        if path.name != "report.json":
            raise VerifierError("invalid_report_path", "report path 必须指向 report.json")
        return {"ok": True, "report": str(path), "result": json.loads(path.read_text(encoding="utf-8"))}

    def get_artifact(self, value: str) -> dict[str, Any]:
        path = resolve_under(self.config.state_root, Path(value), must_exist=True)
        if not path.is_file():
            raise VerifierError("invalid_artifact_path", "artifact path 必须是文件")
        return {"ok": True, "artifact": str(path), "bytes": path.stat().st_size}
