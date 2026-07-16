"""校验 coverage、finding、strength、gap 与复审谱系。"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .errors import ReviewError
from .io import normalize_relative_path


FINDING_FIELDS = {
    "id",
    "category",
    "origin",
    "severity",
    "status",
    "title",
    "claim",
    "impact",
    "recommendation",
    "evidence",
    "confidence",
    "disposition_reason",
}
ORIGIN_FIELDS = {"review_id", "finding_id"}
EVIDENCE_FIELDS = {
    "path",
    "line",
    "symbol",
    "artifact_ref",
    "standard_ref",
    "detail",
    "claim_source",
}
STRENGTH_FIELDS = {"id", "claim", "evidence"}
GAP_FIELDS = {
    "id",
    "requirement_ref",
    "category",
    "claim",
    "needed_evidence",
    "owner",
    "severity",
    "evidence_refs",
}
COUNT_FIELDS = {"blocking", "major", "minor", "advisory", "total"}
GAP_COUNT_FIELDS = {"blocking", "major", "minor", "total"}

SEVERITIES = ("blocking", "major", "minor", "advisory")
GAP_SEVERITIES = ("blocking", "major", "minor")
FINDING_STATUSES = {"open", "resolved", "accepted", "deferred", "invalidated"}
CONFIDENCES = {"high", "medium", "low"}
CATEGORIES = {
    "requirement",
    "correctness",
    "security",
    "reliability",
    "architecture",
    "performance",
    "test",
    "delivery",
    "scope",
}
CLAIM_SOURCES = {"read", "observed", "reported", "inferred", "not-verified"}
GAP_OWNERS = {"caller", "planner", "executor", "specialist", "user"}
FINDING_ID = re.compile(r"^FIND-[0-9]{3,}$")
STRENGTH_ID = re.compile(r"^STR-[0-9]{3,}$")
GAP_ID = re.compile(r"^GAP-[0-9]{3,}$")


def _closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "值必须是 object。", path=path)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ReviewError(
            "REVIEW_CONTRACT_FIELDS_INVALID",
            f"unknown={unknown}, missing={missing}",
            path=path,
        )
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError("REVIEW_CONTRACT_VALUE_INVALID", "值必须是非空字符串。", path=path)
    return value


def _nullable(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, path)


def _strings(
    value: Any,
    path: str,
    *,
    allow_empty: bool = True,
    ordered: bool = False,
) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "值必须是非空字符串数组。", path=path)
    if not allow_empty and not value:
        raise ReviewError("REVIEW_CONTRACT_VALUE_INVALID", "数组不能为空。", path=path)
    if len(value) != len(set(value)) or (ordered and value != sorted(value)):
        raise ReviewError("REVIEW_CONTRACT_ORDER_INVALID", "数组必须排序且去重。", path=path)
    return value


def _bound_ref(reference: str, allowed_paths: set[str]) -> bool:
    return any(
        reference == path
        or reference.startswith(path + ":")
        or reference.startswith(path + "#")
        for path in allowed_paths
    )


def _evidence_refs(value: Any, path: str, allowed_paths: set[str], *, allow_empty: bool = False) -> list[str]:
    refs = _strings(value, path, allow_empty=allow_empty)
    unbound = sorted(item for item in refs if not _bound_ref(item, allowed_paths))
    if unbound:
        raise ReviewError(
            "REVIEW_COVERAGE_EVIDENCE_INVALID",
            "evidence_refs 未绑定 primary/context path：" + ", ".join(unbound),
            path=path,
        )
    return refs


def _validate_evidence(raw: Any, path: str, allowed_paths: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ReviewError("REVIEW_FINDING_EVIDENCE_MISSING", "至少需要一条定位证据。", path=path)
    result = []
    for index, item in enumerate(raw):
        item_path = f"{path}[{index}]"
        evidence = _closed(item, EVIDENCE_FIELDS, item_path)
        location = _nullable(evidence["path"], f"{item_path}.path")
        if location is not None:
            normalized = normalize_relative_path(location)
            if normalized != location or normalized not in allowed_paths:
                raise ReviewError(
                    "REVIEW_FINDING_EVIDENCE_INVALID",
                    "evidence path 必须 canonicalize 且位于 primary/context target。",
                    path=item_path,
                )
        line = evidence["line"]
        if line is not None:
            if not isinstance(line, int) or isinstance(line, bool) or line < 1 or location is None:
                raise ReviewError("REVIEW_FINDING_EVIDENCE_INVALID", "line 必须与 path 一起使用。", path=item_path)
        symbol = _nullable(evidence["symbol"], f"{item_path}.symbol")
        artifact = _nullable(evidence["artifact_ref"], f"{item_path}.artifact_ref")
        standard = _nullable(evidence["standard_ref"], f"{item_path}.standard_ref")
        _nonempty(evidence["detail"], f"{item_path}.detail")
        if evidence["claim_source"] not in CLAIM_SOURCES:
            raise ReviewError("REVIEW_FINDING_CLAIM_SOURCE_INVALID", "未知 claim_source。", path=item_path)
        if not any((location, symbol, artifact, standard)):
            raise ReviewError("REVIEW_FINDING_EVIDENCE_INVALID", "证据缺少可定位来源。", path=item_path)
        result.append(evidence)
    return result


def validate_findings(raw: Any, allowed_paths: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "findings 必须是数组。", path="$.findings")
    result = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        path = f"$.findings[{index}]"
        finding = _closed(item, FINDING_FIELDS, path)
        finding_id = _nonempty(finding["id"], f"{path}.id")
        if not FINDING_ID.fullmatch(finding_id) or finding_id in ids:
            raise ReviewError("REVIEW_FINDING_ID_INVALID", "finding id 必须唯一并使用 FIND-NNN。", path=path)
        ids.add(finding_id)
        if finding["category"] not in CATEGORIES:
            raise ReviewError("REVIEW_FINDING_CATEGORY_INVALID", "finding category 无效。", path=path)
        origin = _closed(finding["origin"], ORIGIN_FIELDS, f"{path}.origin")
        origin_review = _nullable(origin["review_id"], f"{path}.origin.review_id")
        origin_finding = _nullable(origin["finding_id"], f"{path}.origin.finding_id")
        if (origin_review is None) != (origin_finding is None):
            raise ReviewError("REVIEW_LINEAGE_ORIGIN_INVALID", "origin 两个字段必须同时为空或同时存在。", path=path)
        if finding["severity"] not in SEVERITIES:
            raise ReviewError("REVIEW_FINDING_SEVERITY_INVALID", "finding severity 无效。", path=path)
        if finding["status"] not in FINDING_STATUSES:
            raise ReviewError("REVIEW_FINDING_STATUS_INVALID", "finding status 无效。", path=path)
        if finding["confidence"] not in CONFIDENCES:
            raise ReviewError("REVIEW_FINDING_CONFIDENCE_INVALID", "confidence 无效。", path=path)
        for field in ("title", "claim", "impact", "recommendation"):
            _nonempty(finding[field], f"{path}.{field}")
        evidence = _validate_evidence(finding["evidence"], f"{path}.evidence", allowed_paths)
        disposition = finding["disposition_reason"]
        if finding["status"] == "open" and disposition is not None:
            raise ReviewError("REVIEW_FINDING_DISPOSITION_INVALID", "open finding 的 disposition 必须为 null。", path=path)
        if finding["status"] != "open":
            _nonempty(disposition, f"{path}.disposition_reason")
        if finding["severity"] in {"blocking", "major"} and finding["confidence"] == "low":
            raise ReviewError("REVIEW_FINDING_CONFIDENCE_INVALID", "低置信 finding 不能定为 blocking/major。", path=path)
        if finding["status"] in {"resolved", "invalidated"} and not any(
            record["claim_source"] in {"read", "observed"} for record in evidence
        ):
            raise ReviewError(
                "REVIEW_FINDING_DISPOSITION_INVALID",
                "resolved/invalidated finding 需要 read 或 observed 当前证据。",
                path=path,
            )
        result.append({**finding, "origin": origin})
    return result


def validate_strengths(raw: Any, allowed_paths: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "strengths 必须是数组。", path="$.strengths")
    result = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        path = f"$.strengths[{index}]"
        strength = _closed(item, STRENGTH_FIELDS, path)
        strength_id = _nonempty(strength["id"], f"{path}.id")
        if not STRENGTH_ID.fullmatch(strength_id) or strength_id in ids:
            raise ReviewError("REVIEW_STRENGTH_ID_INVALID", "strength id 必须唯一并使用 STR-NNN。", path=path)
        ids.add(strength_id)
        _nonempty(strength["claim"], f"{path}.claim")
        _validate_evidence(strength["evidence"], f"{path}.evidence", allowed_paths)
        result.append(strength)
    return result


def validate_gaps(raw: Any, allowed_paths: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "verification_gaps 必须是数组。")
    result = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        path = f"$.verification_gaps[{index}]"
        gap = _closed(item, GAP_FIELDS, path)
        gap_id = _nonempty(gap["id"], f"{path}.id")
        if not GAP_ID.fullmatch(gap_id) or gap_id in ids:
            raise ReviewError("REVIEW_GAP_ID_INVALID", "gap id 必须唯一并使用 GAP-NNN。", path=path)
        ids.add(gap_id)
        _nullable(gap["requirement_ref"], f"{path}.requirement_ref")
        if gap["category"] not in CATEGORIES:
            raise ReviewError("REVIEW_GAP_CATEGORY_INVALID", "gap category 无效。", path=path)
        if gap["owner"] not in GAP_OWNERS:
            raise ReviewError("REVIEW_GAP_OWNER_INVALID", "gap owner 无效。", path=path)
        if gap["severity"] not in GAP_SEVERITIES:
            raise ReviewError("REVIEW_GAP_SEVERITY_INVALID", "gap severity 无效。", path=path)
        _nonempty(gap["claim"], f"{path}.claim")
        _nonempty(gap["needed_evidence"], f"{path}.needed_evidence")
        _evidence_refs(gap["evidence_refs"], f"{path}.evidence_refs", allowed_paths)
        result.append(gap)
    return result


def derive_open_counts(findings: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        if finding["status"] == "open":
            counts[finding["severity"]] += 1
    return {**counts, "total": sum(counts.values())}


def validate_open_counts(raw: Any, derived: dict[str, int]) -> dict[str, int]:
    counts = _closed(raw, COUNT_FIELDS, "$.open_counts")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values()):
        raise ReviewError("REVIEW_CONTRACT_COUNT_INVALID", "open count 必须是非负整数。")
    if counts != derived:
        raise ReviewError("REVIEW_CONTRACT_COUNT_MISMATCH", f"open_counts 不一致：expected={derived}, actual={counts}")
    return counts


def derive_gap_counts(gaps: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {severity: 0 for severity in GAP_SEVERITIES}
    for gap in gaps:
        counts[gap["severity"]] += 1
    return {**counts, "total": sum(counts.values())}


def validate_lineage(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    findings = current["findings"]
    supersedes = current["supersedes_review_id"]
    inherited = [item for item in findings if item["origin"]["review_id"] is not None]
    if previous is None:
        if supersedes is not None or inherited:
            raise ReviewError("REVIEW_LINEAGE_ORIGIN_INVALID", "无前序 receipt 时不得声明 supersedes/origin。")
        return {"predecessor_review_id": None, "accounted_finding_count": 0}
    if supersedes != previous.get("review_id"):
        raise ReviewError("REVIEW_SUPERSEDES_MISMATCH", "supersedes_review_id 与前序不一致。")
    active_previous = {
        item["id"]: item
        for item in previous.get("findings", [])
        if item.get("status") in {"open", "accepted", "deferred"}
    }
    mappings: dict[str, list[dict[str, Any]]] = {}
    for finding in inherited:
        origin = finding["origin"]
        if origin["review_id"] != previous.get("review_id"):
            raise ReviewError("REVIEW_LINEAGE_ORIGIN_INVALID", "origin 必须指向直属前序 receipt。")
        origin_id = str(origin["finding_id"])
        if origin_id not in active_previous:
            raise ReviewError("REVIEW_LINEAGE_ORIGIN_INVALID", "origin 只能映射前序未关闭 finding。")
        mappings.setdefault(origin_id, []).append(finding)
    missing = sorted(set(active_previous) - set(mappings))
    duplicate = sorted(key for key, values in mappings.items() if len(values) != 1)
    if missing or duplicate:
        raise ReviewError(
            "REVIEW_LINEAGE_ACCOUNTING_INCOMPLETE",
            f"missing={missing}, duplicate={duplicate}",
        )
    severity_rank = {"blocking": 3, "major": 2, "minor": 1, "advisory": 0}
    for previous_id, previous_finding in active_previous.items():
        current_finding = mappings[previous_id][0]
        if current_finding["status"] in {"open", "accepted", "deferred"} and (
            severity_rank[current_finding["severity"]]
            < severity_rank[previous_finding["severity"]]
        ):
            raise ReviewError("REVIEW_LINEAGE_SEVERITY_DOWNGRADE", "未关闭 finding 不能无依据降低 severity。")
    return {
        "predecessor_review_id": previous.get("review_id"),
        "accounted_finding_count": len(active_previous),
    }


def expected_verdict(
    lenses: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> str:
    if any(lens["status"] == "blocked" for lens in lenses) or any(
        gap["severity"] in {"blocking", "major"} for gap in gaps
    ):
        return "blocked"
    unresolved_major = any(
        finding["severity"] in {"blocking", "major"}
        and finding["status"] in {"open", "accepted", "deferred"}
        for finding in findings
    )
    return "changes_required" if unresolved_major else "passed"

