#!/usr/bin/env python3
"""为 compact Executor 状态提供路径、校验和原子存储。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLANNER_SCRIPTS = Path(__file__).resolve().parents[2] / "complex-coding-planner" / "scripts"
sys.path.insert(0, str(PLANNER_SCRIPTS))

from harness_contract import contract_maps, load_contract  # noqa: E402
from harness_plan_check import validate_task  # noqa: E402


LIFECYCLES = {
    "approved",
    "in_progress",
    "blocked",
    "awaiting_reapproval",
    "completed",
}


class StateError(Exception):
    """表示状态操作违反任务、批准或恢复边界。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TaskBundle:
    workspace: Path
    task_dir: Path
    contract: dict[str, Any]
    plan_path: Path
    contract_path: Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_workspace(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise StateError(
            "TASK_WORKSPACE_INVALID",
            "workspace 不存在或不可访问。",
        ) from exc
    if not resolved.is_dir():
        raise StateError("TASK_WORKSPACE_INVALID", "workspace 必须是目录。")
    return resolved


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError("TASK_FILE_MISSING", f"缺少 {label}：{path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError("TASK_FILE_INVALID", f"无法读取 {label}：{path}") from exc
    if not isinstance(value, dict):
        raise StateError("TASK_FILE_INVALID", f"{label} 根节点必须是 object。")
    return value


def _resolve_task_dir(
    workspace: Path,
    raw_task_dir: str | None,
) -> tuple[Path, str | None]:
    expected_task_id: str | None = None
    raw = raw_task_dir
    if raw is None:
        pointer = load_object(
            workspace / ".harness" / "active-task.json",
            "active-task.json",
        )
        raw = pointer.get("task_dir")
        expected_task_id = pointer.get("task_id")
        if not isinstance(raw, str) or not raw:
            raise StateError("TASK_POINTER_INVALID", "active-task.task_dir 无效。")
        if not isinstance(expected_task_id, str) or not expected_task_id:
            raise StateError("TASK_POINTER_INVALID", "active-task.task_id 无效。")

    candidate = Path(raw)
    if not candidate.is_absolute() and ".." in candidate.parts:
        raise StateError("TASK_PATH_INVALID", "task-dir 不能包含 ..。")
    try:
        resolved = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (workspace / candidate).resolve(strict=False)
        )
        task_root = (workspace / ".harness" / "tasks").resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise StateError("TASK_PATH_INVALID", "task-dir 无法安全解析。") from exc
    try:
        task_root.relative_to(workspace)
        resolved.relative_to(task_root)
    except ValueError as exc:
        raise StateError(
            "TASK_PATH_INVALID",
            "task-dir 与任务根目录必须位于 workspace 内。",
        ) from exc
    if not resolved.is_dir():
        raise StateError("TASK_PATH_INVALID", f"task-dir 不存在：{resolved}")
    return resolved, expected_task_id


def load_bundle(workspace_path: Path, raw_task_dir: str | None) -> TaskBundle:
    workspace = resolve_workspace(workspace_path)
    task_dir, expected_task_id = _resolve_task_dir(workspace, raw_task_dir)
    issues = validate_task(task_dir, "approval")
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        detail = "; ".join(f"{item.code}: {item.message}" for item in errors[:3])
        raise StateError("TASK_PLAN_INVALID", detail)
    plan_path = task_dir / "execution-plan.md"
    contract_path = task_dir / "plan-contract.json"
    contract, contract_issues = load_contract(contract_path)
    if any(issue.severity == "error" for issue in contract_issues):
        raise StateError("TASK_PLAN_INVALID", contract_issues[0].message)
    if expected_task_id and contract.get("task_id") != expected_task_id:
        raise StateError(
            "TASK_ID_MISMATCH",
            "active pointer 与 plan-contract 的 task_id 不一致。",
        )
    return TaskBundle(workspace, task_dir, contract, plan_path, contract_path)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                value.update(chunk)
    except OSError as exc:
        raise StateError("TASK_DIGEST_FAILED", f"无法计算 {path.name} digest。") from exc
    return value.hexdigest()


def write_state(task_dir: Path, state: dict[str, Any]) -> None:
    path = task_dir / "run-state.json"
    state["updated_at"] = now()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
    except OSError as exc:
        raise StateError(
            "TASK_STATE_WRITE_FAILED",
            "无法创建 run-state.json 的原子写入临时文件。",
        ) from exc
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise StateError(
            "TASK_STATE_WRITE_FAILED",
            "无法原子写入 run-state.json。",
        ) from exc


def load_state(task_dir: Path, *, required: bool = True) -> dict[str, Any] | None:
    path = task_dir / "run-state.json"
    if not path.exists() and not required:
        return None
    state = load_object(path, "run-state.json")
    if state.get("lifecycle") not in LIFECYCLES:
        raise StateError("TASK_STATE_INVALID", "run-state.lifecycle 无效。")
    revision = state.get("state_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise StateError("TASK_STATE_INVALID", "run-state.state_revision 无效。")
    task_id = state.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise StateError("TASK_STATE_INVALID", "run-state.task_id 无效。")
    plan_revision = state.get("plan_revision")
    if (
        isinstance(plan_revision, bool)
        or not isinstance(plan_revision, int)
        or plan_revision < 1
    ):
        raise StateError("TASK_STATE_INVALID", "run-state.plan_revision 无效。")
    current = state.get("current_stage_id")
    if current is not None and not isinstance(current, str):
        raise StateError("TASK_STATE_INVALID", "run-state.current_stage_id 无效。")
    if not isinstance(state.get("next_action"), str):
        raise StateError("TASK_STATE_INVALID", "run-state.next_action 无效。")
    blocker = state.get("blocker")
    if blocker is not None and not isinstance(blocker, str):
        raise StateError("TASK_STATE_INVALID", "run-state.blocker 无效。")
    if not isinstance(state.get("updated_at"), str) or not state["updated_at"]:
        raise StateError("TASK_STATE_INVALID", "run-state.updated_at 无效。")
    approval = state.get("approval")
    if approval is not None and not isinstance(approval, dict):
        raise StateError("TASK_STATE_INVALID", "run-state.approval 无效。")
    if state["lifecycle"] == "awaiting_reapproval":
        if approval is not None:
            raise StateError(
                "TASK_STATE_INVALID",
                "awaiting_reapproval 状态不能保留旧批准。",
            )
    elif not isinstance(approval, dict):
        raise StateError(
            "TASK_STATE_INVALID",
            "已启动的任务必须包含 approval。",
        )
    for name in (
        "completed_stage_ids",
        "completed_stage_signatures",
        "validations",
        "reviews",
        "authorizations",
    ):
        expected = list if name == "completed_stage_ids" else dict
        if not isinstance(state.get(name), expected):
            raise StateError("TASK_STATE_INVALID", f"run-state.{name} 无效。")
    if not all(isinstance(item, str) for item in state["completed_stage_ids"]):
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.completed_stage_ids 必须只包含字符串。",
        )
    signatures = state["completed_stage_signatures"]
    if any(
        not isinstance(stage_id, str)
        or not isinstance(signature, str)
        or len(signature) != 64
        or any(character not in "0123456789abcdef" for character in signature)
        for stage_id, signature in signatures.items()
    ):
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.completed_stage_signatures 无效。",
        )
    for validation_id, record in state["validations"].items():
        if not isinstance(record, dict) or record.get("result") not in {
            "passed",
            "failed",
            "not-run",
        }:
            raise StateError(
                "TASK_STATE_INVALID",
                f"run-state.validations.{validation_id} 无效。",
            )
    for scope, record in state["reviews"].items():
        if not isinstance(record, dict) or record.get("mode") not in {
            "same-context",
            "independent",
        } or record.get("verdict") not in {
            "passed",
            "changes-required",
            "blocked",
        }:
            raise StateError(
                "TASK_STATE_INVALID",
                f"run-state.reviews.{scope} 无效。",
            )
    authorizations = state["authorizations"]
    if set(authorizations) != {"commit", "external_write", "elevated_tool"} or any(
        not isinstance(authorizations.get(name), bool)
        for name in ("commit", "external_write", "elevated_tool")
    ):
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.authorizations 无效。",
        )
    return state


