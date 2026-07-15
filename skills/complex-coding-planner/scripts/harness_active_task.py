#!/usr/bin/env python3
"""安全分类、激活和显式切换 pointer-only active task。"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POINTER_FIELDS = {"task_id", "task_dir", "run_state_path", "updated_at"}
ACTIVE_LIFECYCLES = {"approved", "in_progress", "blocked"}
TERMINAL_LIFECYCLES = {"completed", "aborted"}


class ActiveTaskError(Exception):
    """active pointer 操作的稳定错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"缺少 {label}：{path}",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"无法解析 {label}：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"{label} 根节点必须是 object：{path}",
        )
    return value


def ensure_within(path: Path, parent: Path, label: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"{label} 越出允许目录：{path}",
        ) from exc


def resolve_relative(base: Path, raw: str, parent: Path, label: str) -> Path:
    if not raw or "\x00" in raw:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"{label} 为空或包含 null byte。",
        )
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"{label} 必须是安全相对路径：{raw}",
        )
    resolved = (base / candidate).resolve()
    ensure_within(resolved, parent, label)
    return resolved


def parse_rfc3339(value: str, label: str) -> None:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"{label} 不是 RFC3339 时间：{value}",
        ) from exc
    if parsed.tzinfo is None:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"{label} 必须包含时区：{value}",
        )


def validate_pointer(pointer: dict[str, Any]) -> None:
    unknown = sorted(set(pointer) - POINTER_FIELDS)
    missing = sorted(POINTER_FIELDS - set(pointer))
    if unknown or missing:
        details = f"unknown={unknown}, missing={missing}"
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            f"active-task 不是 closed pointer：{details}",
        )
    for field in POINTER_FIELDS:
        if not isinstance(pointer.get(field), str) or not pointer[field].strip():
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                f"active-task.{field} 必须是非空字符串。",
            )
    for field in ("task_dir", "run_state_path"):
        candidate = Path(str(pointer[field]))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                f"active-task.{field} 必须是安全相对路径。",
            )
    parse_rfc3339(str(pointer["updated_at"]), "active-task.updated_at")


def load_target(
    workspace: Path,
    task_dir_arg: str | Path,
) -> tuple[Path, str, str]:
    tasks_root = (workspace / ".harness" / "tasks").resolve()
    candidate = Path(task_dir_arg)
    target = candidate.resolve() if candidate.is_absolute() else (workspace / candidate).resolve()
    ensure_within(target, tasks_root, "target task_dir")
    if not target.is_dir():
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_TARGET_INVALID",
            f"目标 task-dir 不存在：{target}",
        )
    contract = load_json_object(target / "plan-contract.json", "target plan-contract")
    task_id = contract.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_TARGET_INVALID",
            "target plan-contract.task_id 必须是非空字符串。",
        )
    relative = target.relative_to(workspace).as_posix()
    return target, task_id, relative


def unknown_classification(
    target_task_id: str,
    target_task_dir: str,
    error: ActiveTaskError,
    *,
    current_task_id: str | None = None,
) -> dict[str, Any]:
    return {
        "state": "different-unknown",
        "target_task_id": target_task_id,
        "target_task_dir": target_task_dir,
        "current_task_id": current_task_id,
        "current_task_dir": None,
        "current_lifecycle": None,
        "reason": error.message,
    }


def classify_active_pointer(
    workspace_arg: str | Path,
    task_dir_arg: str | Path,
) -> dict[str, Any]:
    workspace = Path(workspace_arg).resolve()
    target_dir, target_id, target_relative = load_target(workspace, task_dir_arg)
    pointer_path = (workspace / ".harness" / "active-task.json").resolve()
    if not pointer_path.exists():
        return {
            "state": "missing",
            "target_task_id": target_id,
            "target_task_dir": target_relative,
            "current_task_id": None,
            "current_task_dir": None,
            "current_lifecycle": None,
            "reason": "active-task.json 不存在",
        }
    try:
        pointer = load_json_object(pointer_path, "active-task pointer")
        validate_pointer(pointer)
    except ActiveTaskError as exc:
        return unknown_classification(target_id, target_relative, exc)

    current_id = str(pointer["task_id"])
    current_relative = str(pointer["task_dir"]).replace("\\", "/")
    try:
        current_dir = resolve_relative(
            workspace,
            str(pointer["task_dir"]),
            workspace,
            "current task_dir",
        )
        ensure_within(
            current_dir,
            (workspace / ".harness" / "tasks").resolve(),
            "current task_dir",
        )
        contract = load_json_object(current_dir / "plan-contract.json", "current plan-contract")
        if contract.get("task_id") != current_id:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                "active-task.task_id 与当前 plan-contract 不一致。",
            )
    except ActiveTaskError as exc:
        result = unknown_classification(
            target_id,
            target_relative,
            exc,
            current_task_id=current_id,
        )
        result["current_task_dir"] = current_relative
        return result

    if current_id == target_id and current_dir == target_dir:
        return {
            "state": "same-task",
            "target_task_id": target_id,
            "target_task_dir": target_relative,
            "current_task_id": current_id,
            "current_task_dir": current_relative,
            "current_lifecycle": None,
            "reason": "active pointer 已指向目标任务",
        }
    if current_id == target_id or current_dir == target_dir:
        error = ActiveTaskError(
            "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
            "current 与 target 的 task ID/path 发生部分匹配冲突。",
        )
        result = unknown_classification(
            target_id,
            target_relative,
            error,
            current_task_id=current_id,
        )
        result["current_task_dir"] = current_relative
        return result

    try:
        run_state_path = resolve_relative(
            current_dir,
            str(pointer["run_state_path"]),
            current_dir,
            "current run-state",
        )
        run_state = load_json_object(run_state_path, "current run-state")
        if run_state.get("task_id") != current_id:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                "current run-state.task_id 与 pointer 不一致。",
            )
        lifecycle = run_state.get("lifecycle")
        if lifecycle not in ACTIVE_LIFECYCLES | TERMINAL_LIFECYCLES:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                f"current lifecycle 无效：{lifecycle}",
            )
    except ActiveTaskError as exc:
        result = unknown_classification(
            target_id,
            target_relative,
            exc,
            current_task_id=current_id,
        )
        result["current_task_dir"] = current_relative
        return result

    state = "different-terminal" if lifecycle in TERMINAL_LIFECYCLES else "different-nonterminal"
    return {
        "state": state,
        "target_task_id": target_id,
        "target_task_dir": target_relative,
        "current_task_id": current_id,
        "current_task_dir": current_relative,
        "current_lifecycle": lifecycle,
        "reason": f"current lifecycle={lifecycle}",
    }


