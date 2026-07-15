#!/usr/bin/env python3
"""只读校验批准的 dependency decision 与执行期 receipt。"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from harness_task_bundle import TaskBundle


FRESHNESS_DAYS = {"critical-runtime": 30, "runtime": 60, "dev-build": 90}
CHANGE_ACTIONS = {"add", "upgrade", "replace"}
HARD_GATES = {
    "authenticity",
    "compatibility",
    "stable_support",
    "lifecycle",
    "security",
    "license",
    "reproducibility",
}
RUNTIME_ROOT_FIELDS = {"observed_at", "decisions"}
RUNTIME_DECISION_FIELDS = {
    "decision_id",
    "package",
    "source_repository",
    "selection_class",
    "approved_selected_version",
    "approved_version_policy",
    "resolved_version",
    "manifest_paths",
    "version_policy_result",
    "manifest_result",
    "lock_result",
    "hard_gate_checks",
    "evidence_urls",
    "summary",
}
CHECK_RESULTS = {"passed", "failed", "blocked-by-access", "not-applicable"}
FACT_RESULTS = {"unchanged", "changed", "blocked-by-access"}
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "credential",
    "key",
    "password",
    "private_token",
    "secret",
    "sig",
    "signature",
    "token",
}


class DependencyGateError(Exception):
    """依赖执行事实缺失、漂移或无法证明。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def closed_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 必须是 object。",
        )
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 不是 closed object：unknown={unknown}, missing={missing}",
        )
    return value


def parse_date(value: Any, label: str, today: date) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 必须是 YYYY-MM-DD。",
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 不是有效日期。",
        ) from exc
    if parsed > today:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 不能位于未来。",
        )
    return parsed


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError("文件超过 1 MB")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"无法读取 {label}：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 根节点必须是 object。",
        )
    return value


def task_relative_file(bundle: TaskBundle, raw: str, label: str) -> Path:
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 必须是 task-dir 内相对路径。",
        )
    resolved = (bundle.task_dir / candidate).resolve()
    try:
        resolved.relative_to(bundle.task_dir)
    except ValueError as exc:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 越出 task-dir：{raw}",
        ) from exc
    return resolved


def safe_url(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 必须是有界 URL。",
        )
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 必须是 HTTP(S) URL。",
        )
    if parsed.username or parsed.password:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 不得包含 credential。",
        )
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query)}
    if query_keys & SENSITIVE_QUERY_KEYS:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} query 疑似包含 credential。",
        )
    return value


def dependency_selection(bundle: TaskBundle) -> tuple[str, list[dict[str, Any]]]:
    selection = bundle.contract.get("dependency_selection")
    if selection is None:
        return "none", []
    if not isinstance(selection, dict):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            "contract.dependency_selection 必须是 object。",
        )
    mode = selection.get("mode")
    decisions = selection.get("decisions")
    if mode == "none":
        if decisions not in ([], None):
            raise DependencyGateError(
                "EXEC_DEPENDENCY_APPROVAL_INVALID",
                "none dependency selection 不能包含 decisions。",
            )
        return "none", []
    if mode not in {"retain", "change", "mixed"} or not isinstance(decisions, list):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            "批准的 dependency mode 或 decisions 无效。",
        )
    if not decisions or any(not isinstance(item, dict) for item in decisions):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            "非 none dependency selection 必须包含 decisions。",
        )
    return str(mode), decisions


def dependency_artifact(bundle: TaskBundle, decision: dict[str, Any]) -> dict[str, Any]:
    artifact_id = decision.get("evidence_artifact_id")
    artifacts = bundle.contract.get("artifacts", [])
    metadata = next(
        (
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("id") == artifact_id
        ),
        None,
    )
    if not isinstance(metadata, dict) or not isinstance(metadata.get("path"), str):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            f"{decision.get('id')} 缺少批准 dependency artifact。",
        )
    path = task_relative_file(bundle, str(metadata["path"]), "dependency artifact")
    return load_json(path, "approved dependency artifact")


