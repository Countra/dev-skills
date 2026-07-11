#!/usr/bin/env python3
"""executor 公共 CLI 的参数、JSON 和诊断 helpers。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_task_bundle import TaskBundle, resolve_task_bundle


class CliInputError(Exception):
    """CLI 条件参数或 JSON 输入无效。"""

    code = "CLI_INVALID_ARGUMENT"


def add_bundle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=".", help="workspace 根目录")
    parser.add_argument(
        "--task-dir",
        help="任务目录；省略时读取 pointer-only active-task.json",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
    )


def resolve_from_args(
    args: argparse.Namespace,
    *,
    require_attestation: bool,
) -> TaskBundle:
    return resolve_task_bundle(
        Path(args.workspace),
        Path(args.task_dir) if args.task_dir else None,
        require_attestation=require_attestation,
    )


def parse_json_object(value: str | None, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CliInputError(f"{label} 不是合法 JSON：{exc}") from exc
    if not isinstance(parsed, dict):
        raise CliInputError(f"{label} 必须解析为 object。")
    return parsed


def exception_diagnostic(exc: Exception) -> tuple[str, str]:
    code = getattr(exc, "code", type(exc).__name__)
    message = getattr(exc, "message", str(exc))
    return str(code), str(message)


def emit_success(
    action: str,
    result: dict[str, Any],
    output_format: str,
) -> None:
    payload = {"ok": True, "action": action, "result": result}
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"PASS: {action}")
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def emit_failure(action: str, exc: Exception, output_format: str) -> None:
    code, message = exception_diagnostic(exc)
    if output_format == "json":
        payload = {
            "ok": False,
            "action": action,
            "error": {"code": code, "message": message},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"FAIL [{code}]: {message}")
