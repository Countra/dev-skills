#!/usr/bin/env python3
"""归档上一 plan revision，并激活获批 amendment。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_attestation import (
    AttestationError,
    sha256_file,
    validate_attestation,
)
from harness_event_writer import EventWriteError, append_event_and_update
from harness_state import replay_events
from harness_state_io import write_json_atomic
from harness_state_schema import StateError, read_events
from harness_task_bundle import TaskBundle
from harness_time import parse_rfc3339


ARCHIVE_FIELDS = {"task_id", "plan_revision", "archived_at", "files"}
ARCHIVE_FILE_FIELDS = {"source_path", "archive_path", "sha256", "size_bytes"}


class AmendmentError(Exception):
    """plan revision 归档或激活失败。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def revision_archive_dir(bundle: TaskBundle, revision: int) -> Path:
    return (
        bundle.task_dir
        / "artifacts"
        / "amendments"
        / f"revision-{revision:04d}"
    )


def write_archive_manifest(path: Path, payload: dict[str, Any]) -> None:
    try:
        write_json_atomic(
            path,
            payload,
            error_code="AMENDMENT_ARCHIVE_WRITE_FAILED",
            label="amendment archive manifest",
        )
    except StateError as exc:
        raise AmendmentError(exc.code, exc.message) from exc


def archive_file(
    bundle: TaskBundle,
    source: Path,
    archive_root: Path,
    *,
    allow_missing_ledger: bool = False,
) -> dict[str, Any] | None:
    source_relative = source.relative_to(bundle.task_dir).as_posix()
    target = archive_root / "files" / source_relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        if allow_missing_ledger:
            try:
                target.write_bytes(b"")
            except OSError as exc:
                raise AmendmentError(
                    "AMENDMENT_ARCHIVE_COPY_FAILED",
                    f"无法创建空 ledger 归档：{target}: {exc}",
                ) from exc
        else:
            return None
    else:
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_COPY_FAILED",
                f"无法归档 {source}: {exc}",
            ) from exc
    return {
        "source_path": source_relative,
        "archive_path": target.relative_to(bundle.task_dir).as_posix(),
        "sha256": sha256_file(target),
        "size_bytes": target.stat().st_size,
    }


def archive_current_revision(bundle: TaskBundle) -> dict[str, Any]:
    try:
        attestation = validate_attestation(bundle)
    except AttestationError as exc:
        raise AmendmentError(exc.code, exc.message) from exc
    try:
        events = read_events(bundle.ledger_path)
        if events:
            replayed = replay_events(
                bundle.contract,
                events,
                initial_timestamp=str(attestation["approved_at"]),
            )
            if replayed.state["reapproval_required"] is not True:
                raise AmendmentError(
                    "AMENDMENT_NOT_REQUESTED",
                    "已有执行事件时，归档前必须记录 amendment request 或 research drift。",
                )
    except StateError as exc:
        raise AmendmentError(exc.code, exc.message) from exc
    archive_root = revision_archive_dir(bundle, bundle.plan_revision)
    manifest_path = archive_root / "archive-manifest.json"
    if archive_root.exists():
        if manifest_path.is_file():
            return validate_archive(bundle, archive_root)
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INCOMPLETE",
            f"归档目录存在但未完成：{archive_root}",
        )
    archive_root.mkdir(parents=True)

    records: list[dict[str, Any]] = []
    for item in attestation["immutable_files"]:
        source = bundle.task_dir / item["path"]
        record = archive_file(bundle, source, archive_root)
        assert record is not None
        records.append(record)
    for source, allow_missing in (
        (bundle.attestation_path, False),
        (bundle.ledger_path, True),
        (bundle.run_state_path, False),
    ):
        record = archive_file(
            bundle,
            source,
            archive_root,
            allow_missing_ledger=allow_missing,
        )
        if record is not None:
            records.append(record)
    manifest = {
        "task_id": bundle.task_id,
        "plan_revision": bundle.plan_revision,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "files": sorted(records, key=lambda item: item["source_path"]),
    }
    write_archive_manifest(manifest_path, manifest)
    return manifest


def load_archive_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            f"无法解析 archive manifest：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict) or set(value) != ARCHIVE_FIELDS:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive manifest 字段无效。",
        )
    return value


