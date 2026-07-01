#!/usr/bin/env python3
"""在已有 session 内执行 workflow JSON。"""

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
    parser = argparse.ArgumentParser(description="执行 verifier workflow。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="session 名称或 sessionId")
    parser.add_argument("--workflow", required=True, help="workflow JSON 文件绝对路径或 JSON 字符串")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workflow = read_json_arg(args.workflow, "--workflow")
        if not isinstance(workflow, dict):
            raise EVError("--workflow must resolve to a JSON object")
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/workflows/run", {"session": args.session, "workflow": workflow}, timeout=600.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
