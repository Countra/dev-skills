#!/usr/bin/env python3
"""预览并批准一次高风险 verifier mutation。"""

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
    parser = argparse.ArgumentParser(description="管理与 run/action/target 绑定的一次性风险授权。")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser("preview", help="生成不含动作原文和绑定值的风险预览。")
    preview.add_argument("--run-id", required=True)
    preview.add_argument("--action", required=True, help="typed action JSON 文件绝对路径或 JSON 字符串")

    approve = subparsers.add_parser("approve", help="用户确认风险后签发短期一次性 receipt。")
    approve.add_argument("--preview-id", required=True)
    approve.add_argument("--fingerprint", required=True)
    approve.add_argument("--note", required=True, help="本次用户授权的简短说明，不会以明文持久化")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.command == "preview":
            action = read_json_arg(args.action, "--action")
            if not isinstance(action, dict):
                raise EVError("--action 必须解析为 JSON object")
            result = request_json(
                config,
                "POST",
                "/risks/preview",
                {"runId": args.run_id, "action": action},
            )
        else:
            result = request_json(
                config,
                "POST",
                "/risks/approve",
                {
                    "previewId": args.preview_id,
                    "fingerprint": args.fingerprint,
                    "note": args.note,
                },
            )
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "risk_authorization_failed")


if __name__ == "__main__":
    raise SystemExit(main())