def validate_archive(bundle: TaskBundle, archive_root: Path) -> dict[str, Any]:
    try:
        archive_root.resolve().relative_to(bundle.task_dir)
    except ValueError as exc:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_PATH_UNSAFE",
            f"归档目录越出 task-dir：{archive_root}",
        ) from exc
    manifest = load_archive_manifest(archive_root / "archive-manifest.json")
    if manifest.get("task_id") != bundle.task_id:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_TASK_MISMATCH",
            "archive task_id 与当前 task 不一致。",
        )
    revision = manifest.get("plan_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive plan_revision 必须是正整数。",
        )
    archived_at = manifest.get("archived_at")
    try:
        parse_rfc3339(archived_at)
    except ValueError as exc:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive archived_at 必须是 RFC3339 时间。",
        ) from exc
    files = manifest.get("files")
    if not isinstance(files, list):
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive files 必须是数组。",
        )
    source_paths: set[str] = set()
    archive_paths: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != ARCHIVE_FILE_FIELDS:
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_INVALID",
                f"archive files[{index}] 字段无效。",
            )
        source_value = item.get("source_path")
        archive_value = item.get("archive_path")
        digest = item.get("sha256")
        size = item.get("size_bytes")
        if (
            not isinstance(source_value, str)
            or not source_value
            or not isinstance(archive_value, str)
            or not archive_value
        ):
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_INVALID",
                f"archive files[{index}] 路径必须是字符串。",
            )
        if (
            Path(source_value).is_absolute()
            or ".." in Path(source_value).parts
            or Path(archive_value).is_absolute()
            or ".." in Path(archive_value).parts
        ):
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_PATH_UNSAFE",
                f"archive files[{index}] 包含不安全路径。",
            )
        if source_value in source_paths or archive_value in archive_paths:
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_INVALID",
                "archive source_path/archive_path 必须唯一。",
            )
        source_paths.add(source_value)
        archive_paths.add(archive_value)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_INVALID",
                f"archive files[{index}] hash/size 无效。",
            )
        archive_path = bundle.task_dir / archive_value
        try:
            archive_path.resolve().relative_to(archive_root.resolve())
        except ValueError as exc:
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_PATH_UNSAFE",
                f"归档文件越出 revision 目录：{archive_path}",
            ) from exc
        if not archive_path.is_file():
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_FILE_MISSING",
                f"归档文件不存在：{archive_path}",
            )
        if (
            archive_path.stat().st_size != size
            or sha256_file(archive_path) != digest
        ):
            raise AmendmentError(
                "AMENDMENT_ARCHIVE_HASH_MISMATCH",
                f"归档文件哈希或大小不匹配：{archive_path}",
            )
    required_sources = {
        "execution-plan.md",
        "plan-contract.json",
        "attestation.json",
        "ledger.jsonl",
    }
    missing_sources = sorted(required_sources - source_paths)
    if missing_sources:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive 缺少必备 revision 文件："
            f"{', '.join(missing_sources)}",
        )
    return manifest


def record_by_source(
    manifest: dict[str, Any],
    source_path: str,
) -> dict[str, Any] | None:
    for item in manifest["files"]:
        if item["source_path"] == source_path:
            return item
    return None


def load_archived_contract(
    bundle: TaskBundle,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    record = record_by_source(manifest, "plan-contract.json")
    if record is None:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive 缺少 plan-contract.json。",
        )
    path = bundle.task_dir / str(record["archive_path"])
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            f"无法解析归档 plan contract：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "归档 plan contract 根节点必须是 object。",
        )
    return value


