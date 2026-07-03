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
from ev_asset_runner import load_workflow_asset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 verifier workflow。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="session 名称或 sessionId")
    workflow_group = parser.add_mutually_exclusive_group(required=True)
    workflow_group.add_argument("--workflow", help="workflow JSON 文件绝对路径或 JSON 字符串")
    workflow_group.add_argument("--workflow-id", help="知识库 workflow asset ID；命中可执行资产时优先使用")
    parser.add_argument("--app-id", help="本轮验证所属应用 ID，用于知识库审计和 pending 审核包")
    parser.add_argument("--goal", help="本轮 UI 验证目标，用于知识库审计和 pending 审核包")
    parser.add_argument("--knowledge-preflight", help="知识库预检摘要 JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--knowledge-usage", help="实际使用的知识库候选摘要 JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--learn", action="store_true", help="已废弃：请先让用户确认 pending 包，再使用 ev_persist.py approve")
    parser.add_argument("--no-learn", action="store_true", help="兼容旧参数；当前默认不写知识库")
    parser.add_argument("--learn-assets", action="store_true", help="已废弃：请在 ev_persist.py approve 时使用 --include-assets")
    parser.add_argument("--learn-app-id", help="兼容旧参数，当前忽略；请在 ev_persist.py approve 中指定 --app-id")
    parser.add_argument("--learn-notes", help="兼容旧参数，当前忽略；请在 ev_persist.py approve 中指定 --notes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.learn or args.learn_assets:
            raise EVError("--learn/--learn-assets 已废弃。请先执行验证生成 pending 审核包，用户确认后再运行 ev_persist.py approve。")
        config = load_config(resolve_config_path(args))
        asset_usage: dict[str, object] | None = None
        if args.workflow_id:
            workflow, workflow_source, asset_usage = load_workflow_asset(config, args.workflow_id)
        else:
            workflow = read_json_arg(args.workflow, "--workflow")
            if not isinstance(workflow, dict):
                raise EVError("--workflow must resolve to a JSON object")
            workflow_arg = Path(args.workflow)
            if workflow_arg.is_absolute() and workflow_arg.exists():
                workflow_source = {"type": "file", "path": str(workflow_arg.resolve())}
            else:
                workflow_source = {"type": "inline"}
        payload: dict[str, object] = {"session": args.session, "workflow": workflow}
        payload["workflowSource"] = workflow_source
        app_id = args.app_id or workflow.get("appId")
        goal = args.goal or workflow.get("goal")
        if app_id:
            payload["appId"] = app_id
        if goal:
            payload["goal"] = goal
        if args.knowledge_preflight:
            payload["knowledgePreflight"] = read_json_arg(args.knowledge_preflight, "--knowledge-preflight")
        if args.knowledge_usage:
            payload["knowledgeUsage"] = read_json_arg(args.knowledge_usage, "--knowledge-usage")
        elif asset_usage:
            payload["knowledgeUsage"] = asset_usage
        if args.no_learn:
            payload["knowledgeWriteback"] = {"status": "skipped", "reason": "--no-learn"}
        result = request_json(config, "POST", "/workflows/run", payload, timeout=600.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
