"""校验目标、需求、风险与上下文扩展覆盖。"""

from __future__ import annotations

import re
from typing import Any

from .context import RISK_IDS
from .errors import ReviewError
from .io import normalize_relative_path
from .review_parts import (
    _closed,
    _evidence_refs,
    _nonempty,
    _strings,
)


COVERAGE_FIELDS = {
    "target_paths",
    "requirement_checks",
    "risk_checks",
    "context_expansions",
}
TARGET_COVERAGE_FIELDS = {"path", "status", "reason", "gap_ids"}
REQUIREMENT_CHECK_FIELDS = {
    "id",
    "status",
    "evidence_refs",
    "finding_ids",
    "gap_ids",
    "summary",
}
RISK_CHECK_FIELDS = {
    "id",
    "status",
    "trigger",
    "evidence_refs",
    "finding_ids",
    "gap_ids",
    "summary",
}
CONTEXT_EXPANSION_FIELDS = {
    "id",
    "risk",
    "paths",
    "result",
    "evidence_refs",
    "finding_ids",
    "gap_ids",
}
EXPANSION_ID = re.compile(r"^CTX-[0-9]{3,}$")


def _validate_links(values: Any, path: str, known: set[str]) -> list[str]:
    links = _strings(values, path, ordered=True)
    unknown = sorted(set(links) - known)
    if unknown:
        raise ReviewError(
            "REVIEW_COVERAGE_LINK_INVALID",
            "引用未知 ID：" + ", ".join(unknown),
            path=path,
        )
    return links