def definitions_by_id(contract: dict[str, Any], field: str) -> dict[str, Any]:
    values = contract.get(field, [])
    if not isinstance(values, list):
        return {}
    return {
        str(item["id"]): item
        for item in values
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def carried_stage_semantics(
    contract: dict[str, Any],
    stage_id: str,
) -> dict[str, Any] | None:
    stages = definitions_by_id(contract, "stages")
    stage = stages.get(stage_id)
    if not isinstance(stage, dict):
        return None
    referenced_fields = {
        "requirements": "requirement_ids",
        "acceptance_criteria": "acceptance_ids",
        "nonfunctional_requirements": "nonfunctional_ids",
        "validations": "validation_ids",
    }
    semantics: dict[str, Any] = {"stage": stage}
    for collection, reference_field in referenced_fields.items():
        definitions = definitions_by_id(contract, collection)
        references = stage.get(reference_field, [])
        if not isinstance(references, list):
            return None
        semantics[collection] = [definitions.get(str(item)) for item in references]
    return semantics


def validate_carried_stage_semantics(
    bundle: TaskBundle,
    manifest: dict[str, Any],
    carried_stage_ids: list[str],
) -> None:
    previous_contract = load_archived_contract(bundle, manifest)
    for stage_id in carried_stage_ids:
        previous = carried_stage_semantics(previous_contract, stage_id)
        current = carried_stage_semantics(bundle.contract, stage_id)
        if previous is None or current is None or previous != current:
            raise AmendmentError(
                "AMENDMENT_CARRY_SEMANTICS_CHANGED",
                f"carried stage 的约束或引用定义已变化，必须重跑：{stage_id}",
            )


def validate_carried_stage_completion(
    bundle: TaskBundle,
    manifest: dict[str, Any],
    carried_stage_ids: list[str],
) -> None:
    if not carried_stage_ids:
        return
    previous_contract = load_archived_contract(bundle, manifest)
    ledger_record = record_by_source(manifest, "ledger.jsonl")
    if ledger_record is None:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive 缺少 ledger.jsonl。",
        )
    ledger_path = bundle.task_dir / str(ledger_record["archive_path"])
    try:
        replayed = replay_events(previous_contract, read_events(ledger_path))
    except StateError as exc:
        raise AmendmentError(exc.code, exc.message) from exc
    incomplete = sorted(
        set(carried_stage_ids) - set(replayed.state["completed_stage_ids"])
    )
    if incomplete:
        raise AmendmentError(
            "AMENDMENT_CARRY_NOT_COMPLETED",
            "只能继承上一 revision 已完成的 stages："
            f"{', '.join(incomplete)}",
        )


def activate_amendment(
    bundle: TaskBundle,
    archive_root: Path,
    *,
    carried_completed_stage_ids: list[str] | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    manifest = validate_archive(bundle, archive_root)
    previous_revision = manifest.get("plan_revision")
    if not isinstance(previous_revision, int):
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive plan_revision 无效。",
        )
    if bundle.plan_revision != previous_revision + 1:
        raise AmendmentError(
            "AMENDMENT_REVISION_INVALID",
            "新 plan_revision 必须比归档 revision 大 1。",
        )
    try:
        validate_attestation(bundle)
    except AttestationError as exc:
        raise AmendmentError(exc.code, exc.message) from exc

    carried_stage_ids = carried_completed_stage_ids or []
    validate_carried_stage_semantics(bundle, manifest, carried_stage_ids)
    validate_carried_stage_completion(bundle, manifest, carried_stage_ids)

    ledger_record = record_by_source(manifest, "ledger.jsonl")
    if ledger_record is None:
        raise AmendmentError(
            "AMENDMENT_ARCHIVE_INVALID",
            "archive 缺少 ledger.jsonl 记录。",
        )
    paths_to_reset: list[Path] = []
    for current_path in (bundle.ledger_path, bundle.run_state_path):
        if not current_path.is_file():
            continue
        record = record_by_source(
            manifest,
            current_path.relative_to(bundle.task_dir).as_posix(),
        )
        if record is None or sha256_file(current_path) != record["sha256"]:
            raise AmendmentError(
                "AMENDMENT_RUNTIME_DRIFT",
                f"当前运行文件未被归档或已漂移：{current_path}",
            )
        paths_to_reset.append(current_path)
    for current_path in paths_to_reset:
        try:
            current_path.unlink()
        except OSError as exc:
            raise AmendmentError(
                "AMENDMENT_RUNTIME_RESET_FAILED",
                f"无法轮换当前运行文件：{current_path}: {exc}",
            ) from exc

    payload = {
        "previous_revision": previous_revision,
        "previous_archive": archive_root.relative_to(bundle.task_dir).as_posix(),
        "previous_ledger_sha256": ledger_record["sha256"],
        "carried_completed_stage_ids": carried_stage_ids,
    }
    try:
        return append_event_and_update(
            bundle,
            "amendment_approved",
            payload=payload,
            occurred_at=occurred_at,
            amendment_activation=True,
        )
    except EventWriteError as exc:
        raise AmendmentError(exc.code, exc.message) from exc
