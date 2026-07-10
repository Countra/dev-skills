#!/usr/bin/env python3
"""run-state 原子写入与 ledger 持久化。"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_state_schema import EVENT_TYPES, STATE_FIELDS, StateError


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError("RUN_STATE_INVALID_JSON", f"无法解析 run-state：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError("RUN_STATE_INVALID_TYPE", "run-state 根节点必须是 object。")
    unknown = sorted(set(value) - STATE_FIELDS)
    missing = sorted(STATE_FIELDS - set(value))
    if unknown:
        raise StateError(
            "RUN_STATE_UNKNOWN_FIELD",
            f"run-state 包含未知字段：{', '.join(unknown)}",
        )
    if missing:
        raise StateError(
            "RUN_STATE_MISSING_FIELD",
            f"run-state 缺少字段：{', '.join(missing)}",
        )
    if value.get("lifecycle") not in {
        "approved",
        "in_progress",
        "blocked",
        "completed",
        "aborted",
    }:
        raise StateError("RUN_STATE_INVALID_VALUE", "run-state.lifecycle 无效。")
    if not isinstance(value.get("task_id"), str) or not value["task_id"]:
        raise StateError(
            "RUN_STATE_INVALID_TYPE",
            "run-state.task_id 必须是非空字符串。",
        )
    for field in ("current_stage_id", "stop_condition", "next_action", "updated_at"):
        item = value.get(field)
        if item is not None and not isinstance(item, str):
            raise StateError(
                "RUN_STATE_INVALID_TYPE",
                f"run-state.{field} 必须是字符串或 null。",
            )
    for field in ("completed_stage_ids", "remaining_stage_ids"):
        entries = value.get(field)
        if not isinstance(entries, list) or not all(
            isinstance(item, str) for item in entries
        ):
            raise StateError(
                "RUN_STATE_INVALID_TYPE",
                f"run-state.{field} 必须是字符串数组。",
            )
        if len(entries) != len(set(entries)):
            raise StateError(
                "RUN_STATE_DUPLICATE_STAGE",
                f"run-state.{field} 包含重复 stage。",
            )
    if set(value["completed_stage_ids"]) & set(value["remaining_stage_ids"]):
        raise StateError(
            "RUN_STATE_STAGE_SET_CONFLICT",
            "completed 和 remaining stage 集合重叠。",
        )
    for field in ("plan_revision", "last_event_seq", "state_revision"):
        item = value.get(field)
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise StateError(
                "RUN_STATE_INVALID_TYPE",
                f"run-state.{field} 必须是非负整数。",
            )
    if not isinstance(value.get("reapproval_required"), bool):
        raise StateError(
            "RUN_STATE_INVALID_TYPE",
            "run-state.reapproval_required 必须是 boolean。",
        )
    return value


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    error_code: str,
    label: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise StateError(
            error_code,
            f"无法原子写入 {label}：{path}: {exc}",
        ) from exc


def write_state_atomic(path: Path, state: dict[str, Any]) -> None:
    write_json_atomic(
        path,
        state,
        error_code="RUN_STATE_WRITE_FAILED",
        label="run-state",
    )


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StateError(
            "LEDGER_APPEND_FAILED",
            f"无法追加 ledger：{path}: {exc}",
        ) from exc


def build_event(
    contract: dict[str, Any],
    seq: int,
    event_type: str,
    *,
    stage_id: str | None = None,
    attempt: int | None = None,
    payload: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise StateError("LEDGER_EVENT_TYPE_INVALID", f"未知 event type：{event_type}")
    return {
        "seq": seq,
        "event_id": f"EVT-{seq:06d}",
        "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
        "task_id": contract["task_id"],
        "plan_revision": contract["plan_revision"],
        "stage_id": stage_id,
        "type": event_type,
        "attempt": attempt,
        "payload": payload if payload is not None else {},
        "evidence_refs": evidence_refs if evidence_refs is not None else [],
    }


def state_differences(
    snapshot: dict[str, Any] | None,
    replayed: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if snapshot is None:
        return {"$": {"snapshot": None, "replayed": replayed}}
    differences: dict[str, dict[str, Any]] = {}
    for field in sorted(STATE_FIELDS):
        if snapshot.get(field) != replayed.get(field):
            differences[field] = {
                "snapshot": snapshot.get(field),
                "replayed": replayed.get(field),
            }
    return differences