def _validate_target_paths(
    raw: Any,
    *,
    expected_paths: list[str],
    gaps: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_COVERAGE_TYPE_INVALID", "target_paths 必须是数组。")
    seen = []
    for index, item in enumerate(raw):
        path = f"$.coverage.target_paths[{index}]"
        record = _closed(item, TARGET_COVERAGE_FIELDS, path)
        normalized = normalize_relative_path(record["path"])
        if normalized != record["path"]:
            raise ReviewError("REVIEW_COVERAGE_PATH_INVALID", "coverage path 未 canonicalize。", path=path)
        if record["status"] not in {"reviewed", "excluded", "blocked"}:
            raise ReviewError("REVIEW_COVERAGE_STATUS_INVALID", "target coverage status 无效。", path=path)
        _nonempty(record["reason"], f"{path}.reason")
        gap_ids = _validate_links(record["gap_ids"], f"{path}.gap_ids", set(gaps))
        if record["status"] == "blocked" and not any(
            gaps[item]["severity"] in {"blocking", "major"} for item in gap_ids
        ):
            raise ReviewError("REVIEW_COVERAGE_GAP_MISSING", "blocked target path 需要 blocking/major gap。", path=path)
        if record["status"] != "blocked" and gap_ids:
            raise ReviewError("REVIEW_COVERAGE_LINK_INVALID", "非 blocked target path 不得关联 gap。", path=path)
        seen.append(normalized)
    if seen != expected_paths:
        raise ReviewError(
            "REVIEW_COVERAGE_TARGET_MISMATCH",
            f"target coverage 必须精确匹配 manifest：expected={expected_paths}, actual={seen}",
        )


def _validate_requirements(
    raw: Any,
    *,
    allowed_paths: set[str],
    findings: dict[str, dict[str, Any]],
    gaps: dict[str, dict[str, Any]],
    expected_refs: list[str] | None,
) -> None:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_COVERAGE_TYPE_INVALID", "requirement_checks 必须是数组。")
    ids = []
    for index, item in enumerate(raw):
        path = f"$.coverage.requirement_checks[{index}]"
        record = _closed(item, REQUIREMENT_CHECK_FIELDS, path)
        requirement_id = _nonempty(record["id"], f"{path}.id")
        status = record["status"]
        if status not in {"satisfied", "violated", "not-verifiable", "not-applicable"}:
            raise ReviewError("REVIEW_COVERAGE_STATUS_INVALID", "requirement status 无效。", path=path)
        evidence = _evidence_refs(
            record["evidence_refs"],
            f"{path}.evidence_refs",
            allowed_paths,
            allow_empty=status == "not-applicable",
        )
        finding_ids = _validate_links(record["finding_ids"], f"{path}.finding_ids", set(findings))
        gap_ids = _validate_links(record["gap_ids"], f"{path}.gap_ids", set(gaps))
        _nonempty(record["summary"], f"{path}.summary")
        if status == "satisfied" and (finding_ids or gap_ids or not evidence):
            raise ReviewError("REVIEW_COVERAGE_LINK_INVALID", "satisfied requirement 只接受直接证据。", path=path)
        if status == "violated" and (
            not finding_ids
            or gap_ids
            or not any(findings[item]["status"] in {"open", "accepted", "deferred"} for item in finding_ids)
        ):
            raise ReviewError("REVIEW_COVERAGE_FINDING_MISSING", "violated requirement 需要 unresolved finding。", path=path)
        if status == "not-verifiable" and (not gap_ids or finding_ids):
            raise ReviewError("REVIEW_COVERAGE_GAP_MISSING", "not-verifiable requirement 需要 gap。", path=path)
        if status == "not-applicable" and (finding_ids or gap_ids):
            raise ReviewError("REVIEW_COVERAGE_LINK_INVALID", "not-applicable requirement 不得关联 finding/gap。", path=path)
        ids.append(requirement_id)
    if ids != sorted(set(ids)):
        raise ReviewError("REVIEW_COVERAGE_ORDER_INVALID", "requirement checks 必须按 ID 排序且去重。")
    if expected_refs is not None and ids != expected_refs:
        raise ReviewError(
            "REVIEW_COVERAGE_REQUIREMENT_MISMATCH",
            f"requirement coverage 与 brief 不一致：expected={expected_refs}, actual={ids}",
        )


def _validate_risks(
    raw: Any,
    *,
    allowed_paths: set[str],
    findings: dict[str, dict[str, Any]],
    gaps: dict[str, dict[str, Any]],
    requested_risks: list[str],
) -> None:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_COVERAGE_TYPE_INVALID", "risk_checks 必须是数组。")
    ids = []
    for index, item in enumerate(raw):
        path = f"$.coverage.risk_checks[{index}]"
        record = _closed(item, RISK_CHECK_FIELDS, path)
        risk_id = _nonempty(record["id"], f"{path}.id")
        status = record["status"]
        if status not in {"triggered-reviewed", "not-triggered", "blocked"}:
            raise ReviewError("REVIEW_COVERAGE_STATUS_INVALID", "risk status 无效。", path=path)
        _nonempty(record["trigger"], f"{path}.trigger")
        _evidence_refs(record["evidence_refs"], f"{path}.evidence_refs", allowed_paths)
        finding_ids = _validate_links(record["finding_ids"], f"{path}.finding_ids", set(findings))
        gap_ids = _validate_links(record["gap_ids"], f"{path}.gap_ids", set(gaps))
        _nonempty(record["summary"], f"{path}.summary")
        if status == "blocked" and not any(
            gaps[item]["severity"] in {"blocking", "major"} for item in gap_ids
        ):
            raise ReviewError("REVIEW_COVERAGE_GAP_MISSING", "blocked risk 需要 blocking/major gap。", path=path)
        if status != "blocked" and gap_ids:
            raise ReviewError("REVIEW_COVERAGE_LINK_INVALID", "非 blocked risk 不得关联 gap。", path=path)
        if status == "not-triggered" and finding_ids:
            raise ReviewError("REVIEW_COVERAGE_LINK_INVALID", "not-triggered risk 不得关联 finding。", path=path)
        if risk_id in requested_risks and status == "not-triggered":
            raise ReviewError("REVIEW_COVERAGE_RISK_UNREVIEWED", "brief 指定的 risk 不能标记 not-triggered。", path=path)
        ids.append(risk_id)
    if tuple(ids) != RISK_IDS:
        raise ReviewError("REVIEW_COVERAGE_RISK_INCOMPLETE", "risk checks 必须按六类固定顺序完整出现。")


def _validate_expansions(
    raw: Any,
    *,
    allowed_paths: set[str],
    context_paths: set[str],
    findings: dict[str, dict[str, Any]],
    gaps: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_COVERAGE_TYPE_INVALID", "context_expansions 必须是数组。")
    ids = []
    for index, item in enumerate(raw):
        path = f"$.coverage.context_expansions[{index}]"
        record = _closed(item, CONTEXT_EXPANSION_FIELDS, path)
        expansion_id = _nonempty(record["id"], f"{path}.id")
        if not EXPANSION_ID.fullmatch(expansion_id):
            raise ReviewError("REVIEW_COVERAGE_ID_INVALID", "context expansion id 必须使用 CTX-NNN。", path=path)
        _nonempty(record["risk"], f"{path}.risk")
        paths = _strings(record["paths"], f"{path}.paths", allow_empty=False, ordered=True)
        if not set(paths) <= context_paths:
            raise ReviewError("REVIEW_COVERAGE_PATH_INVALID", "context expansion path 未进入 context target。", path=path)
        if record["result"] not in {"supported", "finding", "unresolved"}:
            raise ReviewError("REVIEW_COVERAGE_STATUS_INVALID", "context expansion result 无效。", path=path)
        _evidence_refs(record["evidence_refs"], f"{path}.evidence_refs", allowed_paths)
        finding_ids = _validate_links(record["finding_ids"], f"{path}.finding_ids", set(findings))
        gap_ids = _validate_links(record["gap_ids"], f"{path}.gap_ids", set(gaps))
        if record["result"] == "supported" and (finding_ids or gap_ids):
            raise ReviewError("REVIEW_COVERAGE_LINK_INVALID", "supported expansion 不得关联 finding/gap。", path=path)
        if record["result"] == "finding" and (not finding_ids or gap_ids):
            raise ReviewError("REVIEW_COVERAGE_FINDING_MISSING", "finding expansion 需要 finding。", path=path)
        if record["result"] == "unresolved" and (not gap_ids or finding_ids):
            raise ReviewError("REVIEW_COVERAGE_GAP_MISSING", "unresolved expansion 需要 gap。", path=path)
        ids.append(expansion_id)
    if ids != sorted(set(ids)):
        raise ReviewError("REVIEW_COVERAGE_ORDER_INVALID", "context expansions 必须按 ID 排序且去重。")


def validate_coverage(
    raw: Any,
    *,
    target_paths: list[str],
    context_paths: set[str],
    findings: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    expected_requirement_refs: list[str] | None,
    requested_risks: list[str],
) -> dict[str, Any]:
    coverage = _closed(raw, COVERAGE_FIELDS, "$.coverage")
    allowed_paths = set(target_paths) | context_paths
    finding_map = {item["id"]: item for item in findings}
    gap_map = {item["id"]: item for item in gaps}
    _validate_target_paths(coverage["target_paths"], expected_paths=target_paths, gaps=gap_map)
    _validate_requirements(
        coverage["requirement_checks"],
        allowed_paths=allowed_paths,
        findings=finding_map,
        gaps=gap_map,
        expected_refs=expected_requirement_refs,
    )
    _validate_risks(
        coverage["risk_checks"],
        allowed_paths=allowed_paths,
        findings=finding_map,
        gaps=gap_map,
        requested_risks=requested_risks,
    )
    _validate_expansions(
        coverage["context_expansions"],
        allowed_paths=allowed_paths,
        context_paths=context_paths,
        findings=finding_map,
        gaps=gap_map,
    )
    linked_findings = {
        finding_id
        for section in (
            coverage["requirement_checks"],
            coverage["risk_checks"],
            coverage["context_expansions"],
        )
        for item in section
        for finding_id in item["finding_ids"]
    }
    linked_gaps = {
        gap_id
        for section in (
            coverage["target_paths"],
            coverage["requirement_checks"],
            coverage["risk_checks"],
            coverage["context_expansions"],
        )
        for item in section
        for gap_id in item["gap_ids"]
    }
    active_findings = {
        finding_id
        for finding_id, finding in finding_map.items()
        if finding["status"] in {"open", "accepted", "deferred"}
    }
    unlinked_findings = sorted(active_findings - linked_findings)
    unlinked_gaps = sorted(set(gap_map) - linked_gaps)
    if unlinked_findings or unlinked_gaps:
        raise ReviewError(
            "REVIEW_COVERAGE_LINK_INCOMPLETE",
            f"unlinked findings={unlinked_findings}, gaps={unlinked_gaps}",
        )
    return coverage


def coverage_summary(coverage: dict[str, Any]) -> dict[str, int]:
    return {
        "target_paths": len(coverage["target_paths"]),
        "requirements": len(coverage["requirement_checks"]),
        "risks": len(coverage["risk_checks"]),
        "context_expansions": len(coverage["context_expansions"]),
    }
