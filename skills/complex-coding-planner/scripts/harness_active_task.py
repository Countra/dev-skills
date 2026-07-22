#!/usr/bin/env python3
"""原子维护 workspace 唯一的 compact managed task 指针。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_contract import load_contract
from harness_plan_check import validate_task


POINTER_FIELDS = {"task_id", "task_dir", "updated_at"}
LIFECYCLES = {
    "approved",
    "in_progress",
    "blocked",
    "awaiting_reapproval",
    "completed",
}


class ActiveTaskError(Exception):
    """表示 active pointer 无法安全读取或更新。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspace(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_WORKSPACE_INVALID",
            "workspace 不存在或不可访问。",
        ) from exc
    if not resolved.is_dir():
        raise ActiveTaskError(
            "ACTIVE_TASK_WORKSPACE_INVALID",
            "workspace 必须是目录。",
        )
    return resolved


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_FILE_MISSING",
            f"缺少 {label}。",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_FILE_INVALID",
            f"无法读取 {label}。",
        ) from exc
    if not isinstance(value, dict):
        raise ActiveTaskError(
            "ACTIVE_TASK_FILE_INVALID",
            f"{label} 根节点必须是 object。",
        )
    return value


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
    except OSError as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_WRITE_FAILED",
            "无法创建 active-task.json 的原子写入临时文件。",
        ) from exc
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ActiveTaskError(
            "ACTIVE_TASK_WRITE_FAILED",
            "无法原子更新 active-task.json。",
        ) from exc


def _relative_task_dir(workspace: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if not candidate.is_absolute() and ".." in candidate.parts:
        raise ActiveTaskError(
            "ACTIVE_TASK_PATH_INVALID",
            "task-dir 不能包含 ..。",
        )
    try:
        resolved = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (workspace / candidate).resolve(strict=False)
        )
        task_root = (workspace / ".harness" / "tasks").resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_PATH_INVALID",
            "task-dir 无法安全解析。",
        ) from exc
    try:
        task_root.relative_to(workspace)
        relative = resolved.relative_to(task_root)
    except ValueError as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_PATH_INVALID",
            "task-dir 与任务根目录必须位于 workspace 内。",
        ) from exc
    normalized = (Path(".harness") / "tasks" / relative).as_posix()
    return resolved, normalized


def _task_from_pointer(workspace: Path, pointer: dict[str, Any]) -> dict[str, Any]:
    if set(pointer) != POINTER_FIELDS:
        raise ActiveTaskError(
            "ACTIVE_TASK_POINTER_INVALID",
            "active-task.json 字段不符合 compact pointer。",
        )
    task_id = pointer.get("task_id")
    raw_dir = pointer.get("task_dir")
    updated_at = pointer.get("updated_at")
    if not isinstance(task_id, str) or not task_id:
        raise ActiveTaskError(
            "ACTIVE_TASK_POINTER_INVALID",
            "pointer.task_id 无效。",
        )
    if not isinstance(raw_dir, str) or not raw_dir:
        raise ActiveTaskError(
            "ACTIVE_TASK_POINTER_INVALID",
            "pointer.task_dir 无效。",
        )
    if not isinstance(updated_at, str) or not updated_at:
        raise ActiveTaskError(
            "ACTIVE_TASK_POINTER_INVALID",
            "pointer.updated_at 无效。",
        )
    task_dir, normalized = _relative_task_dir(workspace, raw_dir)
    if not task_dir.is_dir():
        raise ActiveTaskError(
            "ACTIVE_TASK_TARGET_MISSING",
            f"任务目录不存在：{normalized}",
        )
    contract, contract_issues = load_contract(task_dir / "plan-contract.json")
    errors = [issue for issue in contract_issues if issue.severity == "error"]
    if errors:
        raise ActiveTaskError(errors[0].code, errors[0].message)
    if contract.get("task_id") != task_id:
        raise ActiveTaskError(
            "ACTIVE_TASK_ID_MISMATCH",
            "pointer.task_id 与 plan-contract.json 不一致。",
        )

    state_path = task_dir / "run-state.json"
    lifecycle = "planning"
    if state_path.exists():
        state = _load_object(state_path, "run-state.json")
        if state.get("task_id") != task_id:
            raise ActiveTaskError(
                "ACTIVE_TASK_ID_MISMATCH",
                "run-state.json 与 pointer.task_id 不一致。",
            )
        lifecycle = state.get("lifecycle")
        if lifecycle not in LIFECYCLES:
            raise ActiveTaskError(
                "ACTIVE_TASK_STATE_INVALID",
                "run-state.lifecycle 无效。",
            )
    return {
        "task_id": task_id,
        "task_dir": normalized,
        "lifecycle": lifecycle,
    }


