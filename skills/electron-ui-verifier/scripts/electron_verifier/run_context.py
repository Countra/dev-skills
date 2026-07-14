"""Run 现场上下文、当前状态与服务端 asset usage 校验。"""

from __future__ import annotations

from typing import Any

from .errors import VerifierError
from .sensitivity import normalize_parameter_schema


PREPARE_FIELDS = {
    "session",
    "name",
    "cdp",
    "targetType",
    "targetUrlContains",
    "targetTitleContains",
    "targetIndex",
    "targetId",
    "appId",
    "goal",
    "appVersion",
    "screenDigest",
    "preState",
    "maxRisk",
    "parameterSchema",
    "aliases",
    "reuse",
    "kind",
}
RISK_LEVELS = {"low", "medium", "high"}
ASSET_USAGE_FIELDS = {"assetId", "preState", "postState", "risk"}


def _optional_text(value: Any, label: str, maximum: int) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise VerifierError("invalid_run_context", f"{label} 必须是 1..{maximum} 字符的字符串")
    return value.strip()


def normalize_prepare_context(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VerifierError("invalid_run_context", "prepare 请求必须是 object")
    unknown = sorted(set(payload) - PREPARE_FIELDS)
    if unknown:
        raise VerifierError("invalid_run_context", f"prepare 请求包含未知字段：{unknown}")
    session_name = str(payload.get("session") or payload.get("name") or "").strip()
    if not session_name:
        raise VerifierError("session_name_required", "prepare 需要 session name")
    aliases = payload.get("aliases") or []
    if (
        not isinstance(aliases, list)
        or len(aliases) > 50
        or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 200 for item in aliases)
    ):
        raise VerifierError("invalid_run_context", "aliases 必须是最多 50 项的非空字符串数组")
    max_risk = str(payload.get("maxRisk") or "low").lower()
    if max_risk not in RISK_LEVELS:
        raise VerifierError("invalid_risk_level", f"maxRisk 不受支持：{max_risk}")
    return {
        "sessionName": session_name,
        "appId": _optional_text(payload.get("appId"), "appId", 200),
        "appVersion": _optional_text(payload.get("appVersion"), "appVersion", 100),
        "screenDigest": _optional_text(payload.get("screenDigest"), "screenDigest", 200),
        "preState": _optional_text(payload.get("preState"), "preState", 200),
        "maxRisk": max_risk,
        "goal": _optional_text(payload.get("goal"), "goal", 500),
        "aliases": sorted(set(item.strip() for item in aliases)),
        "parameterSchema": normalize_parameter_schema(payload.get("parameterSchema")),
    }


def current_run_state(journal: dict[str, Any]) -> str | None:
    for step in reversed(journal.get("steps", [])):
        if step.get("status") == "passed" and isinstance(step.get("postState"), str):
            return str(step["postState"])
    return str(journal["preState"]) if journal.get("preState") else None


def configure_asset_workflow(
    journal: dict[str, Any],
    asset_id: str,
    goal: str,
    expected_steps: int,
    parameter_schema: Any,
) -> None:
    if journal.get("state") not in {"prepared", "running"}:
        raise VerifierError("run_not_appendable", "run 当前状态不能执行 workflow asset", status=409)
    schema = normalize_parameter_schema(parameter_schema)
    current = normalize_parameter_schema(journal.get("parameterSchema"))
    if schema and current and schema != current:
        raise VerifierError("parameter_schema_conflict", "workflow asset 与 prepared run 的 parameterSchema 不一致", status=409)
    if schema and not current:
        if journal.get("steps"):
            raise VerifierError("parameter_schema_late_binding", "已有步骤后不能再修改 parameterSchema", status=409)
        journal["parameterSchema"] = schema
    journal["workflow"] = {
        "goal": goal[:500],
        "expectedSteps": expected_steps,
        "assetId": asset_id,
    }


def validate_asset_usage(value: Any, current_state: str | None) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != ASSET_USAGE_FIELDS:
        raise VerifierError("asset_usage_invalid", "服务端 asset usage 字段无效", status=500)
    if any(not isinstance(value.get(field), str) or not value[field] for field in ASSET_USAGE_FIELDS):
        raise VerifierError("asset_usage_invalid", "服务端 asset usage 值无效", status=500)
    if current_state != value["preState"]:
        raise VerifierError("asset_pre_state_mismatch", "asset preState 与当前 run state 不一致", status=409)
    return value
