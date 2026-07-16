"""构建并校验审查 brief 与独立 context snapshot。"""

from __future__ import annotations

import fnmatch
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .errors import ReviewError
from .io import (
    canonical_json_bytes,
    load_json_object,
    normalize_relative_path,
    read_bytes,
    resolve_relative_file,
    resolve_root,
)


BRIEF_FIELDS = {
    "profile",
    "scope",
    "summary",
    "requirement_refs",
    "constraint_refs",
    "claim_refs",
    "requested_risk_focus",
    "created_at",
}
CONTEXT_FIELDS = {"kind", "identity", "digest_algorithm", "digest", "manifest"}
CONTEXT_IDENTITY_FIELDS = {"root", "label"}
CONTEXT_ENTRY_FIELDS = {"path", "role", "state", "sha256", "size"}
CONTEXT_ROLES = {
    "brief",
    "requirement",
    "standard",
    "validation",
    "adjacent-code",
    "config",
    "test",
    "other",
}
ROOT_KINDS = {"workspace", "task-dir"}
RISK_IDS = (
    "security-privacy",
    "concurrency-integrity",
    "performance-resources",
    "api-data-compatibility",
    "ui-accessibility-i18n",
    "removal-dependencies",
)
MAX_CONTEXT_FILES = 128
MAX_CONTEXT_FILE_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_TOTAL_BYTES = 8 * 1024 * 1024
SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.key",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
)


