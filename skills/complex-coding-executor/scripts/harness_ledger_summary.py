#!/usr/bin/env python3
"""生成稳定形状的任务 ledger 摘要。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_task_resolver import ResolverError, resolve_task


LEDGER_NAME = "ledger.jsonl"


def read_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return events, errors
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_no}: {exc}")
                continue
            if isinstance(value, dict):
                events.append(value)
            else:
                errors.append(f"line {line_no}: event is not an object")
    return events, errors


def summarize(events: list[dict[str, Any]], parse_errors: list[str]) -> dict[str, Any]:
    completed: set[str] = set()
    started: set[str] = set()
    last_event_by_actor: dict[str, str] = {}
    current_stage = ""
    last_blocking_reason = ""
    last_heartbeat = ""
    validation_failed = 0
    review_findings = 0

    for event in events:
        event_type = str(event.get("event", ""))
        stage = str(event.get("stage", ""))
        actor = str(event.get("actor", ""))
        if actor:
            last_event_by_actor[actor] = event_type
        if event_type == "stage_started" and stage:
            started.add(stage)
            current_stage = stage
        elif event_type == "stage_completed" and stage:
            completed.add(stage)
            if current_stage == stage:
                current_stage = ""
        elif event_type == "blocked":
            last_blocking_reason = str(event.get("reason") or event.get("summary") or "")
        elif event_type == "heartbeat":
            last_heartbeat = stage or str(event.get("summary", ""))
        elif event_type == "validation_failed":
            validation_failed += 1
        elif event_type == "review_finding":
            review_findings += 1

    return {
        "entries": len(events),
        "parse_errors": parse_errors,
        "stages_started": sorted(started),
        "stages_completed": sorted(completed),
        "stages_complete_count": len(completed),
        "current_stage": current_stage,
        "last_event_by_actor": dict(sorted(last_event_by_actor.items())),
        "last_blocking_reason": last_blocking_reason,
        "last_heartbeat": last_heartbeat,
        "validation_failed_count": validation_failed,
        "review_finding_count": review_findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="输出 .harness ledger 摘要")
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument("--task-dir", help="任务目录；省略时读取 active-task.json")
    args = parser.parse_args()

    try:
        resolved = resolve_task(args.workspace, args.task_dir)
    except ResolverError as exc:
        print(f"FAIL: {exc}")
        return 1

    events, parse_errors = read_events(resolved.task_dir / LEDGER_NAME)
    payload = summarize(events, parse_errors)
    payload["task_id"] = resolved.active.get("task_id")
    payload["ledger_path"] = str(resolved.task_dir / LEDGER_NAME)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if parse_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