def rfc3339_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def write_pointer_atomic(path: Path, pointer: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(pointer, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_WRITE_FAILED",
            f"无法原子写入 active pointer：{exc}",
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def pointer_document(classification: dict[str, Any]) -> dict[str, str]:
    return {
        "task_id": str(classification["target_task_id"]),
        "task_dir": str(classification["target_task_dir"]),
        "run_state_path": "run-state.json",
        "updated_at": rfc3339_now(),
    }


def activate_or_switch(
    workspace_arg: str | Path,
    task_dir_arg: str | Path,
    mode: str,
    expected_current_task_id: str | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_arg).resolve()
    classification = classify_active_pointer(workspace, task_dir_arg)
    state = str(classification["state"])
    current_id = classification.get("current_task_id")

    if mode not in {"activate", "switch"}:
        raise ActiveTaskError(
            "TASK_ACTIVE_POINTER_MODE_INVALID",
            f"不支持的写入模式：{mode}",
        )
    if mode == "switch":
        expected = (expected_current_task_id or "").strip()
        if not expected:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_SWITCH_EXPECTATION_REQUIRED",
                "显式 switch 必须提供 --expected-current-task-id。",
            )
        if not isinstance(current_id, str) or current_id != expected:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_SWITCH_CONFLICT",
                "active pointer 已变化或无法确认 current task ID；拒绝切换。",
            )

    if state == "same-task":
        result = dict(classification)
        result["action"] = "reused"
        return result

    if mode == "activate":
        if state == "different-nonterminal":
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_CONFLICT",
                "active pointer 指向非终态任务；请恢复该任务或显式 switch。",
            )
        if state == "different-unknown":
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                "active pointer 状态无法证明；请修复状态或显式 switch。",
            )
        if state not in {"missing", "different-terminal"}:
            raise ActiveTaskError(
                "TASK_ACTIVE_POINTER_STATE_UNKNOWN",
                f"不支持的 active pointer 分类：{state}",
            )

    pointer_path = workspace / ".harness" / "active-task.json"
    pointer = pointer_document(classification)
    write_pointer_atomic(pointer_path, pointer)
    result = dict(classification)
    result["action"] = "created" if state == "missing" else "replaced"
    result["pointer"] = pointer
    return result


def print_result(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"state={result['state']} action={result.get('action', 'classified')}")
    print(
        "target="
        f"{result['target_task_id']} current={result.get('current_task_id') or 'none'}"
    )
    print(f"reason={result['reason']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="安全分类、激活或显式切换 .harness/active-task.json。",
    )
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument("--task-dir", required=True, help="目标 managed task 目录")
    parser.add_argument(
        "--mode",
        choices=("classify", "activate", "switch"),
        default="classify",
    )
    parser.add_argument(
        "--expected-current-task-id",
        help="switch 的 compare-and-swap 预期 current task ID",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.mode == "classify":
            result = classify_active_pointer(args.workspace, args.task_dir)
            result["action"] = "classified"
        else:
            result = activate_or_switch(
                args.workspace,
                args.task_dir,
                args.mode,
                args.expected_current_task_id,
            )
    except ActiveTaskError as exc:
        failure = {"code": exc.code, "message": exc.message, "result": "failed"}
        if args.format == "json":
            print(json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(str(exc))
        return 2
    print_result(result, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