def _closed(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_CONTEXT_TYPE_INVALID", "值必须是 object。", path=path)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown or missing:
        raise ReviewError(
            "REVIEW_CONTEXT_FIELDS_INVALID",
            f"unknown={unknown}, missing={missing}",
            path=path,
        )
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewError("REVIEW_CONTEXT_VALUE_INVALID", "值必须是非空字符串。", path=path)
    return value


def _string_list(
    value: Any,
    path: str,
    *,
    allow_empty: bool = True,
    ordered: bool = True,
) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ReviewError("REVIEW_CONTEXT_TYPE_INVALID", "值必须是非空字符串数组。", path=path)
    if not allow_empty and not value:
        raise ReviewError("REVIEW_CONTEXT_VALUE_INVALID", "数组不能为空。", path=path)
    if len(value) != len(set(value)) or (ordered and value != sorted(value)):
        raise ReviewError(
            "REVIEW_CONTEXT_ORDER_INVALID",
            "字符串数组必须排序且去重。",
            path=path,
        )
    return value


def _validate_scope(profile: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_CONTEXT_SCOPE_INVALID", "brief.scope 必须是 object。")
    kind = value.get("kind")
    if profile == "plan-review":
        scope = _closed(value, {"kind", "task_id", "plan_revision"}, "$.brief.scope")
        if kind != "managed-plan":
            raise ReviewError("REVIEW_CONTEXT_SCOPE_INVALID", "plan-review brief 必须是 managed-plan。")
        _nonempty(scope["task_id"], "$.brief.scope.task_id")
        revision = scope["plan_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ReviewError("REVIEW_CONTEXT_SCOPE_INVALID", "plan_revision 必须是正整数。")
        return scope
    if kind == "stage-delta":
        scope = _closed(value, {"kind", "stage_id", "attempt"}, "$.brief.scope")
        _nonempty(scope["stage_id"], "$.brief.scope.stage_id")
        attempt = scope["attempt"]
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ReviewError("REVIEW_CONTEXT_SCOPE_INVALID", "attempt 必须是正整数。")
        return scope
    if kind in {"final-integration", "standalone"}:
        return _closed(value, {"kind"}, "$.brief.scope")
    raise ReviewError("REVIEW_CONTEXT_SCOPE_INVALID", "code-review brief scope 无效。")


def validate_review_brief(value: Any) -> dict[str, Any]:
    brief = _closed(value, BRIEF_FIELDS, "$.brief")
    profile = brief["profile"]
    if profile not in {"plan-review", "code-review"}:
        raise ReviewError("REVIEW_CONTEXT_PROFILE_INVALID", "brief.profile 无效。")
    scope = _validate_scope(profile, brief["scope"])
    _nonempty(brief["summary"], "$.brief.summary")
    requirements = _string_list(
        brief["requirement_refs"],
        "$.brief.requirement_refs",
        allow_empty=False,
    )
    constraints = _string_list(brief["constraint_refs"], "$.brief.constraint_refs")
    claims = _string_list(brief["claim_refs"], "$.brief.claim_refs")
    for index, claim in enumerate(claims):
        normalized = normalize_relative_path(claim)
        if claim != normalized:
            raise ReviewError(
                "REVIEW_CONTEXT_PATH_INVALID",
                "claim_refs 必须使用 canonical 相对路径。",
                path=f"$.brief.claim_refs[{index}]",
            )
    risks = _string_list(
        brief["requested_risk_focus"],
        "$.brief.requested_risk_focus",
        ordered=False,
    )
    unknown_risks = sorted(set(risks) - set(RISK_IDS))
    if unknown_risks:
        raise ReviewError(
            "REVIEW_CONTEXT_RISK_INVALID",
            f"未知 requested risk：{', '.join(unknown_risks)}",
        )
    expected_risk_order = [item for item in RISK_IDS if item in risks]
    if risks != expected_risk_order:
        raise ReviewError("REVIEW_CONTEXT_ORDER_INVALID", "requested_risk_focus 顺序无效。")
    created_at = _nonempty(brief["created_at"], "$.brief.created_at")
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewError("REVIEW_CONTEXT_TIMESTAMP_INVALID", "created_at 必须是 RFC3339。") from exc
    if parsed.tzinfo is None:
        raise ReviewError("REVIEW_CONTEXT_TIMESTAMP_INVALID", "created_at 必须包含时区。")
    return {
        **brief,
        "scope": scope,
        "requirement_refs": requirements,
        "constraint_refs": constraints,
        "claim_refs": claims,
        "requested_risk_focus": risks,
    }


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sensitive_path(path: str) -> bool:
    name = Path(path).name.lower()
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in SENSITIVE_PATTERNS)


def _entry(path: str, role: str, data: bytes | None) -> dict[str, Any]:
    normalized = normalize_relative_path(path)
    if role not in CONTEXT_ROLES:
        raise ReviewError("REVIEW_CONTEXT_ROLE_INVALID", f"未知 context role：{role}", path=path)
    if _sensitive_path(normalized):
        raise ReviewError("REVIEW_CONTEXT_SECRET_PATH", "敏感文件不能进入 context snapshot。", path=path)
    return {
        "path": normalized,
        "role": role,
        "state": "present" if data is not None else "deleted",
        "sha256": _digest(data) if data is not None else None,
        "size": len(data) if data is not None else None,
    }


def _finalize(root_kind: str, label: str, entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    if root_kind not in ROOT_KINDS:
        raise ReviewError("REVIEW_CONTEXT_ROOT_INVALID", "context root 必须是 workspace 或 task-dir。")
    _nonempty(label, "$.context.identity.label")
    manifest = sorted(entries, key=lambda item: item["path"])
    paths = [item["path"] for item in manifest]
    if not manifest:
        raise ReviewError("REVIEW_CONTEXT_EMPTY", "context 至少需要一个文件。")
    if len(paths) != len(set(paths)):
        raise ReviewError("REVIEW_CONTEXT_DUPLICATE_PATH", "context 不能包含重复路径。")
    present = [item for item in manifest if item["state"] == "present"]
    if len(present) > MAX_CONTEXT_FILES:
        raise ReviewError("REVIEW_CONTEXT_LIMIT_EXCEEDED", "context 文件数超过上限。")
    if any(int(item["size"]) > MAX_CONTEXT_FILE_BYTES for item in present):
        raise ReviewError("REVIEW_CONTEXT_LIMIT_EXCEEDED", "context 单文件超过上限。")
    if sum(int(item["size"]) for item in present) > MAX_CONTEXT_TOTAL_BYTES:
        raise ReviewError("REVIEW_CONTEXT_LIMIT_EXCEEDED", "context 总字节超过上限。")
    payload = {
        "kind": "review-context",
        "identity": {"root": root_kind, "label": label},
        "digest_algorithm": "sha256",
        "manifest": manifest,
    }
    result = {**payload, "digest": _digest(canonical_json_bytes(payload))}
    validate_context_target_shape(result)
    return result


def build_context_target(
    root: Path,
    *,
    root_kind: str,
    label: str,
    entries: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    canonical_root = resolve_root(root, label="context root")
    records = []
    for relative, role in entries:
        normalized = normalize_relative_path(relative)
        path = resolve_relative_file(canonical_root, normalized)
        data = read_bytes(path, display_path=normalized)
        records.append(_entry(normalized, role, data))
    return _finalize(root_kind, label, records)


def validate_context_target_shape(value: Any) -> dict[str, Any]:
    context = _closed(value, CONTEXT_FIELDS, "$.context")
    if context["kind"] != "review-context":
        raise ReviewError("REVIEW_CONTEXT_KIND_INVALID", "context.kind 必须是 review-context。")
    identity = _closed(context["identity"], CONTEXT_IDENTITY_FIELDS, "$.context.identity")
    if identity["root"] not in ROOT_KINDS:
        raise ReviewError("REVIEW_CONTEXT_ROOT_INVALID", "context identity root 无效。")
    _nonempty(identity["label"], "$.context.identity.label")
    if context["digest_algorithm"] != "sha256":
        raise ReviewError("REVIEW_CONTEXT_DIGEST_INVALID", "context digest_algorithm 必须是 sha256。")
    digest = context["digest"]
    if not isinstance(digest, str) or len(digest) != 64 or any(
        item not in "0123456789abcdef" for item in digest
    ):
        raise ReviewError("REVIEW_CONTEXT_DIGEST_INVALID", "context digest 必须是小写 SHA-256。")
    manifest = context["manifest"]
    if not isinstance(manifest, list) or not manifest:
        raise ReviewError("REVIEW_CONTEXT_EMPTY", "context manifest 不能为空。")
    paths = []
    present_count = 0
    total_size = 0
    brief_count = 0
    for index, raw in enumerate(manifest):
        path = f"$.context.manifest[{index}]"
        item = _closed(raw, CONTEXT_ENTRY_FIELDS, path)
        normalized = normalize_relative_path(item["path"])
        if normalized != item["path"]:
            raise ReviewError("REVIEW_CONTEXT_PATH_INVALID", "context path 未 canonicalize。", path=path)
        if _sensitive_path(normalized):
            raise ReviewError("REVIEW_CONTEXT_SECRET_PATH", "敏感文件不能进入 context snapshot。", path=normalized)
        if item["role"] not in CONTEXT_ROLES:
            raise ReviewError("REVIEW_CONTEXT_ROLE_INVALID", "context role 无效。", path=path)
        if item["role"] == "brief":
            brief_count += 1
        if item["state"] == "present":
            sha = item["sha256"]
            size = item["size"]
            if not isinstance(sha, str) or len(sha) != 64 or any(
                char not in "0123456789abcdef" for char in sha
            ):
                raise ReviewError("REVIEW_CONTEXT_DIGEST_INVALID", "present context entry 需要 SHA-256。")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ReviewError("REVIEW_CONTEXT_SIZE_INVALID", "present context entry 需要非负 size。")
            present_count += 1
            total_size += size
        elif item["state"] == "deleted":
            if item["sha256"] is not None or item["size"] is not None:
                raise ReviewError("REVIEW_CONTEXT_DELETION_INVALID", "deleted entry 的 hash/size 必须为 null。")
        else:
            raise ReviewError("REVIEW_CONTEXT_STATE_INVALID", "context state 无效。")
        paths.append(normalized)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ReviewError("REVIEW_CONTEXT_ORDER_INVALID", "context manifest 必须排序且去重。")
    if brief_count != 1:
        raise ReviewError("REVIEW_CONTEXT_BRIEF_INVALID", "context 必须包含且只包含一个 brief。")
    if (
        present_count > MAX_CONTEXT_FILES
        or total_size > MAX_CONTEXT_TOTAL_BYTES
        or any(
            item["state"] == "present" and int(item["size"]) > MAX_CONTEXT_FILE_BYTES
            for item in manifest
        )
    ):
        raise ReviewError("REVIEW_CONTEXT_LIMIT_EXCEEDED", "context 超过有界预算。")
    payload = {key: context[key] for key in ("kind", "identity", "digest_algorithm", "manifest")}
    if _digest(canonical_json_bytes(payload)) != digest:
        raise ReviewError("REVIEW_CONTEXT_DIGEST_INVALID", "context digest 与 canonical payload 不一致。")
    return context


def _context_root(
    context: dict[str, Any],
    *,
    workspace: Path | None,
    task_dir: Path | None,
) -> Path:
    root_kind = context["identity"]["root"]
    root = workspace if root_kind == "workspace" else task_dir
    if root is None:
        raise ReviewError(
            "REVIEW_CONTEXT_ROOT_MISSING",
            f"context freshness 需要 --{root_kind}。",
        )
    return resolve_root(root, label=f"context {root_kind}")


def verify_context_freshness(
    context: dict[str, Any],
    *,
    workspace: Path | None = None,
    task_dir: Path | None = None,
) -> dict[str, Any]:
    value = validate_context_target_shape(context)
    root = _context_root(value, workspace=workspace, task_dir=task_dir)
    records = []
    for item in value["manifest"]:
        path = resolve_relative_file(root, item["path"], must_exist=False)
        if item["state"] == "deleted":
            if path.exists() or path.is_symlink():
                raise ReviewError("REVIEW_CONTEXT_STALE", "声明删除的 context 文件当前存在。", path=item["path"])
            records.append(_entry(item["path"], item["role"], None))
            continue
        existing = resolve_relative_file(root, item["path"])
        records.append(_entry(item["path"], item["role"], read_bytes(existing, display_path=item["path"])))
    rebuilt = _finalize(value["identity"]["root"], value["identity"]["label"], records)
    if rebuilt["digest"] != value["digest"]:
        raise ReviewError("REVIEW_CONTEXT_STALE", "当前 context 与 receipt digest 不一致。")
    return rebuilt


def load_context_brief(
    context: dict[str, Any],
    *,
    workspace: Path | None = None,
    task_dir: Path | None = None,
) -> dict[str, Any]:
    value = validate_context_target_shape(context)
    root = _context_root(value, workspace=workspace, task_dir=task_dir)
    brief_entry = next(item for item in value["manifest"] if item["role"] == "brief")
    if brief_entry["state"] != "present":
        raise ReviewError("REVIEW_CONTEXT_BRIEF_INVALID", "brief 必须是 present 文件。")
    brief_path = resolve_relative_file(root, brief_entry["path"])
    brief = validate_review_brief(
        load_json_object(brief_path, code="REVIEW_CONTEXT_BRIEF_INVALID")
    )
    present_context_paths = {
        item["path"] for item in value["manifest"] if item["state"] == "present"
    }
    missing_claims = sorted(set(brief["claim_refs"]) - present_context_paths)
    if missing_claims:
        raise ReviewError(
            "REVIEW_CONTEXT_CLAIM_UNBOUND",
            "brief.claim_refs 未进入 context manifest：" + ", ".join(missing_claims),
        )
    return brief
