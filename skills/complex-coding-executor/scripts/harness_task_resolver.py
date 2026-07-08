#!/usr/bin/env python3
"""解析当前 .harness managed 任务，并校验路径边界。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ResolverError(Exception):
    """resolver 发现不可执行或不安全状态。"""


@dataclass(frozen=True)
class ResolvedTask:
    workspace: Path
    active_path: Path
    task_dir: Path
    plan_path: Path
    active: dict[str, Any]


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise ResolverError(f"active-task not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ResolverError(f"active-task is not valid json: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResolverError("active-task root must be an object")
    return value


def ensure_within_workspace(path: Path, workspace: Path, label: str) -> None:
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise ResolverError(f"{label} escapes workspace: {path}") from exc


def resolve_task(
    workspace_arg: str | Path = ".",
    task_dir_arg: str | Path | None = None,
    *,
    require_executable: bool = False,
) -> ResolvedTask:
    if os.environ.get("HARNESS_DISABLED") == "1":
        raise ResolverError("HARNESS_DISABLED=1")

    workspace = Path(workspace_arg).resolve()
    active_path = workspace / ".harness" / "active-task.json"
    active = load_json(active_path)

    raw_task_dir = str(task_dir_arg or active.get("task_dir") or "").strip()
    if not raw_task_dir:
        raise ResolverError("active-task task_dir is empty")
    if "\x00" in raw_task_dir:
        raise ResolverError("active-task task_dir contains null byte")

    task_dir = Path(raw_task_dir)
    if not task_dir.is_absolute():
        task_dir = workspace / task_dir
    task_dir = task_dir.resolve()
    ensure_within_workspace(task_dir, workspace, "task_dir")

    plan_path = (task_dir / "execution-plan.md").resolve()
    ensure_within_workspace(plan_path, workspace, "execution-plan")
    if not plan_path.is_file():
        raise ResolverError(f"execution-plan not found: {plan_path}")

    if require_executable:
        status_values = {
            str(active.get("status", "")).lower(),
            str(active.get("overall_status", "")).lower(),
        }
        if "completed" in status_values:
            raise ResolverError("active task is already completed")
        if "awaiting_plan_approval" in status_values:
            raise ResolverError("active task is awaiting plan approval")

    return ResolvedTask(
        workspace=workspace,
        active_path=active_path,
        task_dir=task_dir,
        plan_path=plan_path,
        active=active,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="解析 .harness active task")
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument("--task-dir", help="任务目录；省略时读取 active-task.json")
    parser.add_argument("--require-executable", action="store_true", help="拒绝未批准或已完成任务")
    args = parser.parse_args()

    if os.environ.get("HARNESS_DISABLED") == "1":
        print(json.dumps({"disabled": True, "reason": "HARNESS_DISABLED=1"}, ensure_ascii=False))
        return 0

    try:
        resolved = resolve_task(
            args.workspace,
            args.task_dir,
            require_executable=args.require_executable,
        )
    except ResolverError as exc:
        print(f"FAIL: {exc}")
        return 1

    print(
        json.dumps(
            {
                "disabled": False,
                "workspace": str(resolved.workspace),
                "active_path": str(resolved.active_path),
                "task_dir": str(resolved.task_dir),
                "plan_path": str(resolved.plan_path),
                "task_id": resolved.active.get("task_id"),
                "status": resolved.active.get("status"),
                "overall_status": resolved.active.get("overall_status"),
                "current_stage": resolved.active.get("current_stage"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
