#!/usr/bin/env python3
"""依赖选型 contract 与 evidence receipt 的确定性校验。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from harness_contract import (
    ValidationIssue,
    check_closed_object,
    check_id,
    check_references,
    check_string,
    check_string_list,
    collect_ids,
)
from harness_contract_dependency_common import dependency_issue
from harness_contract_dependency_triggers import has_contract_dependency_trigger


SELECTION_FIELDS = {
    "mode",
    "necessity_result",
    "decision_ids",
    "evidence_artifact_ids",
    "decisions",
}
DECISION_FIELDS = {
    "id",
    "action",
    "category",
    "criticality",
    "requirement_ids",
    "selection_class",
    "ecosystem",
    "package",
    "source_repository",
    "selected_version",
    "version_policy",
    "manifest_paths",
    "freshness_max_age_days",
    "evidence_artifact_id",
    "validation_ids",
}
SELECTION_MODES = {"none", "retain", "change", "mixed"}
ACTIONS = {"retain", "add", "upgrade", "replace"}
CHANGE_ACTIONS = ACTIONS - {"retain"}
NECESSITY_RESULTS = {
    "not-triggered",
    "dependency-required",
    "existing-sufficient",
    "standard-or-official-sufficient",
    "blocked",
}
SELECTION_CLASSES = {
    "existing-stack",
    "standard-or-official",
    "ecosystem-mainstream",
    "specialized-exception",
}
FRESHNESS_DAYS = {"critical-runtime": 30, "runtime": 60, "dev-build": 90}
def check_workspace_path(
    value: Any,
    path: str,
    issues: list[ValidationIssue],
) -> str:
    if not check_string(value, path, issues):
        return ""
    raw = str(value)
    normalized = raw.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    unsafe = candidate.is_absolute() or ".." in candidate.parts
    unsafe = unsafe or bool(candidate.parts and ":" in candidate.parts[0])
    if unsafe:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            path,
            "manifest path 必须是 workspace 内相对路径。",
            "移除绝对路径、盘符和 ..。",
        )
        return ""
    return normalized


def safe_evidence_url(value: Any, path: str, issues: list[ValidationIssue]) -> str:
    if not check_string(value, path, issues):
        return ""
    raw = str(value)
    if len(raw) > 2048:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "evidence URL 过长。",
            "保存稳定、无秘密的来源 URL。",
        )
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "必须是 HTTP(S) evidence URL。",
            "使用官方、registry 或一手来源 URL。",
        )
        return ""
    if parsed.username or parsed.password:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "evidence URL 不得包含 credential。",
            "移除用户名、密码或 token。",
        )
        return ""
    sensitive_keys = {
        "access_token", "api_key", "apikey", "auth",
        "credential", "key", "password", "private_token",
        "secret", "sig", "signature", "token",
    }
    query_keys = {
        key.lower()
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    }
    if query_keys & sensitive_keys:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_INVALID",
            path,
            "evidence URL query 疑似包含 credential 或签名。",
            "保存无秘密的 canonical source URL。",
        )
        return ""
    return raw


def validate_dependency_selection(
    contract: dict[str, Any],
    task_dir: Path,
    mode: str,
    *,
    requirement_ids: set[str],
    validation_ids: set[str],
    artifacts: list[dict[str, Any]],
    artifact_ids: set[str],
    issues: list[ValidationIssue],
) -> set[str]:
    selection = contract.get("dependency_selection")
    if selection is None:
        if has_contract_dependency_trigger(contract):
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_SELECTION_MISSING",
                "$.dependency_selection",
                "计划范围触发了依赖选型，但缺少 dependency_selection。",
                "补充 mode、necessity、DEP decisions 和 evidence artifact。",
            )
        return set()
    if not check_closed_object(selection, "$.dependency_selection", SELECTION_FIELDS, issues):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection",
            "dependency selection 摘要结构不完整。",
            "按 task-contract.md 补齐 closed fields。",
        )
        return set()

    selection_mode = selection.get("mode")
    if selection_mode not in SELECTION_MODES:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_MODE_INVALID",
            "$.dependency_selection.mode",
            "未知 dependency selection mode。",
            "使用 none、retain、change 或 mixed。",
        )
    necessity_result = selection.get("necessity_result")
    if necessity_result not in NECESSITY_RESULTS:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection.necessity_result",
            "未知 necessity result。",
            "使用 Dependency Selection Gate 定义的受控结果。",
        )

    declared_ids = check_string_list(
        selection.get("decision_ids"),
        "$.dependency_selection.decision_ids",
        issues,
    )
    valid_declared_ids = {
        check_id(value, "dependency", f"$.dependency_selection.decision_ids[{index}]", issues)
        for index, value in enumerate(declared_ids)
    }
    valid_declared_ids.discard("")
    if len(valid_declared_ids) != len(declared_ids):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection.decision_ids",
            "decision_ids 必须唯一且格式有效。",
            "使用唯一 DEP-* ID。",
        )

    evidence_ids = check_string_list(
        selection.get("evidence_artifact_ids"),
        "$.dependency_selection.evidence_artifact_ids",
        issues,
    )
    check_references(
        evidence_ids,
        artifact_ids,
        "$.dependency_selection.evidence_artifact_ids",
        issues,
    )
    decisions, decision_ids = collect_ids(
        selection.get("decisions"),
        "dependency",
        "$.dependency_selection.decisions",
        issues,
    )
    if len(decisions) > 50:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection.decisions",
            "单个 task 最多允许 50 个 dependency decisions。",
            "拆分不相关的依赖选型任务。",
        )
    if valid_declared_ids != decision_ids:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection.decision_ids",
            "decision_ids 与 decisions 中的 DEP ID 不一致。",
            "同步摘要 ID 与 decision objects。",
        )

    artifact_map = {
        str(item.get("id")): item
        for item in artifacts
        if isinstance(item.get("id"), str)
    }
    dependency_artifact_ids = {
        artifact_id
        for artifact_id, item in artifact_map.items()
        if item.get("kind") == "dependency"
    }

    if selection_mode == "none":
        if necessity_result != "not-triggered" or decisions or evidence_ids:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_TRIGGER_MISMATCH",
                "$.dependency_selection",
                "none mode 必须使用 not-triggered 且没有 decision/evidence artifact。",
                "移除虚假依赖决策，或改用 retain/change/mixed。",
            )
        if has_contract_dependency_trigger(contract):
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_TRIGGER_MISMATCH",
                "$.dependency_selection.mode",
                "stage/artifact scope 已触发依赖选型，不能声明 none。",
                "根据实际 action 选择 retain、change 或 mixed。",
            )
        return decision_ids

    if not decisions:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection.decisions",
            "非 none mode 至少需要一个 decision。",
            "补充 DEP-* 决策。",
        )
    if necessity_result in {"not-triggered", "blocked"}:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_DECISION_INVALID",
            "$.dependency_selection.necessity_result",
            "非 none 可审批计划必须完成 necessity decision。",
            "证明依赖必要、现有方案足够或标准/官方能力足够。",
        )
    if set(evidence_ids) != dependency_artifact_ids:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_MISSING",
            "$.dependency_selection.evidence_artifact_ids",
            "依赖 evidence IDs 必须与 contract 的 dependency artifacts 完全一致。",
            "只索引本次依赖决策的 required JSON artifacts。",
        )

    referenced_artifacts: set[str] = set()
    actions: set[str] = set()
    decisions_by_artifact: dict[str, list[dict[str, Any]]] = {}
    for index, decision in enumerate(decisions):
        path = f"$.dependency_selection.decisions[{index}]"
        if not check_closed_object(decision, path, DECISION_FIELDS, issues):
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                path,
                "dependency decision 结构不完整。",
                "补齐身份、版本、manifest、freshness 和引用。",
            )
            continue
        action = decision.get("action")
        if action not in ACTIONS:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.action",
                "未知 dependency action。",
                "使用 retain、add、upgrade 或 replace。",
            )
        elif isinstance(action, str):
            actions.add(action)
        criticality = decision.get("criticality")
        if criticality not in FRESHNESS_DAYS:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.criticality",
                "未知 dependency criticality。",
                "使用 critical-runtime、runtime 或 dev-build。",
            )
        expected_age = FRESHNESS_DAYS.get(str(criticality))
        if decision.get("freshness_max_age_days") != expected_age:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_STALE",
                f"{path}.freshness_max_age_days",
                "freshness policy 与 criticality 不一致。",
                "critical-runtime/runtime/dev-build 分别使用 30/60/90 天。",
            )
        if decision.get("selection_class") not in SELECTION_CLASSES:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.selection_class",
                "未知 selection class。",
                "使用现有栈、标准/官方、生态主流或专用例外。",
            )
        for field in (
            "category",
            "ecosystem",
            "package",
            "selected_version",
            "version_policy",
        ):
            check_string(decision.get(field), f"{path}.{field}", issues)
        safe_evidence_url(decision.get("source_repository"), f"{path}.source_repository", issues)
        requirement_refs = check_string_list(
            decision.get("requirement_ids"),
            f"{path}.requirement_ids",
            issues,
            allow_empty=False,
        )
        if len(requirement_refs) > 50:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.requirement_ids",
                "requirement refs 超过 50 项。",
                "拆分 decision。",
            )
        check_references(requirement_refs, requirement_ids, f"{path}.requirement_ids", issues)
        validation_refs = check_string_list(
            decision.get("validation_ids"),
            f"{path}.validation_ids",
            issues,
            allow_empty=False,
        )
        if len(validation_refs) > 50:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.validation_ids",
                "validation refs 超过 50 项。",
                "拆分或合并验证。",
            )
        check_references(validation_refs, validation_ids, f"{path}.validation_ids", issues)
        manifests = check_string_list(
            decision.get("manifest_paths"),
            f"{path}.manifest_paths",
            issues,
            allow_empty=False,
        )
        if len(manifests) > 32:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.manifest_paths",
                "manifest paths 超过 32 项。",
                "拆分跨生态 decision。",
            )
        normalized_paths = [
            check_workspace_path(value, f"{path}.manifest_paths[{item_index}]", issues)
            for item_index, value in enumerate(manifests)
        ]
        if len({value for value in normalized_paths if value}) != len(manifests):
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_DECISION_INVALID",
                f"{path}.manifest_paths",
                "manifest paths 必须有效且唯一。",
                "删除重复或不安全路径。",
            )
        artifact_id = decision.get("evidence_artifact_id")
        if not isinstance(artifact_id, str) or artifact_id not in dependency_artifact_ids:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_MISSING",
                f"{path}.evidence_artifact_id",
                "decision 必须引用 dependency artifact。",
                "引用 artifacts 中 kind=dependency 的 ART-*。",
            )
        else:
            referenced_artifacts.add(artifact_id)
            decisions_by_artifact.setdefault(artifact_id, []).append(decision)

    if selection_mode == "retain" and actions != {"retain"}:
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_MODE_INVALID",
            "$.dependency_selection.mode",
            "retain mode 只能包含 retain action。",
            "修正 mode 或 action。",
        )
    if selection_mode == "change" and (not actions or not actions <= CHANGE_ACTIONS):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_MODE_INVALID",
            "$.dependency_selection.mode",
            "change mode 只能包含 add/upgrade/replace。",
            "修正 mode 或 action。",
        )
    if selection_mode == "mixed" and not ({"retain"} <= actions and actions & CHANGE_ACTIONS):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_MODE_INVALID",
            "$.dependency_selection.mode",
            "mixed mode 必须同时包含 retain 与 change action。",
            "补齐两类 action 或修正 mode。",
        )
    if referenced_artifacts != set(evidence_ids):
        dependency_issue(
            issues,
            "TASK_DEPENDENCY_EVIDENCE_MISSING",
            "$.dependency_selection.evidence_artifact_ids",
            "存在未被 decision 使用或未列入摘要的 dependency artifact。",
            "同步 decision 和 evidence_artifact_ids。",
        )

    from harness_contract_dependency_artifact import validate_dependency_artifact

    for artifact_id, expected_decisions in decisions_by_artifact.items():
        metadata = artifact_map[artifact_id]
        if metadata.get("required") is not True or metadata.get("approval_included") is not True:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_MISSING",
                f"$.artifacts.{artifact_id}",
                "dependency artifact 必须 required 且 approval_included。",
                "把完整 evidence receipt 纳入批准哈希集合。",
            )
        relative = metadata.get("path")
        valid_artifact_path = (
            isinstance(relative, str)
            and relative.replace("\\", "/").startswith("artifacts/dependencies/")
            and relative.endswith(".json")
        )
        if not valid_artifact_path:
            dependency_issue(
                issues,
                "TASK_DEPENDENCY_EVIDENCE_INVALID",
                f"$.artifacts.{artifact_id}.path",
                "dependency artifact 必须位于 artifacts/dependencies/ 且为 JSON。",
                "使用结构化 dependency-selection.json receipt。",
            )
            continue
        artifact_path = task_dir / relative
        if artifact_path.is_file():
            validate_dependency_artifact(
                artifact_path,
                expected_decisions,
                requirement_ids,
                mode,
                issues,
            )
    return decision_ids