def assert_identity(state: dict[str, Any], bundle: TaskBundle) -> None:
    if state.get("task_id") != bundle.contract.get("task_id"):
        raise StateError(
            "TASK_ID_MISMATCH",
            "run-state 与 plan-contract 的 task_id 不一致。",
        )
    if state.get("plan_revision") != bundle.contract.get("plan_revision"):
        raise StateError(
            "TASK_PLAN_STALE",
            "plan revision 已变化，需要重新批准。",
        )
    stages, validations = contract_maps(bundle.contract)
    completed = state.get("completed_stage_ids", [])
    completed_set = set(completed)
    if len(completed) != len(completed_set) or not completed_set <= set(stages):
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.completed_stage_ids 包含重复或未知阶段。",
        )
    signatures = state.get("completed_stage_signatures", {})
    if set(signatures) != completed_set:
        raise StateError(
            "TASK_STATE_INVALID",
            "已完成阶段与 completed_stage_signatures 不一致。",
        )
    for stage_id in completed:
        if signatures[stage_id] != stage_signature(bundle.contract, stage_id):
            raise StateError(
                "TASK_PLAN_STALE",
                f"已完成阶段 {stage_id} 的执行边界已变化，需要重新批准。",
            )
    for stage_id in completed:
        if not set(stages[stage_id]["depends_on"]) <= completed_set:
            raise StateError(
                "TASK_STATE_INVALID",
                f"已完成阶段 {stage_id} 的依赖尚未完成。",
            )
    current = state.get("current_stage_id")
    if current is not None and (current not in stages or current in completed):
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.current_stage_id 无效。",
        )
    lifecycle = state.get("lifecycle")
    if lifecycle == "in_progress" and current is None:
        raise StateError(
            "TASK_STATE_INVALID",
            "in_progress 状态必须有 current stage。",
        )
    if lifecycle in {"approved", "awaiting_reapproval", "completed"} and current is not None:
        raise StateError(
            "TASK_STATE_INVALID",
            f"{lifecycle} 状态不能保留 current stage。",
        )
    if lifecycle == "completed" and set(completed) != set(stages):
        raise StateError(
            "TASK_STATE_INVALID",
            "completed 状态仍有未完成阶段。",
        )
    validation_records = state.get("validations", {})
    if not set(validation_records) <= set(validations):
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.validations 包含未知验证。",
        )
    active_scopes = completed_set | ({current} if current else set())
    for validation_id in validation_records:
        owner = validations[validation_id]["stage_id"]
        if owner == "final":
            valid_owner = (
                completed_set == set(stages)
                and validation_id in bundle.contract.get("final_validation_ids", [])
            )
        else:
            valid_owner = owner in active_scopes
        if not valid_owner:
            raise StateError(
                "TASK_STATE_INVALID",
                f"run-state.validations.{validation_id} 与当前阶段状态不一致。",
            )
    review_records = state.get("reviews", {})
    if not set(review_records) <= {*stages, "final"}:
        raise StateError(
            "TASK_STATE_INVALID",
            "run-state.reviews 包含未知 scope。",
        )
    for scope in review_records:
        if scope != "final" and scope not in active_scopes:
            raise StateError(
                "TASK_STATE_INVALID",
                f"run-state.reviews.{scope} 与当前阶段状态不一致。",
            )
        if scope == "final" and completed_set != set(stages):
            raise StateError(
                "TASK_STATE_INVALID",
                "阶段未全部完成时不能存在 final review。",
            )
        if scope == "final":
            for validation_id in bundle.contract.get("final_validation_ids", []):
                definition = validations[validation_id]
                record = validation_records.get(validation_id)
                if definition["required"] and (
                    not isinstance(record, dict) or record.get("result") != "passed"
                ):
                    raise StateError(
                        "TASK_STATE_INVALID",
                        f"final review 缺少通过的必需验证 {validation_id}。",
                    )
    for stage_id in completed:
        stage = stages[stage_id]
        for validation_id in stage["validation_ids"]:
            definition = validations[validation_id]
            record = validation_records.get(validation_id)
            if definition["required"] and (
                not isinstance(record, dict) or record.get("result") != "passed"
            ):
                raise StateError(
                    "TASK_STATE_INVALID",
                    f"已完成阶段 {stage_id} 缺少通过的必需验证 {validation_id}。",
                )
        requirement = stage["review"]
        review = review_records.get(stage_id)
        if requirement != "none" and (
            not isinstance(review, dict) or review.get("verdict") != "passed"
        ):
            raise StateError(
                "TASK_STATE_INVALID",
                f"已完成阶段 {stage_id} 缺少通过的审查。",
            )
        if requirement == "independent" and review.get("mode") != "independent":
            raise StateError(
                "TASK_STATE_INVALID",
                f"已完成阶段 {stage_id} 缺少 independent 审查。",
            )
    if lifecycle == "completed":
        final_review = review_records.get("final")
        if not isinstance(final_review, dict) or final_review.get("verdict") != "passed":
            raise StateError(
                "TASK_STATE_INVALID",
                "completed 状态缺少通过的 final review。",
            )
        if (
            bundle.contract["final_review"] == "independent"
            and final_review.get("mode") != "independent"
        ):
            raise StateError(
                "TASK_STATE_INVALID",
                "completed 状态缺少 independent final review。",
            )


