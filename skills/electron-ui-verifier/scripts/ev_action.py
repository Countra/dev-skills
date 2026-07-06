#!/usr/bin/env python3
"""在已有 session 内执行单个 Electron UI action。"""

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
from ev_asset_runner import load_action_asset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行单个 verifier action。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="session 名称或 sessionId")
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--action", help="action JSON 文件绝对路径或 JSON 字符串")
    action_group.add_argument("--action-id", help="知识库 action asset ID；命中可执行资产时优先使用")
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
        if args.action_id:
            step, action_source, asset_usage = load_action_asset(config, args.action_id)
        else:
            step = read_json_arg(args.action, "--action")
            if not isinstance(step, dict):
                raise EVError("--action must resolve to a JSON object")
            action_arg = Path(args.action)
            if action_arg.is_absolute() and action_arg.exists():
                action_source = {"type": "file", "path": str(action_arg.resolve())}
            else:
                action_source = {"type": "inline"}
        payload: dict[str, object] = {"session": args.session, "action": step}
        payload["actionSource"] = action_source
        if args.app_id:
            payload["appId"] = args.app_id
        if args.goal:
            payload["goal"] = args.goal
        if args.knowledge_preflight:
            payload["knowledgePreflight"] = read_json_arg(args.knowledge_preflight, "--knowledge-preflight")
        if args.knowledge_usage:
            payload["knowledgeUsage"] = read_json_arg(args.knowledge_usage, "--knowledge-usage")
        elif asset_usage:
            payload["knowledgeUsage"] = asset_usage
        if args.no_learn:
            payload["knowledgeWriteback"] = {"status": "skipped", "reason": "--no-learn"}
        result = request_json(config, "POST", "/actions/run", payload, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "action_failed")


if __name__ == "__main__":
    raise SystemExit(main())
