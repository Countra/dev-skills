"""Codex JSONL trace 与 structured final 的有界解析。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ExecutionError


KNOWN_EVENT_TYPES = {
    "error",
    "item.completed",
    "item.started",
    "thread.started",
    "turn.completed",
    "turn.failed",
    "turn.started",
}


def parse_jsonl_trace(path: Path, *, max_events: int = 10000, max_line_bytes: int = 1024 * 1024) -> dict[str, Any]:
    """只汇总稳定字段，未知事件保留在原 trace 中且不猜测语义。"""
    event_count = 0
    event_types: dict[str, int] = {}
    unknown_types: set[str] = set()
    usage: dict[str, Any] = {}
    thread_id: str | None = None
    failed = False
    try:
        with path.open("rb") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                if len(raw_line) > max_line_bytes:
                    raise ExecutionError(f"trace 第 {line_number} 行超过大小上限", outcome="unknown")
                if not raw_line.strip():
                    continue
                event_count += 1
                if event_count > max_events:
                    raise ExecutionError("trace 事件数量超过上限", outcome="unknown")
                try:
                    event = json.loads(raw_line)
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise ExecutionError(f"trace 第 {line_number} 行不是合法 JSON", outcome="unknown") from exc
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ExecutionError(f"trace 第 {line_number} 行缺少事件 type", outcome="unknown")
                event_type = event["type"]
                event_types[event_type] = event_types.get(event_type, 0) + 1
                if event_type not in KNOWN_EVENT_TYPES:
                    unknown_types.add(event_type)
                if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
                    thread_id = event["thread_id"]
                if event_type == "turn.completed" and isinstance(event.get("usage"), dict):
                    usage = dict(event["usage"])
                failed = failed or event_type in {"error", "turn.failed"}
    except OSError as exc:
        raise ExecutionError(f"无法读取 Codex trace：{exc}", outcome="unknown") from exc
    return {
        "event_count": event_count,
        "event_types": event_types,
        "unknown_event_types": sorted(unknown_types),
        "thread_id": thread_id,
        "usage": usage,
        "failed_event_seen": failed,
    }


def load_structured_final(path: Path, *, max_bytes: int = 1024 * 1024) -> dict[str, Any]:
    """读取有大小上限的 structured final object。"""
    try:
        if path.stat().st_size > max_bytes:
            raise ExecutionError("structured final 超过大小上限", outcome="unknown")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExecutionError("Codex 未生成 structured final", outcome="unknown") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionError(f"structured final 无法解析：{exc}", outcome="unknown") from exc
    if not isinstance(value, dict):
        raise ExecutionError("structured final 必须是 JSON object", outcome="unknown")
    return value
