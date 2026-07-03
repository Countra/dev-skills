#!/usr/bin/env python3
"""pending 审核包生成和校验工具。"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from ev_common import EVConfig, EVError, read_json, write_json


DETACHED_FLAGS = {"detour", "wrongPage", "unrelated", "recoveryOnly"}


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "run"


def pending_dir_for(config: EVConfig, session_name: str, run_name: str) -> Path:
    path = config.pending_dir / safe_slug(session_name) / safe_slug(run_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def step_payload(step: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "snapshot",
        "screenshot",
        "clickText",
        "clickXY",
        "fillText",
        "pressKey",
        "extractText",
        "extractTable",
        "waitText",
        "waitUrlContains",
        "evaluate",
        "collectConsole",
        "collectExceptions",
        "collectNetwork",
        "domSnapshot",
        "accessibilitySnapshot",
    ):
        if key in step:
            return {"action": key, "value": step[key]}
    return {"action": str(step.get("action") or "unknown"), "value": None}


def step_flags(step: dict[str, Any]) -> set[str]:
    flags: set[str] = set()
    raw_flags = step.get("persistence")
    if isinstance(raw_flags, str):
        flags.add(raw_flags)
    elif isinstance(raw_flags, list):
        flags.update(str(item) for item in raw_flags)
    if step.get("detour") is True:
        flags.add("detour")
    if step.get("wrongPage") is True:
        flags.add("wrongPage")
    if step.get("unrelated") is True:
        flags.add("unrelated")
    if step.get("recoveryOnly") is True:
        flags.add("recoveryOnly")
    return flags


def is_detour_step(step: dict[str, Any]) -> bool:
    return bool(step_flags(step) & DETACHED_FLAGS)


def clean_step(step: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(step)
    for key in ("persistence", "detour", "wrongPage", "unrelated", "recoveryOnly", "detourReason"):
        cleaned.pop(key, None)
    return cleaned


def split_steps(steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    correct: list[dict[str, Any]] = []
    detours: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if is_detour_step(step):
            detours.append(
                {
                    "index": index,
                    "id": step.get("id") or f"step-{index}",
                    "flags": sorted(step_flags(step)),
                    "reason": step.get("detourReason") or step.get("reason") or "marked as detour",
                    "step": step,
                }
            )
        else:
            correct.append(clean_step(step))
    return correct, detours


def workflow_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps = workflow.get("steps")
    return [dict(item) for item in steps if isinstance(item, dict)] if isinstance(steps, list) else []


def proposed_workflow(workflow: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    proposed = dict(workflow)
    correct, detours = split_steps(workflow_steps(workflow))
    proposed["steps"] = correct
    proposed.pop("learn", None)
    return proposed, detours


def describe_action(action: str, value: Any) -> str:
    if action == "waitText":
        text = value.get("text") if isinstance(value, dict) else value
        return f"等待页面出现文本：{text}"
    if action == "waitUrlContains":
        text = value.get("text") if isinstance(value, dict) else value
        return f"等待 URL 包含：{text}"
    if action == "clickText":
        if isinstance(value, dict):
            suffix = f"，匹配序号 {value.get('index')}" if value.get("index") is not None else ""
            return f"点击可见文本：{value.get('text')}{suffix}"
        return f"点击可见文本：{value}"
    if action == "clickXY" and isinstance(value, dict):
        return f"点击坐标：({value.get('x')}, {value.get('y')})"
    if action == "fillText" and isinstance(value, dict):
        return f"在输入框填写内容：selector={value.get('selector')}"
    if action == "pressKey":
        key = value.get("key") if isinstance(value, dict) else value
        return f"按键：{key}"
    if action == "snapshot":
        return "采集当前页面 DOM 文本和元素快照"
    if action == "screenshot":
        return f"截图：{value}"
    if action == "extractText":
        name = value.get("name") if isinstance(value, dict) else value
        return f"抽取页面文本：{name}"
    if action == "extractTable":
        name = value.get("name") if isinstance(value, dict) else value
        return f"抽取表格或列表：{name}"
    if action in {"collectConsole", "collectExceptions", "collectNetwork", "domSnapshot", "accessibilitySnapshot"}:
        return f"采集诊断证据：{action}"
    if action == "evaluate":
        return "执行显式 JavaScript 评估（需要重点确认）"
    return f"执行动作：{action}"


def review_lines(report: dict[str, Any], workflow: dict[str, Any], detours: list[dict[str, Any]], pending_dir: Path) -> list[str]:
    lines = [
        "# UI 验证流程待确认",
        "",
        "## 正确路径",
        "",
    ]
    steps = workflow_steps(workflow)
    if not steps:
        lines.append("- 未生成可持久化步骤，需要重新验证。")
    for index, step in enumerate(steps, start=1):
        payload = step_payload(step)
        lines.append(f"{index}. {describe_action(payload['action'], payload['value'])}")
    lines.extend(["", "## 已排除的错误路径", ""])
    if not detours:
        lines.append("- 未记录 detour。")
    for item in detours:
        lines.append(f"- {item.get('id')}: {item.get('reason')} ({', '.join(item.get('flags') or [])})")
    lines.extend(
        [
            "",
            "## 证据",
            "",
            f"- Report: {report.get('reportPath') or ''}",
            f"- Pending package: {pending_dir}",
            f"- Status: {report.get('status')}",
            "",
            "该流程当前只作为本轮验证证据，尚未保存为长期 workflow，也尚未写入知识库。",
            "注意：待保存的 workflow 只包含“正确路径”，不包含“已排除的错误路径”。",
            "",
            ">>> USER INPUT: EV-PERSIST-001 >>>",
            "Decision:",
            "Notes:",
            "<<< END <<<",
        ]
    )
    return lines


def write_pending_package(config: EVConfig, session_name: str, run_name: str, workflow: dict[str, Any], report: dict[str, Any], report_path: Path, summary_path: Path) -> dict[str, Any]:
    pending_dir = pending_dir_for(config, session_name, run_name)
    proposed, detours = proposed_workflow(workflow)
    report_for_review = dict(report)
    report_for_review["reportPath"] = str(report_path)
    evidence = {
        "schemaVersion": 1,
        "status": "pending_user_confirmation",
        "report": str(report_path),
        "summary": str(summary_path),
        "artifacts": report.get("artifacts") or [],
        "knowledgePreflight": report.get("knowledgePreflight"),
        "knowledgeUsage": report.get("knowledgeUsage"),
        "detourCount": len(detours),
        "detours": [{"id": item.get("id"), "reason": item.get("reason"), "flags": item.get("flags")} for item in detours],
    }
    write_json(pending_dir / "workflow.proposed.json", proposed)
    write_json(pending_dir / "evidence-index.json", evidence)
    if detours:
        write_json(pending_dir / "detours.json", {"schemaVersion": 1, "detours": detours})
    (pending_dir / "workflow-review.md").write_text("\n".join(review_lines(report_for_review, proposed, detours, pending_dir)) + "\n", encoding="utf-8")
    return {
        "status": "pending_user_confirmation",
        "path": str(pending_dir),
        "workflow": str(pending_dir / "workflow.proposed.json"),
        "review": str(pending_dir / "workflow-review.md"),
        "evidence": str(pending_dir / "evidence-index.json"),
        "detours": str(pending_dir / "detours.json") if detours else None,
        "detourCount": len(detours),
    }


def safe_pending_dir(config: EVConfig, pending: str) -> Path:
    path = Path(pending)
    if not path.is_absolute():
        raise EVError("--pending must be an absolute path")
    resolved = path.resolve()
    root = config.pending_dir.resolve()
    if root not in resolved.parents and resolved != root:
        raise EVError(f"pending package must be under {root}")
    if not resolved.exists() or not resolved.is_dir():
        raise EVError(f"pending package does not exist: {resolved}")
    return resolved


def validate_proposed_workflow(path: Path) -> dict[str, Any]:
    workflow = read_json(path)
    if not isinstance(workflow, dict):
        raise EVError("workflow.proposed.json must be an object")
    detour_steps = []
    for index, step in enumerate(workflow_steps(workflow), start=1):
        if is_detour_step(step):
            detour_steps.append(step.get("id") or f"step-{index}")
    if detour_steps:
        raise EVError(f"workflow.proposed.json still contains detour steps: {', '.join(map(str, detour_steps))}")
    return workflow


def approve_workflow(config: EVConfig, pending_dir: Path, session_name: str | None = None) -> Path:
    workflow = validate_proposed_workflow(pending_dir / "workflow.proposed.json")
    session = safe_slug(session_name or pending_dir.parent.name)
    target_dir = config.workflows_dir / session
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{pending_dir.name}.workflow.json"
    shutil.copyfile(pending_dir / "workflow.proposed.json", target)
    return target
