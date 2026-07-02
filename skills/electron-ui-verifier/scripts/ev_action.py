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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行单个 verifier action。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="session 名称或 sessionId")
    parser.add_argument("--action", required=True, help="action JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--app-id", help="本轮验证所属应用 ID，用于知识库审计和默认回写")
    parser.add_argument("--goal", help="本轮 UI 验证目标，用于知识库审计和默认回写")
    parser.add_argument("--knowledge-preflight", help="知识库预检摘要 JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--knowledge-usage", help="实际使用的知识库候选摘要 JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--learn", action="store_true", help="执行成功或失败后从 report 学习基础候选知识")
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
        step = read_json_arg(args.action, "--action")
        if not isinstance(step, dict):
            raise EVError("--action must resolve to a JSON object")
        config = load_config(resolve_config_path(args))
        payload: dict[str, object] = {"session": args.session, "action": step}
        action_arg = Path(args.action)
        if action_arg.is_absolute() and action_arg.exists():
            payload["actionSource"] = {"type": "file", "path": str(action_arg.resolve())}
        else:
            payload["actionSource"] = {"type": "inline"}
        if args.app_id:
            payload["appId"] = args.app_id
        if args.goal:
            payload["goal"] = args.goal
        if args.knowledge_preflight:
            payload["knowledgePreflight"] = read_json_arg(args.knowledge_preflight, "--knowledge-preflight")
        if args.knowledge_usage:
            payload["knowledgeUsage"] = read_json_arg(args.knowledge_usage, "--knowledge-usage")
        should_learn = (args.learn or args.learn_assets or args.app_id or args.goal) and not args.no_learn
        if should_learn:
            payload["learn"] = {
                "appId": args.learn_app_id or args.app_id,
                "notes": args.learn_notes or args.goal,
                "includeAssets": bool(args.learn_assets),
            }
        elif args.no_learn:
            payload["knowledgeWriteback"] = {"status": "skipped", "reason": "--no-learn"}
        result = request_json(config, "POST", "/actions/run", payload, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "action_failed")


if __name__ == "__main__":
    raise SystemExit(main())
