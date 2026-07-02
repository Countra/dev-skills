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
    parser.add_argument("--app-id", help="本轮验证所属应用 ID，用于知识库审计和默认回写")
    parser.add_argument("--goal", help="本轮 UI 验证目标，用于知识库审计和默认回写")
    parser.add_argument("--knowledge-preflight", help="知识库预检摘要 JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--knowledge-usage", help="实际使用的知识库候选摘要 JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--learn", action="store_true", help="执行后从 report 学习基础候选知识")
    parser.add_argument("--no-learn", action="store_true", help="明确跳过基础知识回写；最终回复必须说明原因")
    parser.add_argument("--learn-assets", action="store_true", help="配合 --learn 显式写入 action/workflow 资产")
    parser.add_argument("--learn-app-id", help="学习时覆盖 appId")
    parser.add_argument("--learn-notes", help="写入 knowledge evidence 的说明")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.no_learn and (args.learn or args.learn_assets):
            raise EVError("--no-learn cannot be combined with --learn or --learn-assets")
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
        workflow_learn = workflow.get("learn")
        should_learn = (args.learn or args.learn_assets or app_id or goal or workflow_learn) and not args.no_learn
        if should_learn:
            learn_payload: dict[str, object] = {}
            if isinstance(workflow_learn, dict):
                learn_payload.update(workflow_learn)
            payload["learn"] = {
                "appId": args.learn_app_id or app_id or learn_payload.get("appId"),
                "notes": args.learn_notes or goal or learn_payload.get("notes"),
                "includeAssets": bool(args.learn_assets or learn_payload.get("includeAssets") or learn_payload.get("learnAssets")),
            }
        elif args.no_learn:
            payload["knowledgeWriteback"] = {"status": "skipped", "reason": "--no-learn"}
        result = request_json(config, "POST", "/workflows/run", payload, timeout=600.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