def selected_candidate(artifact: dict[str, Any], decision_id: str) -> dict[str, Any]:
    receipts = artifact.get("decisions")
    if not isinstance(receipts, list):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            "批准 dependency artifact 缺少 decisions。",
        )
    receipt = next(
        (
            item
            for item in receipts
            if isinstance(item, dict) and item.get("decision_id") == decision_id
        ),
        None,
    )
    candidates = receipt.get("candidates") if isinstance(receipt, dict) else None
    selected = [
        item
        for item in candidates or []
        if isinstance(item, dict) and item.get("disposition") == "selected"
    ]
    if len(selected) != 1:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            f"{decision_id} 没有唯一 selected candidate。",
        )
    return selected[0]


def approved_evidence_date(
    bundle: TaskBundle,
    decision: dict[str, Any],
    today: date,
) -> date:
    decision_id = str(decision.get("id", ""))
    artifact = dependency_artifact(bundle, decision)
    candidate = selected_candidate(artifact, decision_id)
    values: list[Any] = [artifact.get("observed_at")]
    signals = candidate.get("trust_signals")
    if isinstance(signals, dict):
        values.extend(
            item.get("as_of")
            for item in signals.values()
            if isinstance(item, dict)
        )
    dates = [parse_date(value, f"{decision_id}.approved_as_of", today) for value in values]
    if not dates:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            f"{decision_id} 缺少批准证据日期。",
        )
    return min(dates)


def normalized_paths(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 必须是非空数组。",
        )
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_RECEIPT_INVALID",
                f"{label} 只能包含非空字符串。",
            )
        candidate = Path(item)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_RECEIPT_INVALID",
                f"{label} 包含不安全路径：{item}",
            )
        paths.append(item.replace("\\", "/"))
    if len(paths) != len(set(paths)):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{label} 包含重复路径。",
        )
    return paths


def validate_runtime_decision(
    value: Any,
    expected: dict[str, Any],
    *,
    require_manifest: bool,
) -> dict[str, Any]:
    decision_id = str(expected.get("id", ""))
    receipt = closed_object(value, RUNTIME_DECISION_FIELDS, decision_id)
    exact_fields = {
        "decision_id": "id",
        "package": "package",
        "source_repository": "source_repository",
        "selection_class": "selection_class",
        "approved_selected_version": "selected_version",
        "approved_version_policy": "version_policy",
    }
    for runtime_field, contract_field in exact_fields.items():
        if receipt.get(runtime_field) != expected.get(contract_field):
            raise DependencyGateError(
                "EXEC_DEPENDENCY_APPROVAL_DRIFT",
                f"{decision_id}.{runtime_field} 与批准 contract 不一致；需要 amendment。",
            )
    actual_paths = normalized_paths(receipt.get("manifest_paths"), f"{decision_id}.manifest_paths")
    expected_paths = [str(item).replace("\\", "/") for item in expected.get("manifest_paths", [])]
    if set(actual_paths) != set(expected_paths):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_DRIFT",
            f"{decision_id}.manifest_paths 与批准集合不一致；需要 amendment。",
        )
    resolved_version = receipt.get("resolved_version")
    summary = receipt.get("summary")
    if not isinstance(resolved_version, str) or not resolved_version.strip():
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{decision_id}.resolved_version 必须是非空字符串。",
        )
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 2000:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{decision_id}.summary 必须是 1-2000 字符。",
        )

    checks = receipt.get("hard_gate_checks")
    if not isinstance(checks, dict) or set(checks) != HARD_GATES:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{decision_id}.hard_gate_checks 必须完整覆盖七项门禁。",
        )
    if any(result not in FACT_RESULTS for result in checks.values()):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{decision_id}.hard_gate_checks 包含无效结果。",
        )
    blocked = sorted(name for name, result in checks.items() if result == "blocked-by-access")
    changed = sorted(name for name, result in checks.items() if result == "changed")
    if blocked:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECHECK_BLOCKED",
            f"{decision_id} 无法复核 hard gates：{blocked}",
        )
    if changed:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RESEARCH_DRIFT",
            f"{decision_id} hard-gate 事实变化：{changed}；记录 drift 并判断 amendment。",
        )

    evidence_urls = receipt.get("evidence_urls")
    if not isinstance(evidence_urls, list) or not 1 <= len(evidence_urls) <= 20:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            f"{decision_id}.evidence_urls 必须包含 1-20 个来源。",
        )
    for index, url in enumerate(evidence_urls):
        safe_url(url, f"{decision_id}.evidence_urls[{index}]")

    for field in ("version_policy_result", "manifest_result", "lock_result"):
        if receipt.get(field) not in CHECK_RESULTS:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_RECEIPT_INVALID",
                f"{decision_id}.{field} 不是受控结果。",
            )
        if receipt.get(field) == "blocked-by-access":
            raise DependencyGateError(
                "EXEC_DEPENDENCY_RECHECK_BLOCKED",
                f"{decision_id}.{field} 无法验证。",
            )
        if receipt.get(field) == "failed":
            raise DependencyGateError(
                "EXEC_DEPENDENCY_IMPLEMENTATION_DRIFT",
                f"{decision_id}.{field} 已明确失败。",
            )
    if require_manifest:
        if receipt.get("version_policy_result") != "passed":
            raise DependencyGateError(
                "EXEC_DEPENDENCY_IMPLEMENTATION_DRIFT",
                f"{decision_id} resolved version 不符合批准 version policy。",
            )
        if receipt.get("manifest_result") != "passed":
            raise DependencyGateError(
                "EXEC_DEPENDENCY_IMPLEMENTATION_DRIFT",
                f"{decision_id} manifest identity/version 未通过原生验证。",
            )
        if receipt.get("lock_result") not in {"passed", "not-applicable"}:
            raise DependencyGateError(
                "EXEC_DEPENDENCY_IMPLEMENTATION_DRIFT",
                f"{decision_id} lock validation 未通过。",
            )
    return receipt