def classify(workspace: Path) -> dict[str, Any]:
    pointer_path = workspace / ".harness" / "active-task.json"
    if not pointer_path.exists():
        return {"status": "none", "task": None, "error": None}
    try:
        pointer = _load_object(pointer_path, "active-task.json")
        task = _task_from_pointer(workspace, pointer)
    except ActiveTaskError as exc:
        return {
            "status": "invalid",
            "task": None,
            "error": {"code": exc.code, "message": exc.message},
        }
    return {"status": "active", "task": task, "error": None}


def activate(
    workspace: Path,
    raw_task_dir: str,
    *,
    allow_switch: bool,
    expected_task_id: str | None,
) -> dict[str, Any]:
    task_dir, normalized = _relative_task_dir(workspace, raw_task_dir)
    issues = validate_task(task_dir, "approval")
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise ActiveTaskError(errors[0].code, errors[0].message)
    contract, _ = load_contract(task_dir / "plan-contract.json")
    task_id = str(contract["task_id"])

    current = classify(workspace)
    if current["status"] == "invalid":
        error = current["error"]
        raise ActiveTaskError(
            error["code"],
            f"现有 pointer 无效，必须先处理：{error['message']}",
        )
    current_task = current.get("task")
    switching_task = current_task and (
        current_task["task_id"] != task_id
        or current_task["task_dir"] != normalized
    )
    if switching_task:
        if not allow_switch:
            raise ActiveTaskError(
                "ACTIVE_TASK_SWITCH_REQUIRED",
                "当前 pointer 指向其它任务目录，切换必须显式使用 --switch。",
            )
        if expected_task_id != current_task["task_id"]:
            raise ActiveTaskError(
                "ACTIVE_TASK_EXPECTATION_MISMATCH",
                "--expect-task-id 与当前任务不一致。",
            )

    pointer = {"task_id": task_id, "task_dir": normalized, "updated_at": _now()}
    _write_atomic(workspace / ".harness" / "active-task.json", pointer)
    return {"status": "active", "task": _task_from_pointer(workspace, pointer)}


def clear(workspace: Path, expected_task_id: str | None) -> dict[str, Any]:
    pointer_path = workspace / ".harness" / "active-task.json"
    current = classify(workspace)
    if current["status"] == "none":
        return {"status": "none", "task": None}
    if current["status"] == "invalid":
        if expected_task_id:
            pointer = _load_object(pointer_path, "active-task.json")
            if pointer.get("task_id") != expected_task_id:
                raise ActiveTaskError(
                    "ACTIVE_TASK_EXPECTATION_MISMATCH",
                    "--expect-task-id 与无效 pointer 中的 task_id 不一致。",
                )
        try:
            pointer_path.unlink()
        except OSError as exc:
            raise ActiveTaskError(
                "ACTIVE_TASK_WRITE_FAILED",
                "无法删除无效的 active-task.json。",
            ) from exc
        return {"status": "cleared", "task": None}
    task = current["task"]
    if expected_task_id and expected_task_id != task["task_id"]:
        raise ActiveTaskError(
            "ACTIVE_TASK_EXPECTATION_MISMATCH",
            "--expect-task-id 与当前任务不一致。",
        )
    try:
        pointer_path.unlink()
    except OSError as exc:
        raise ActiveTaskError(
            "ACTIVE_TASK_WRITE_FAILED",
            "无法删除 active-task.json。",
        ) from exc
    return {"status": "cleared", "task": task}


def _print_result(result: dict[str, Any]) -> None:
    if result["status"] == "none":
        print("No active managed task.")
        return
    if result["status"] == "invalid":
        error = result["error"]
        print(f"INVALID [{error['code']}]: {error['message']}")
        return
    task = result.get("task")
    if task:
        print(
            f"{result['status'].upper()}: {task['task_id']} "
            f"({task['lifecycle']}) at {task['task_dir']}"
        )
    else:
        print(result["status"].upper())


def main() -> int:
    parser = argparse.ArgumentParser(description="读取或更新当前 managed task 指针")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    activate_parser = commands.add_parser("activate")
    activate_parser.add_argument("--task-dir", required=True)
    activate_parser.add_argument("--switch", action="store_true")
    activate_parser.add_argument("--expect-task-id")
    clear_parser = commands.add_parser("clear")
    clear_parser.add_argument("--expect-task-id")
    args = parser.parse_args()

    try:
        workspace = _workspace(args.workspace)
        if args.command == "status":
            result = classify(workspace)
        elif args.command == "activate":
            result = activate(
                workspace,
                args.task_dir,
                allow_switch=args.switch,
                expected_task_id=args.expect_task_id,
            )
        else:
            result = clear(workspace, args.expect_task_id)
    except ActiveTaskError as exc:
        print(f"FAIL [{exc.code}]: {exc.message}")
        return 1
    _print_result(result)
    return 1 if result["status"] == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