def assert_approval_current(state: dict[str, Any], bundle: TaskBundle) -> None:
    approval = state.get("approval")
    if not isinstance(approval, dict) or approval.get("implementation") is not True:
        raise StateError("TASK_APPROVAL_REQUIRED", "当前任务没有有效实施批准。")
    if approval.get("plan_sha256") != digest(bundle.plan_path):
        raise StateError(
            "TASK_PLAN_STALE",
            "execution-plan.md 已在批准后变化，需要重新批准。",
        )
    if approval.get("contract_sha256") != digest(bundle.contract_path):
        raise StateError(
            "TASK_PLAN_STALE",
            "plan-contract.json 已在批准后变化，需要重新批准。",
        )
    if state.get("lifecycle") == "awaiting_reapproval":
        raise StateError(
            "TASK_APPROVAL_REQUIRED",
            "当前任务正在等待重新批准。",
        )


def compact_summary(value: str, label: str, *, limit: int = 600) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise StateError("TASK_SUMMARY_INVALID", f"{label} 不能为空。")
    if len(normalized) > limit:
        raise StateError(
            "TASK_SUMMARY_INVALID",
            f"{label} 不能超过 {limit} 个字符。",
        )
    return normalized


def stage_signature(contract: dict[str, Any], stage_id: str) -> str:
    """绑定影响阶段复用正确性的最小 contract 片段。"""

    stages, validations = contract_maps(contract)
    stage = stages[stage_id]
    value = {
        "id": stage["id"],
        "depends_on": stage["depends_on"],
        "scope": stage["scope"],
        "risk": stage["risk"],
        "validation_ids": stage["validation_ids"],
        "review": stage["review"],
        "validations": [
            validations[validation_id]
            for validation_id in stage["validation_ids"]
        ],
    }
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stage_order(contract: dict[str, Any]) -> list[str]:
    return [str(item["id"]) for item in contract.get("stages", [])]


def next_stage(contract: dict[str, Any], completed: list[str]) -> str | None:
    stages, _ = contract_maps(contract)
    completed_set = set(completed)
    for stage_id in stage_order(contract):
        if stage_id in completed_set:
            continue
        if set(stages[stage_id]["depends_on"]) <= completed_set:
            return stage_id
    return None
