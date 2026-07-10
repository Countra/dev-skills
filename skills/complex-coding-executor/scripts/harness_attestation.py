#!/usr/bin/env python3
"""构建和校验不可变批准集合的 attestation。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_state_io import write_json_atomic
from harness_state_schema import StateError
from harness_task_bundle import TaskBundle
from harness_time import parse_rfc3339


ATTESTATION_FIELDS = {
    "task_id",
    "plan_revision",
    "approved_at",
    "approved_by",
    "approval_summary",
    "authorizations",
    "immutable_files",
}

AUTHORIZATION_FIELDS = {
    "implementation",
    "commit",
    "external_write",
    "elevated_tool",
}

IMMUTABLE_FILE_FIELDS = {"path", "sha256", "size_bytes"}


class AttestationError(Exception):
    """批准证明缺失、无效或与不可变集合不一致。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AttestationError(
            "ATTESTATION_FILE_UNREADABLE",
            f"无法读取批准文件：{path}: {exc}",
        ) from exc
    return digest.hexdigest()


def immutable_paths(bundle: TaskBundle) -> list[Path]:
    paths = [bundle.plan_path, bundle.contract_path]
    artifacts = bundle.contract.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise AttestationError(
            "ATTESTATION_CONTRACT_INVALID",
            "contract.artifacts 必须是数组。",
        )
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise AttestationError(
                "ATTESTATION_CONTRACT_INVALID",
                f"contract.artifacts[{index}] 必须是 object。",
            )
        if artifact.get("approval_included") is not True:
            continue
        raw_path = artifact.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise AttestationError(
                "ATTESTATION_CONTRACT_INVALID",
                f"contract.artifacts[{index}].path 无效。",
            )
        candidate = (bundle.task_dir / raw_path).resolve()
        try:
            candidate.relative_to(bundle.task_dir)
        except ValueError as exc:
            raise AttestationError(
                "ATTESTATION_PATH_UNSAFE",
                f"批准文件越出 task-dir：{raw_path}",
            ) from exc
        paths.append(candidate)
    unique = {path.resolve() for path in paths}
    if len(unique) != len(paths):
        raise AttestationError(
            "ATTESTATION_DUPLICATE_PATH",
            "不可变批准集合包含重复路径。",
        )
    return sorted(unique, key=lambda path: path.as_posix())


def immutable_manifest(bundle: TaskBundle) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for path in immutable_paths(bundle):
        if not path.is_file():
            raise AttestationError(
                "ATTESTATION_FILE_MISSING",
                f"批准文件不存在：{path}",
            )
        manifest.append(
            {
                "path": path.relative_to(bundle.task_dir).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": file_size(path),
            }
        )
    return manifest


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError as exc:
        raise AttestationError(
            "ATTESTATION_FILE_UNREADABLE",
            f"无法读取批准文件大小：{path}: {exc}",
        ) from exc


def build_attestation(
    bundle: TaskBundle,
    *,
    approved_by: str,
    approval_summary: str,
    commit_authorized: bool = False,
    external_write_authorized: bool = False,
    elevated_tool_authorized: bool = False,
    approved_at: str | None = None,
) -> dict[str, Any]:
    if not approved_by.strip() or not approval_summary.strip():
        raise AttestationError(
            "ATTESTATION_APPROVAL_INVALID",
            "approved_by 和 approval_summary 必须是非空字符串。",
        )
    return {
        "task_id": bundle.task_id,
        "plan_revision": bundle.plan_revision,
        "approved_at": approved_at or datetime.now(timezone.utc).isoformat(),
        "approved_by": approved_by,
        "approval_summary": approval_summary,
        "authorizations": {
            "implementation": True,
            "commit": commit_authorized,
            "external_write": external_write_authorized,
            "elevated_tool": elevated_tool_authorized,
        },
        "immutable_files": immutable_manifest(bundle),
    }


def load_attestation(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AttestationError(
            "ATTESTATION_MISSING",
            f"批准证明不存在：{path}",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AttestationError(
            "ATTESTATION_INVALID_JSON",
            f"无法解析批准证明：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise AttestationError(
            "ATTESTATION_INVALID_TYPE",
            "attestation 根节点必须是 object。",
        )
    return value


def validate_closed_fields(
    value: Any,
    allowed: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AttestationError(
            "ATTESTATION_INVALID_TYPE",
            f"{label} 必须是 object。",
        )
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if unknown:
        raise AttestationError(
            "ATTESTATION_UNKNOWN_FIELD",
            f"{label} 包含未知字段：{', '.join(unknown)}",
        )
    if missing:
        raise AttestationError(
            "ATTESTATION_MISSING_FIELD",
            f"{label} 缺少字段：{', '.join(missing)}",
        )
    return value


def validate_attestation(
    bundle: TaskBundle,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attestation = (
        payload
        if payload is not None
        else load_attestation(bundle.attestation_path)
    )
    validate_closed_fields(attestation, ATTESTATION_FIELDS, "attestation")
    if attestation.get("task_id") != bundle.task_id:
        raise AttestationError(
            "ATTESTATION_TASK_MISMATCH",
            "attestation.task_id 与 contract 不一致。",
        )
    if attestation.get("plan_revision") != bundle.plan_revision:
        raise AttestationError(
            "ATTESTATION_REVISION_MISMATCH",
            "attestation.plan_revision 与 contract 不一致。",
        )
    for field in ("approved_at", "approved_by", "approval_summary"):
        if (
            not isinstance(attestation.get(field), str)
            or not attestation[field].strip()
        ):
            raise AttestationError(
                "ATTESTATION_APPROVAL_INVALID",
                f"attestation.{field} 必须是非空字符串。",
            )
    try:
        parse_rfc3339(attestation["approved_at"])
    except ValueError as exc:
        raise AttestationError(
            "ATTESTATION_APPROVAL_INVALID",
            "attestation.approved_at 必须是 RFC3339 时间。",
        ) from exc
    authorizations = validate_closed_fields(
        attestation.get("authorizations"),
        AUTHORIZATION_FIELDS,
        "attestation.authorizations",
    )
    for field in AUTHORIZATION_FIELDS:
        if not isinstance(authorizations.get(field), bool):
            raise AttestationError(
                "ATTESTATION_AUTHORIZATION_INVALID",
                f"authorizations.{field} 必须是 boolean。",
            )
    if authorizations["implementation"] is not True:
        raise AttestationError(
            "ATTESTATION_IMPLEMENTATION_DENIED",
            "用户尚未授权 implementation。",
        )

    files = attestation.get("immutable_files")
    if not isinstance(files, list):
        raise AttestationError(
            "ATTESTATION_INVALID_TYPE",
            "attestation.immutable_files 必须是数组。",
        )
    recorded: list[dict[str, Any]] = []
    for index, item in enumerate(files):
        recorded.append(
            validate_closed_fields(
                item,
                IMMUTABLE_FILE_FIELDS,
                f"attestation.immutable_files[{index}]",
            )
        )
    expected = immutable_manifest(bundle)
    if recorded != expected:
        raise AttestationError(
            "ATTESTATION_HASH_MISMATCH",
            "不可变文件集合、大小或 SHA-256 与批准证明不一致。",
        )
    return attestation


def write_attestation(path: Path, payload: dict[str, Any]) -> None:
    validate_closed_fields(payload, ATTESTATION_FIELDS, "attestation")
    try:
        write_json_atomic(
            path,
            payload,
            error_code="ATTESTATION_WRITE_FAILED",
            label="attestation",
        )
    except StateError as exc:
        raise AttestationError(exc.code, exc.message) from exc
