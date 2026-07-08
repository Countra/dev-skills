#!/usr/bin/env python3
"""向任务 ledger 追加一条 JSONL 事件。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_task_resolver import ResolverError, resolve_task


LEDGER_NAME = "ledger.jsonl"
EVENT_TYPES = {
    "plan_created",
    "plan_approved",
    "stage_started",
    "stage_completed",
    "validation_passed",
    "validation_failed",
    "review_finding",
    "amendment_requested",
    "blocked",
    "final_ready",
    "heartbeat",
    "note",
}


def parse_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--metadata-json must decode to an object")
    return parsed


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="追加 .harness ledger 事件")
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument("--task-dir", help="任务目录；省略时读取 active-task.json")
    parser.add_argument("--event", required=True, choices=sorted(EVENT_TYPES), help="事件类型")
    parser.add_argument("--stage", default="", help="阶段，例如 Stage 2")
    parser.add_argument("--actor", default="complex-coding-executor", help="事件写入方")
    parser.add_argument("--summary", default="", help="简短摘要")
    parser.add_argument("--result", default="", help="结果，例如 passed/failed/blocked")
    parser.add_argument("--reason", default="", help="失败或阻塞原因")
    parser.add_argument("--metadata-json", help="附加对象，必须是 JSON object")
    args = parser.parse_args()

    try:
        resolved = resolve_task(args.workspace, args.task_dir)
        metadata = parse_metadata(args.metadata_json)
    except (ResolverError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    event = {
        "schema_version": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": resolved.active.get("task_id"),
        "event": args.event,
        "stage": args.stage,
        "actor": args.actor,
        "summary": args.summary,
        "result": args.result,
        "reason": args.reason,
        "metadata": metadata,
    }
    append_event(resolved.task_dir / LEDGER_NAME, event)
    print(f"PASS: appended ledger event: {args.event}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
