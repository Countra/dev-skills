#!/usr/bin/env python3
"""在已有 session 内执行单个 Electron UI action。"""

from __future__ import annotations

import argparse

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
    parser.add_argument("--learn", action="store_true", help="执行成功或失败后从 report 显式学习候选知识")
    parser.add_argument("--learn-app-id", help="学习时覆盖 appId")
    parser.add_argument("--learn-notes", help="写入 knowledge evidence 的说明")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        step = read_json_arg(args.action, "--action")
        if not isinstance(step, dict):
            raise EVError("--action must resolve to a JSON object")
        config = load_config(resolve_config_path(args))
        payload: dict[str, object] = {"session": args.session, "action": step}
        if args.learn:
            payload["learn"] = {"appId": args.learn_app_id, "notes": args.learn_notes}
        result = request_json(config, "POST", "/actions/run", payload, timeout=120.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "action_failed")


if __name__ == "__main__":
    raise SystemExit(main())
