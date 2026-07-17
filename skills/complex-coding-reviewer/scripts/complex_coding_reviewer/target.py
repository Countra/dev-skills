"""构建并重新验证 canonical review target。"""

from __future__ import annotations

import fnmatch
import hashlib
import subprocess
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


TARGET_FIELDS = {
    "kind",
    "identity",
    "digest_algorithm",
    "digest",
    "manifest",
}
MANIFEST_FIELDS = {"path", "role", "state", "sha256", "size"}
TARGET_KINDS = {"plan-bundle", "git-diff", "commit-range", "file-manifest"}


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(path: str, role: str, data: bytes | None) -> dict[str, Any]:
    return {
        "path": normalize_relative_path(path),
        "role": role,
        "state": "present" if data is not None else "deleted",
        "sha256": _digest_bytes(data) if data is not None else None,
        "size": len(data) if data is not None else None,
    }


def _finalize_target(
    kind: str,
    identity: dict[str, Any],
    entries: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    manifest = sorted(entries, key=lambda item: item["path"])
    paths = [item["path"] for item in manifest]
    if len(paths) != len(set(paths)):
        raise ReviewError(
            "REVIEW_TARGET_DUPLICATE_PATH",
            "canonical target 不能包含重复路径。",
        )
    payload = {
        "kind": kind,
        "identity": identity,
        "digest_algorithm": "sha256",
        "manifest": manifest,
    }
    target = {**payload, "digest": _digest_bytes(canonical_json_bytes(payload))}
    validate_target_shape(target)
    return target


def build_plan_bundle_target(task_dir: Path) -> dict[str, Any]:
    root = resolve_root(task_dir, label="task directory")
    contract = load_json_object(root / "plan-contract.json", code="REVIEW_TARGET_CONTRACT_INVALID")
    task_id = contract.get("task_id")
    plan_revision = contract.get("plan_revision")
    if not isinstance(task_id, str) or not task_id:
        raise ReviewError("REVIEW_TARGET_CONTRACT_INVALID", "contract.task_id 必须是非空字符串。")
    if not isinstance(plan_revision, int) or isinstance(plan_revision, bool) or plan_revision < 1:
        raise ReviewError("REVIEW_TARGET_CONTRACT_INVALID", "contract.plan_revision 必须是正整数。")
    specs: list[tuple[str, str]] = [
        ("execution-plan.md", "plan"),
        ("plan-contract.json", "contract"),
    ]
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReviewError("REVIEW_TARGET_CONTRACT_INVALID", "contract.artifacts 必须是数组。")
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ReviewError(
                "REVIEW_TARGET_CONTRACT_INVALID",
                "artifact 必须是 object。",
                path=f"$.artifacts[{index}]",
            )
        if artifact.get("kind") == "review":
            continue
        if artifact.get("required") is not True and artifact.get("approval_included") is not True:
            continue
        path = artifact.get("path")
        kind = artifact.get("kind")
        if not isinstance(path, str) or not isinstance(kind, str) or not kind:
            raise ReviewError(
                "REVIEW_TARGET_CONTRACT_INVALID",
                "被纳入审批的 artifact 必须声明 path 与 kind。",
                path=f"$.artifacts[{index}]",
            )
        specs.append((path, f"artifact:{kind}"))
    entries = []
    for relative, role in specs:
        path = resolve_relative_file(root, relative)
        entries.append(_entry(relative, role, read_bytes(path, display_path=relative)))
    return _finalize_target(
        "plan-bundle",
        {"task_id": task_id, "plan_revision": plan_revision},
        entries,
    )


def build_file_manifest_target(
    workspace: Path,
    files: Iterable[str],
    *,
    label: str = "standalone",
    roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = resolve_root(workspace, label="workspace")
    normalized = sorted({normalize_relative_path(item) for item in files})
    if not normalized:
        raise ReviewError("REVIEW_TARGET_EMPTY", "file-manifest 至少需要一个目标文件。")
    role_map = {normalize_relative_path(key): value for key, value in (roles or {}).items()}
    entries = []
    for relative in normalized:
        role = role_map.get(relative, "source")
        if not isinstance(role, str) or not role.strip():
            raise ReviewError("REVIEW_TARGET_ROLE_INVALID", "manifest role 必须是非空字符串。", path=relative)
        path = resolve_relative_file(root, relative)
        entries.append(_entry(relative, role, read_bytes(path, display_path=relative)))
    return _finalize_target("file-manifest", {"label": label}, entries)


def _run_git(repository: Path, arguments: list[str], *, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ReviewError("REVIEW_TARGET_GIT_UNAVAILABLE", f"无法启动 git：{exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ReviewError(
            "REVIEW_TARGET_GIT_FAILED",
            f"git {' '.join(arguments)} 失败：{stderr}",
        )
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def _repository_root(repository: Path) -> Path:
    root = resolve_root(repository, label="repository")
    value = _run_git(root, ["rev-parse", "--show-toplevel"])
    assert isinstance(value, str)
    return resolve_root(Path(value), label="git repository")


def _commit(repository: Path, revision: str) -> str:
    value = _run_git(repository, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
    assert isinstance(value, str)
    return value


def _parse_name_status(data: bytes) -> list[tuple[str, str]]:
    tokens = [item for item in data.decode("utf-8", errors="surrogateescape").split("\0") if item]
    if len(tokens) % 2:
        raise ReviewError("REVIEW_TARGET_GIT_OUTPUT_INVALID", "git name-status 输出无法成对解析。")
    pairs = []
    for index in range(0, len(tokens), 2):
        status = tokens[index]
        path = normalize_relative_path(tokens[index + 1])
        if status[:1] not in {"A", "C", "D", "M", "R", "T", "U", "X", "B"}:
            raise ReviewError("REVIEW_TARGET_GIT_OUTPUT_INVALID", f"未知 git status：{status}")
        pairs.append((status[:1], path))
    return pairs


def _selected(path: str, paths: tuple[str, ...], excludes: tuple[str, ...]) -> bool:
    if paths and not any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in paths):
        return False
    return not any(fnmatch.fnmatchcase(path, pattern) for pattern in excludes)


def _selection(paths: Iterable[str], excludes: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized_paths = tuple(sorted({normalize_relative_path(item) for item in paths}))
    normalized_excludes = tuple(sorted({item.replace("\\", "/") for item in excludes if item}))
    return normalized_paths, normalized_excludes


def _git_identity(
    *,
    mode: str,
    baseline: str,
    head: str,
    paths: tuple[str, ...],
    excludes: tuple[str, ...],
    stage_id: str | None,
    attempt: int | None,
) -> dict[str, Any]:
    return {
        "repository": ".",
        "mode": mode,
        "baseline": baseline,
        "head": head,
        "paths": list(paths),
        "excludes": list(excludes),
        "stage_id": stage_id,
        "attempt": attempt,
    }


def build_working_tree_target(
    repository: Path,
    *,
    baseline: str = "HEAD",
    paths: Iterable[str] = (),
    excludes: Iterable[str] = (),
    stage_id: str | None = None,
    attempt: int | None = None,
) -> dict[str, Any]:
    root = _repository_root(repository)
    baseline_commit = _commit(root, baseline)
    head_commit = _commit(root, "HEAD")
    selected_paths, selected_excludes = _selection(paths, excludes)
    diff = _run_git(
        root,
        ["diff", "--name-status", "-z", "--no-renames", baseline_commit, "--", *selected_paths],
        binary=True,
    )
    untracked = _run_git(
        root,
        ["ls-files", "--others", "--exclude-standard", "-z", "--", *selected_paths],
        binary=True,
    )
    assert isinstance(diff, bytes) and isinstance(untracked, bytes)
    states = {path: status for status, path in _parse_name_status(diff)}
    for raw in untracked.decode("utf-8", errors="surrogateescape").split("\0"):
        if raw:
            states[normalize_relative_path(raw)] = "A"
    entries = []
    for relative, status in sorted(states.items()):
        if not _selected(relative, selected_paths, selected_excludes):
            continue
        if status == "D":
            entries.append(_entry(relative, "source", None))
            continue
        path = resolve_relative_file(root, relative)
        entries.append(_entry(relative, "source", read_bytes(path, display_path=relative)))
    return _finalize_target(
        "git-diff",
        _git_identity(
            mode="working-tree",
            baseline=baseline_commit,
            head=head_commit,
            paths=selected_paths,
            excludes=selected_excludes,
            stage_id=stage_id,
            attempt=attempt,
        ),
        entries,
    )


def build_commit_range_target(
    repository: Path,
    *,
    baseline: str,
    head: str,
    paths: Iterable[str] = (),
    excludes: Iterable[str] = (),
) -> dict[str, Any]:
    root = _repository_root(repository)
    baseline_commit = _commit(root, baseline)
    head_commit = _commit(root, head)
    selected_paths, selected_excludes = _selection(paths, excludes)
    diff = _run_git(
        root,
        ["diff", "--name-status", "-z", "--no-renames", baseline_commit, head_commit, "--", *selected_paths],
        binary=True,
    )
    assert isinstance(diff, bytes)
    entries = []
    for status, relative in _parse_name_status(diff):
        if not _selected(relative, selected_paths, selected_excludes):
            continue
        if status == "D":
            entries.append(_entry(relative, "source", None))
            continue
        data = _run_git(root, ["show", f"{head_commit}:{relative}"], binary=True)
        assert isinstance(data, bytes)
        entries.append(_entry(relative, "source", data))
    return _finalize_target(
        "commit-range",
        _git_identity(
            mode="commit-range",
            baseline=baseline_commit,
            head=head_commit,
            paths=selected_paths,
            excludes=selected_excludes,
            stage_id=None,
            attempt=None,
        ),
        entries,
    )


def _closed_object(value: Any, expected: set[str], *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError("REVIEW_CONTRACT_TYPE_INVALID", "值必须是 object。", path=path)
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown or missing:
        detail = f"unknown={unknown}, missing={missing}"
        raise ReviewError("REVIEW_CONTRACT_FIELDS_INVALID", detail, path=path)
    return value


def _validate_identity(kind: str, raw: Any) -> dict[str, Any]:
    if kind == "plan-bundle":
        identity = _closed_object(raw, {"task_id", "plan_revision"}, path="$.target.identity")
        if not isinstance(identity["task_id"], str) or not identity["task_id"]:
            raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "plan target 需要 task_id。")
        revision = identity["plan_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "plan_revision 必须是正整数。")
        return identity
    if kind == "file-manifest":
        identity = _closed_object(raw, {"label"}, path="$.target.identity")
        if not isinstance(identity["label"], str) or not identity["label"].strip():
            raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "file target 需要非空 label。")
        return identity
    identity = _closed_object(
        raw,
        {"repository", "mode", "baseline", "head", "paths", "excludes", "stage_id", "attempt"},
        path="$.target.identity",
    )
    expected_mode = "working-tree" if kind == "git-diff" else "commit-range"
    if identity["repository"] != "." or identity["mode"] != expected_mode:
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "Git target repository/mode 非 canonical。")
    for field in ("baseline", "head"):
        revision = identity[field]
        if not isinstance(revision, str) or len(revision) not in {40, 64} or any(
            char not in "0123456789abcdef" for char in revision
        ):
            raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", f"{field} 必须是完整 Git object id。")
    paths = identity["paths"]
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "identity.paths 必须是字符串数组。")
    normalized_paths = [normalize_relative_path(item) for item in paths]
    if paths != sorted(set(normalized_paths)):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "identity.paths 必须 canonicalize、排序且去重。")
    excludes = identity["excludes"]
    if not isinstance(excludes, list) or not all(isinstance(item, str) and item for item in excludes):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "identity.excludes 必须是非空字符串数组。")
    if excludes != sorted(set(item.replace("\\", "/") for item in excludes)):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "identity.excludes 必须 canonicalize、排序且去重。")
    stage_id = identity["stage_id"]
    attempt = identity["attempt"]
    if (stage_id is None) != (attempt is None):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "stage_id 与 attempt 必须同时出现或同时为 null。")
    if stage_id is not None and (not isinstance(stage_id, str) or not stage_id):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "stage_id 必须是非空字符串。")
    if attempt is not None and (
        not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1
    ):
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "attempt 必须是正整数。")
    if kind == "commit-range" and stage_id is not None:
        raise ReviewError("REVIEW_TARGET_IDENTITY_INVALID", "commit-range 不携带 stage attempt。")
    return identity