def validate_runtime_receipt(
    bundle: TaskBundle,
    raw_path: str,
    expected: list[dict[str, Any]],
    *,
    today: date,
    require_manifest: bool,
) -> dict[str, Any]:
    path = task_relative_file(bundle, raw_path, "runtime dependency receipt")
    root = closed_object(
        load_json(path, "runtime dependency receipt"),
        RUNTIME_ROOT_FIELDS,
        "$runtime",
    )
    observed = parse_date(root.get("observed_at"), "$runtime.observed_at", today)
    age_values = [item.get("freshness_max_age_days") for item in expected]
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in age_values
    ):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_APPROVAL_INVALID",
            "批准 decision 的 freshness_max_age_days 无效。",
        )
    maximum_age = min(age_values)
    if maximum_age not in FRESHNESS_DAYS.values() or (today - observed).days > maximum_age:
        raise DependencyGateError(
            "EXEC_DEPENDENCY_EVIDENCE_STALE",
            f"runtime receipt 超过 freshness 上限 {maximum_age} 天。",
        )
    values = root.get("decisions")
    if not isinstance(values, list):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            "$runtime.decisions 必须是数组。",
        )
    expected_map = {str(item.get("id")): item for item in expected}
    actual_map = {
        str(item.get("decision_id")): item
        for item in values
        if isinstance(item, dict)
    }
    if set(actual_map) != set(expected_map) or len(actual_map) != len(values):
        raise DependencyGateError(
            "EXEC_DEPENDENCY_RECEIPT_INVALID",
            "runtime receipt 必须与当前门禁的 DEP decisions 一一对应。",
        )
    for decision_id, decision in expected_map.items():
        validate_runtime_decision(
            actual_map[decision_id],
            decision,
            require_manifest=require_manifest,
        )
    return {
        "path": path.relative_to(bundle.task_dir).as_posix(),
        "observed_at": observed.isoformat(),
        "decision_ids": sorted(expected_map),
    }
