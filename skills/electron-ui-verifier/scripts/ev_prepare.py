#!/usr/bin/env python3
"""准备 Electron UI 验证 run，并确保 session 实时可用。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json_arg, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="准备 verifier run。")
    add_common_args(parser)
    parser.add_argument("--session", required=True, help="稳定 session 名称")
    parser.add_argument("--cdp", help="首次 attach 或重新连接时使用的 loopback CDP endpoint")
    parser.add_argument("--app-id")
    parser.add_argument("--goal")
    parser.add_argument("--alias", action="append", default=[], help="知识检索别名，可重复，最多 50 项")
    parser.add_argument("--app-version", help="用于资产版本硬过滤")
    parser.add_argument("--screen-digest", help="用于资产屏幕指纹硬过滤")
    parser.add_argument("--pre-state", help="用于资产前置状态硬过滤")
    parser.add_argument("--max-risk", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--parameter-schema", help="可复用参数 schema JSON 文件绝对路径或 JSON 字符串")
    parser.add_argument("--target-url-contains")
    parser.add_argument("--target-title-contains")
    parser.add_argument("--target-index", type=int)
    parser.add_argument("--target-id")
    parser.add_argument("--no-reuse", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload: dict[str, object] = {"session": args.session, "reuse": not args.no_reuse}
        for key, value in (
            ("cdp", args.cdp),
            ("appId", args.app_id),
            ("goal", args.goal),
            ("appVersion", args.app_version),
            ("screenDigest", args.screen_digest),
            ("preState", args.pre_state),
            ("maxRisk", args.max_risk),
            ("targetUrlContains", args.target_url_contains),
            ("targetTitleContains", args.target_title_contains),
            ("targetIndex", args.target_index),
            ("targetId", args.target_id),
        ):
            if value not in (None, ""):
                payload[key] = value
        if args.parameter_schema:
            payload["parameterSchema"] = read_json_arg(args.parameter_schema, "--parameter-schema")
        if args.alias:
            payload["aliases"] = args.alias
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/runs/prepare", payload, timeout=60.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "prepare_failed")


if __name__ == "__main__":
    raise SystemExit(main())