def validate_target_shape(target: Any) -> dict[str, Any]:
    value = _closed_object(target, TARGET_FIELDS, path="$.target")
    if value["kind"] not in TARGET_KINDS:
        raise ReviewError("REVIEW_TARGET_KIND_INVALID", "未知 target kind。", path="$.target.kind")
    if value["digest_algorithm"] != "sha256":
        raise ReviewError("REVIEW_TARGET_DIGEST_INVALID", "digest_algorithm 必须是 sha256。")
    digest = value["digest"]
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ReviewError("REVIEW_TARGET_DIGEST_INVALID", "digest 必须是小写 64 位 SHA-256。")
    _validate_identity(value["kind"], value["identity"])
    manifest = value["manifest"]
    if not isinstance(manifest, list):
        raise ReviewError("REVIEW_TARGET_MANIFEST_INVALID", "target.manifest 必须是数组。")
    paths = []
    for index, raw in enumerate(manifest):
        item = _closed_object(raw, MANIFEST_FIELDS, path=f"$.target.manifest[{index}]")
        path = normalize_relative_path(item["path"]) if isinstance(item["path"], str) else ""
        if path != item["path"]:
            raise ReviewError("REVIEW_TARGET_PATH_INVALID", "manifest path 必须已 canonicalize。", path=path)
        if not isinstance(item["role"], str) or not item["role"]:
            raise ReviewError("REVIEW_TARGET_ROLE_INVALID", "manifest role 必须是非空字符串。", path=path)
        if item["state"] == "present":
            if (
                not isinstance(item["sha256"], str)
                or len(item["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in item["sha256"])
            ):
                raise ReviewError("REVIEW_TARGET_DIGEST_INVALID", "present entry 需要 SHA-256。", path=path)
            if not isinstance(item["size"], int) or isinstance(item["size"], bool) or item["size"] < 0:
                raise ReviewError("REVIEW_TARGET_SIZE_INVALID", "present entry 需要非负 size。", path=path)
        elif item["state"] == "deleted":
            if item["sha256"] is not None or item["size"] is not None:
                raise ReviewError("REVIEW_TARGET_DELETION_INVALID", "deleted entry 的 hash 与 size 必须为 null。", path=path)
        else:
            raise ReviewError("REVIEW_TARGET_STATE_INVALID", "manifest state 必须是 present 或 deleted。", path=path)
        paths.append(path)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ReviewError("REVIEW_TARGET_ORDER_INVALID", "manifest 必须按路径排序且无重复。")
    payload = {key: value[key] for key in ("kind", "identity", "digest_algorithm", "manifest")}
    actual = _digest_bytes(canonical_json_bytes(payload))
    if actual != digest:
        raise ReviewError("REVIEW_TARGET_DIGEST_INVALID", "target digest 与 canonical payload 不一致。")
    return value


def verify_target_freshness(
    target: dict[str, Any],
    *,
    workspace: Path | None = None,
    task_dir: Path | None = None,
) -> dict[str, Any]:
    value = validate_target_shape(target)
    kind = value["kind"]
    identity = value["identity"]
    if kind == "plan-bundle":
        if task_dir is None:
            raise ReviewError("REVIEW_TARGET_CONTEXT_MISSING", "plan-bundle freshness 需要 --task-dir。")
        rebuilt = build_plan_bundle_target(task_dir)
    elif kind == "file-manifest":
        if workspace is None:
            raise ReviewError("REVIEW_TARGET_CONTEXT_MISSING", "file-manifest freshness 需要 --workspace。")
        roles = {item["path"]: item["role"] for item in value["manifest"]}
        rebuilt = build_file_manifest_target(
            workspace,
            [item["path"] for item in value["manifest"]],
            label=identity.get("label", "standalone"),
            roles=roles,
        )
    elif kind == "git-diff":
        if workspace is None:
            raise ReviewError("REVIEW_TARGET_CONTEXT_MISSING", "git-diff freshness 需要 --workspace。")
        rebuilt = build_working_tree_target(
            workspace,
            baseline=identity.get("baseline", ""),
            paths=identity.get("paths", []),
            excludes=identity.get("excludes", []),
            stage_id=identity.get("stage_id"),
            attempt=identity.get("attempt"),
        )
    else:
        if workspace is None:
            raise ReviewError("REVIEW_TARGET_CONTEXT_MISSING", "commit-range freshness 需要 --workspace。")
        rebuilt = build_commit_range_target(
            workspace,
            baseline=identity.get("baseline", ""),
            head=identity.get("head", ""),
            paths=identity.get("paths", []),
            excludes=identity.get("excludes", []),
        )
    if rebuilt["digest"] != value["digest"]:
        raise ReviewError(
            "REVIEW_TARGET_STALE",
            "当前目标与 receipt 中的 target digest 不一致。",
        )
    return rebuilt
