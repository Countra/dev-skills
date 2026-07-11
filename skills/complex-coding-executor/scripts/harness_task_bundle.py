#!/usr/bin/env python3
"""安全解析 pointer-only active task 和当前 task bundle。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness_time import parse_rfc3339


POINTER_FIELDS = {"task_id", "task_dir", "run_state_path", "updated_at"}
CONTRACT_MINIMUM_FIELDS = {"task_id", "plan_revision", "stages"}


class TaskBundleError(Exception):
    """task bundle 缺失、无效或越界。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


@dataclass(frozen=True)
class TaskBundle:
    workspace: Path
    pointer_path: Path
    task_dir: Path
    plan_path: Path
    contract_path: Path
    attestation_path: Path
    run_state_path: Path
    ledger_path: Path
    pointer: dict[str, Any] | None
    contract: dict[str, Any]

    @property
    def task_id(self) -> str:
        return str(self.contract["task_id"])

    @property
    def plan_revision(self) -> int:
        return int(self.contract["plan_revision"])


def load_json_object(path: Path, label: str, code_prefix: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskBundleError(f"{code_prefix}_MISSING", f"缺少 {label}：{path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TaskBundleError(
            f"{code_prefix}_INVALID_JSON",
            f"无法解析 {label}：{path}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise TaskBundleError(
            f"{code_prefix}_INVALID_TYPE",
            f"{label} 根节点必须是 object：{path}",
        )
    return value


def ensure_within(path: Path, parent: Path, label: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise TaskBundleError(
            "TASK_PATH_OUTSIDE_WORKSPACE",
            f"{label} 越出允许目录：{path}",
        ) from exc


def resolve_relative_path(base: Path, raw: str, parent: Path, label: str) -> Path:
    if not raw or "\x00" in raw:
        raise TaskBundleError("TASK_PATH_INVALID", f"{label} 为空或包含 null byte。")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    ensure_within(resolved, parent, label)
    return resolved


def validate_pointer(pointer: dict[str, Any], pointer_path: Path) -> None:
    unknown = sorted(set(pointer) - POINTER_FIELDS)
    missing = sorted(POINTER_FIELDS - set(pointer))
    if unknown:
        raise TaskBundleError(
            "TASK_POINTER_UNKNOWN_FIELD",
            f"active-task 包含运行状态或未知字段：{', '.join(unknown)}",
        )
    if missing:
        raise TaskBundleError(
            "TASK_POINTER_MISSING_FIELD",
            f"active-task 缺少字段：{', '.join(missing)}: {pointer_path}",
        )
    for field in POINTER_FIELDS:
        if not isinstance(pointer.get(field), str) or not pointer[field].strip():
            raise TaskBundleError(
                "TASK_POINTER_INVALID_FIELD",
                f"active-task.{field} 必须是非空字符串。",
            )
    for field in ("task_dir", "run_state_path"):
        candidate = Path(pointer[field])
        if candidate.is_absolute() or ".." in candidate.parts:
            raise TaskBundleError(
                "TASK_POINTER_INVALID_FIELD",
                f"active-task.{field} 必须是安全相对路径。",
            )
    try:
        parse_rfc3339(pointer["updated_at"])
    except ValueError as exc:
        raise TaskBundleError(
            "TASK_POINTER_INVALID_FIELD",
            "active-task.updated_at 必须是 RFC3339 时间。",
        ) from exc


def validate_contract_minimum(contract: dict[str, Any], path: Path) -> None:
    missing = sorted(CONTRACT_MINIMUM_FIELDS - set(contract))
    if missing:
        raise TaskBundleError(
            "TASK_CONTRACT_MISSING_FIELD",
            f"plan-contract 缺少字段：{', '.join(missing)}: {path}",
        )
    if not isinstance(contract.get("task_id"), str) or not contract["task_id"].strip():
        raise TaskBundleError(
            "TASK_CONTRACT_INVALID_FIELD",
            "plan-contract.task_id 必须是非空字符串。",
        )
    revision = contract.get("plan_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise TaskBundleError(
            "TASK_CONTRACT_INVALID_FIELD",
            "plan-contract.plan_revision 必须是从 1 开始的整数。",
        )
    if not isinstance(contract.get("stages"), list) or not contract["stages"]:
        raise TaskBundleError(
            "TASK_CONTRACT_INVALID_FIELD",
            "plan-contract.stages 必须是非空数组。",
        )


def resolve_task_bundle(
    workspace_arg: str | Path = ".",
    task_dir_arg: str | Path | None = None,
    *,
    require_attestation: bool = False,
) -> TaskBundle:
    if os.environ.get("HARNESS_DISABLED") == "1":
        raise TaskBundleError("HARNESS_DISABLED", "HARNESS_DISABLED=1")

    workspace = Path(workspace_arg).resolve()
    pointer_path = (workspace / ".harness" / "active-task.json").resolve()
    ensure_within(pointer_path, workspace, "active-task")
    pointer: dict[str, Any] | None = None
    if task_dir_arg is None:
        pointer = load_json_object(pointer_path, "active task pointer", "TASK_POINTER")
        validate_pointer(pointer, pointer_path)
        task_dir = resolve_relative_path(
            workspace,
            str(pointer["task_dir"]),
            workspace,
            "task_dir",
        )
    else:
        task_dir = resolve_relative_path(
            workspace,
            str(task_dir_arg),
            workspace,
            "task_dir",
        )

    if not task_dir.is_dir():
        raise TaskBundleError("TASK_DIR_MISSING", f"任务目录不存在：{task_dir}")
    plan_path = (task_dir / "execution-plan.md").resolve()
    contract_path = (task_dir / "plan-contract.json").resolve()
    ensure_within(plan_path, task_dir, "execution-plan")
    ensure_within(contract_path, task_dir, "plan-contract")
    if not plan_path.is_file():
        raise TaskBundleError("TASK_PLAN_MISSING", f"缺少 execution-plan.md：{plan_path}")
    contract = load_json_object(
        contract_path,
        "plan contract",
        "TASK_CONTRACT",
    )
    validate_contract_minimum(contract, contract_path)

    if pointer is not None and pointer["task_id"] != contract["task_id"]:
        raise TaskBundleError(
            "TASK_POINTER_CONTRACT_MISMATCH",
            "active-task.task_id 与 plan-contract.task_id 不一致。",
        )
    raw_run_state = str(pointer["run_state_path"]) if pointer else "run-state.json"
    run_state_path = resolve_relative_path(
        task_dir,
        raw_run_state,
        task_dir,
        "run-state",
    )
    attestation_path = (task_dir / "attestation.json").resolve()
    ledger_path = (task_dir / "ledger.jsonl").resolve()
    ensure_within(attestation_path, task_dir, "attestation")
    ensure_within(ledger_path, task_dir, "ledger")
    if require_attestation and not attestation_path.is_file():
        raise TaskBundleError(
            "ATTESTATION_MISSING",
            f"用户批准后必须先生成 attestation：{attestation_path}",
        )
    return TaskBundle(
        workspace=workspace,
        pointer_path=pointer_path,
        task_dir=task_dir,
        plan_path=plan_path,
        contract_path=contract_path,
        attestation_path=attestation_path,
        run_state_path=run_state_path,
        ledger_path=ledger_path,
        pointer=pointer,
        contract=contract,
    )
