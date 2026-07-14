"""静态证据专用闭合契约，保持结构、计数与 hash 自洽。"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .errors import ContractError
from .paths import hash_document


SCHEMA_VERSION = 1
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CHECK_STATUSES = {"pass", "warn", "fail", "not_applicable"}
EXPECTED_CHECK_IDS = {
    "skill.metadata",
    "skill.structure",
    "skill.references",
    "skill.disclosure",
    "skill.syntax",
    "skill.capabilities",
    "skill.validation_assets",
    "skill.baseline_delta",
}
SEVERITY_BY_STATUS = {
    "pass": "info",
    "warn": "advisory",
    "fail": "blocking",
    "not_applicable": "info",
}


def _error(message: str, path: str) -> ContractError:
    return ContractError(message, code="CONTRACT_INVALID", path=path)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("必须是 object", path)
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error("必须是 array", path)
    return value


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise _error("必须是字符串", path)
    return value


def _closed(value: dict[str, Any], path: str, required: set[str]) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise _error(f"缺少字段：{', '.join(missing)}", path)
    if unknown:
        raise _error(f"存在未知字段：{', '.join(unknown)}", path)


def _relative(value: Any, path: str, *, allow_dot: bool = True) -> str:
    text = _string(value, path)
    normalized = text.replace("\\", "/")
    parts = normalized.split("/")
    if (
        Path(text).is_absolute()
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in parts
        or (not allow_dot and normalized == ".")
    ):
        raise _error("必须是无父目录跳转的相对路径", path)
    return text


def _sha256(value: Any, path: str) -> str:
    text = _string(value, path)
    if not SHA256.fullmatch(text):
        raise _error("必须是小写 SHA-256", path)
    return text


def _nonnegative_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _error("必须是非负整数", path)
    return value


def _source_identity(value: Any, path: str) -> dict[str, Any]:
    identity = _object(value, path)
    _closed(identity, path, {"path", "tree_sha256", "file_count", "total_bytes", "files"})
    _relative(identity["path"], f"{path}.path")
    declared_hash = _sha256(identity["tree_sha256"], f"{path}.tree_sha256")
    declared_count = _nonnegative_int(identity["file_count"], f"{path}.file_count")
    declared_total = _nonnegative_int(identity["total_bytes"], f"{path}.total_bytes")

    files = _array(identity["files"], f"{path}.files")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw_file in enumerate(files):
        file_path = f"{path}.files[{index}]"
        item = _object(raw_file, file_path)
        _closed(item, file_path, {"path", "size", "sha256"})
        relative = _relative(item["path"], f"{file_path}.path", allow_dot=False)
        if relative in seen:
            raise _error("source manifest 文件路径重复", f"{file_path}.path")
        seen.add(relative)
        normalized.append(
            {
                "path": relative,
                "size": _nonnegative_int(item["size"], f"{file_path}.size"),
                "sha256": _sha256(item["sha256"], f"{file_path}.sha256"),
            }
        )
    if [item["path"] for item in normalized] != sorted(item["path"] for item in normalized):
        raise _error("source manifest 必须按路径排序", f"{path}.files")
    if declared_count != len(normalized):
        raise _error("file_count 与 manifest 不一致", f"{path}.file_count")
    if declared_total != sum(item["size"] for item in normalized):
        raise _error("total_bytes 与 manifest 不一致", f"{path}.total_bytes")
    if declared_hash != hash_document(normalized):
        raise _error("tree_sha256 与 manifest 不一致", f"{path}.tree_sha256")
    return identity


def _check_items(value: Any) -> list[dict[str, Any]]:
    checks = _array(value, "$.checks")
    seen: set[str] = set()
    for index, raw_check in enumerate(checks):
        path = f"$.checks[{index}]"
        check = _object(raw_check, path)
        _closed(
            check,
            path,
            {"id", "dimension", "status", "severity", "summary", "evidence", "guidance"},
        )
        check_id = _string(check["id"], f"{path}.id")
        if check_id not in EXPECTED_CHECK_IDS or check_id in seen:
            raise _error("static check id 未知或重复", f"{path}.id")
        seen.add(check_id)
        status = _string(check["status"], f"{path}.status")
        if status not in CHECK_STATUSES:
            raise _error("static check status 无效", f"{path}.status")
        if check["severity"] != SEVERITY_BY_STATUS[status]:
            raise _error("severity 与 status 不一致", f"{path}.severity")
        _string(check["dimension"], f"{path}.dimension")
        _string(check["summary"], f"{path}.summary")
        _string(check["guidance"], f"{path}.guidance", allow_empty=True)
        evidence = _array(check["evidence"], f"{path}.evidence")
        if not evidence:
            raise _error("static check 至少需要一条 evidence", f"{path}.evidence")
        for evidence_index, raw_evidence in enumerate(evidence):
            evidence_path = f"{path}.evidence[{evidence_index}]"
            item = _object(raw_evidence, evidence_path)
            _closed(item, evidence_path, {"path", "detail"})
            _relative(item["path"], f"{evidence_path}.path")
            _string(item["detail"], f"{evidence_path}.detail")
    if seen != EXPECTED_CHECK_IDS:
        missing = ", ".join(sorted(EXPECTED_CHECK_IDS - seen))
        raise _error(f"缺少 static check：{missing}", "$.checks")
    return checks


def _capabilities(value: Any) -> None:
    for index, raw_capability in enumerate(_array(value, "$.capabilities")):
        path = f"$.capabilities[{index}]"
        item = _object(raw_capability, path)
        _closed(item, path, {"kind", "path", "line", "detail"})
        _string(item["kind"], f"{path}.kind")
        _relative(item["path"], f"{path}.path", allow_dot=False)
        line = item["line"]
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise _error("line 必须是正整数", f"{path}.line")
        _string(item["detail"], f"{path}.detail")


def _string_array(value: Any, path: str, *, relative: bool = False) -> list[str]:
    items = _array(value, path)
    values = [
        _relative(item, f"{path}[{index}]", allow_dot=False)
        if relative
        else _string(item, f"{path}[{index}]")
        for index, item in enumerate(items)
    ]
    if len(values) != len(set(values)):
        raise _error("数组条目不能重复", path)
    return values


def _delta(value: Any, *, baseline_present: bool) -> None:
    if not baseline_present:
        if value is not None:
            raise _error("未提供 baseline 时 delta 必须为 null", "$.delta")
        return
    delta = _object(value, "$.delta")
    _closed(
        delta,
        "$.delta",
        {
            "added_files",
            "removed_files",
            "changed_files",
            "check_status_changes",
            "capabilities_added",
            "capabilities_removed",
        },
    )
    for field in ("added_files", "removed_files", "changed_files"):
        _string_array(delta[field], f"$.delta.{field}", relative=True)
    for index, raw_change in enumerate(_array(delta["check_status_changes"], "$.delta.check_status_changes")):
        path = f"$.delta.check_status_changes[{index}]"
        change = _object(raw_change, path)
        _closed(change, path, {"id", "baseline", "candidate"})
        if _string(change["id"], f"{path}.id") not in EXPECTED_CHECK_IDS:
            raise _error("delta check id 未知", f"{path}.id")
        for field in ("baseline", "candidate"):
            if change[field] not in CHECK_STATUSES:
                raise _error("delta check status 无效", f"{path}.{field}")
    for field in ("capabilities_added", "capabilities_removed"):
        for index, raw_item in enumerate(_array(delta[field], f"$.delta.{field}")):
            path = f"$.delta.{field}[{index}]"
            item = _array(raw_item, path)
            if len(item) != 3:
                raise _error("capability delta 必须包含 kind、path、detail", path)
            _string(item[0], f"{path}[0]")
            _relative(item[1], f"{path}[1]", allow_dot=False)
            _string(item[2], f"{path}[2]")


def validate_static_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """校验静态证据的完整结构、派生计数和 source identity。"""
    document = _object(value, "$")
    _closed(
        document,
        "$",
        {
            "schema_version",
            "evaluation_id",
            "generated_at",
            "checker",
            "candidate",
            "baseline",
            "checks",
            "capabilities",
            "delta",
            "summary",
        },
    )
    if document["schema_version"] != SCHEMA_VERSION:
        raise _error("schema_version 必须为 1", "$.schema_version")
    evaluation_id = _string(document["evaluation_id"], "$.evaluation_id")
    if not IDENTIFIER.fullmatch(evaluation_id):
        raise _error("evaluation_id 格式无效", "$.evaluation_id")
    _string(document["generated_at"], "$.generated_at")
    checker = _object(document["checker"], "$.checker")
    expected_checker = {
        "name": "skill-evaluation-lab",
        "contract": "deterministic-static-only",
        "agent_calls": 0,
        "network_calls": 0,
        "target_imports": 0,
    }
    _closed(checker, "$.checker", set(expected_checker))
    if checker != expected_checker:
        raise _error("checker 必须声明纯静态零派生调用", "$.checker")

    candidate = _source_identity(document["candidate"], "$.candidate")
    baseline = (
        _source_identity(document["baseline"], "$.baseline")
        if document["baseline"] is not None
        else None
    )
    if baseline is not None and baseline["path"] == candidate["path"]:
        raise _error("baseline 不能与 candidate 相同", "$.baseline.path")
    checks = _check_items(document["checks"])
    _capabilities(document["capabilities"])
    _delta(document["delta"], baseline_present=baseline is not None)

    summary = _object(document["summary"], "$.summary")
    _closed(summary, "$.summary", CHECK_STATUSES)
    counts = Counter(str(item["status"]) for item in checks)
    for status in CHECK_STATUSES:
        actual = _nonnegative_int(summary[status], f"$.summary.{status}")
        if actual != counts.get(status, 0):
            raise _error("summary 与 checks 计数不一致", f"$.summary.{status}")
    baseline_status = next(item["status"] for item in checks if item["id"] == "skill.baseline_delta")
    expected_status = "pass" if baseline is not None else "not_applicable"
    if baseline_status != expected_status:
        raise _error("baseline delta status 与 baseline 不一致", "$.checks")
    return document
