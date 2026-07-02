#!/usr/bin/env python3
"""在已有 session 内执行 workflow JSON。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ev_common import (
    EVError,
    add_common_args,
    fail,
    load_config,
    print_json,
    read_json_arg,
    request_json,
    resolve_config_path,
    result_exit_code,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 verifier workflow。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="session 名称或 sessionId")
    parser.add_argument("--workflow", required=True, help="workflow JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--learn", action="store_true", help="执行后从 report 显式学习候选知识")
    parser.add_argument("--learn-assets", action="store_true", help="配合 --learn 显式写入 action/workflow 资产")
    parser.add_argument("--learn-app-id", help="学习时覆盖 appId")
    parser.add_argument("--learn-notes", help="写入 knowledge evidence 的说明")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workflow = read_json_arg(args.workflow, "--workflow")
        if not isinstance(workflow, dict):
            raise EVError("--workflow must resolve to a JSON object")
        config = load_config(resolve_config_path(args))
        payload: dict[str, object] = {"session": args.session, "workflow": workflow}
        workflow_arg = Path(args.workflow)
        if workflow_arg.is_absolute() and workflow_arg.exists():
            payload["workflowSource"] = {"type": "file", "path": str(workflow_arg.resolve())}
        else:
            payload["workflowSource"] = {"type": "inline"}
        if args.learn or args.learn_assets:
            payload["learn"] = {"appId": args.learn_app_id, "notes": args.learn_notes, "includeAssets": bool(args.learn_assets)}
        result = request_json(config, "POST", "/workflows/run", payload, timeout=600.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
