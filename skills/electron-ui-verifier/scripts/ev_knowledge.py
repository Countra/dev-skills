#!/usr/bin/env python3
"""查询、组合和校验 current canonical knowledge。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json_arg, request_json, resolve_config_path, result_exit_code


def add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-version")
    parser.add_argument("--screen-digest")
    parser.add_argument("--pre-state")
    parser.add_argument("--max-risk", choices=("low", "medium", "high"), default="low")


def context_payload(args: argparse.Namespace) -> dict[str, object]:
    result: dict[str, object] = {"appId": args.app_id, "maxRisk": args.max_risk}
    for key, value in (
        ("appVersion", args.app_version),
        ("screenDigest", args.screen_digest),
        ("preState", args.pre_state),
    ):
        if value:
            result[key] = value
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 current canonical knowledge；低置信结果会明确 abstain。")
    add_common_args(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="执行 hybrid retrieval")
    add_context_args(search)
    search.add_argument("--query", required=True)
    search.add_argument("--kind", choices=("action", "workflow"))
    search.add_argument("--limit", type=int, default=3)
    search.add_argument("--min-score", type=float, default=0.62)
    search.add_argument("--min-margin", type=float, default=0.05)
    search.add_argument("--explain", action="store_true")
    compose = commands.add_parser("compose", help="按显式子目标组合状态兼容 action assets")
    add_context_args(compose)
    compose.add_argument("--goal")
    compose.add_argument("--subgoal", action="append", required=True)
    compose.add_argument("--bindings", help="参数绑定 JSON 文件绝对路径或 JSON 字符串")
    commands.add_parser("stats", help="输出 current index 计数")
    commands.add_parser("verify", help="校验 canonical 与 derived index")
    commands.add_parser("rebuild", help="从 canonical 重建 derived index")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.command == "search":
            payload = context_payload(args)
            payload.update(
                {
                    "query": args.query,
                    "kind": args.kind,
                    "limit": args.limit,
                    "minScore": args.min_score,
                    "minMargin": args.min_margin,
                    "explain": args.explain,
                }
            )
            result = request_json(config, "POST", "/knowledge/search", payload)
        elif args.command == "compose":
            payload = context_payload(args)
            payload.update({"goal": args.goal, "subgoals": args.subgoal})
            if args.bindings:
                payload["bindings"] = read_json_arg(args.bindings, "--bindings")
            result = request_json(config, "POST", "/knowledge/compose", payload)
        elif args.command == "stats":
            result = request_json(config, "GET", "/knowledge/stats")
        elif args.command == "verify":
            result = request_json(config, "GET", "/knowledge/verify")
        else:
            result = request_json(config, "POST", "/knowledge/rebuild", {})
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "knowledge_failed")


if __name__ == "__main__":
    raise SystemExit(main())
