#!/usr/bin/env python3
"""对完整目标和 agent 提供的子目标执行渐进式知识建议。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json_arg, request_json, resolve_config_path, result_exit_code
from ev_knowledge import add_context_args, context_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检索目标；不命中时返回 abstain，不补齐无关 recent assets。")
    add_common_args(parser)
    add_context_args(parser)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--subgoal", action="append", default=[], help="由 agent 明确提供，可重复，最多 20 个")
    parser.add_argument("--kind", choices=("action", "workflow"))
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--compose", action="store_true", help="仅对 subgoal 尝试状态安全组合")
    parser.add_argument("--bindings", help="组合所需参数绑定 JSON；值不会写入知识或输出")
    return parser


def _search(config, args: argparse.Namespace, goal: str) -> dict:
    payload = context_payload(args)
    payload.update({"query": goal, "kind": args.kind, "limit": 3, "explain": args.explain})
    return request_json(config, "POST", "/knowledge/search", payload)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if len(args.subgoal) > 20:
            raise EVError("--subgoal 最多提供 20 个")
        if args.compose and not args.subgoal:
            raise EVError("--compose 至少需要一个 --subgoal")
        config = load_config(resolve_config_path(args))
        direct = _search(config, args, args.goal)
        subgoals = [{"goal": goal, "retrieval": _search(config, args, goal)} for goal in args.subgoal]
        result: dict[str, object] = {"ok": direct.get("ok") is not False, "direct": direct, "subgoals": subgoals}
        result["ok"] = bool(result["ok"]) and all(item["retrieval"].get("ok") is not False for item in subgoals)
        if args.compose:
            payload = context_payload(args)
            payload.update({"goal": args.goal, "subgoals": args.subgoal})
            if args.bindings:
                payload["bindings"] = read_json_arg(args.bindings, "--bindings")
            composition = request_json(config, "POST", "/knowledge/compose", payload)
            result["composition"] = composition
            result["ok"] = bool(result["ok"]) and composition.get("ok") is not False
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "suggest_failed")


if __name__ == "__main__":
    raise SystemExit(main())
