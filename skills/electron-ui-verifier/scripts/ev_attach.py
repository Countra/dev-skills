#!/usr/bin/env python3
"""创建或复用 Electron verifier session。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="attach 到 Electron CDP target。")
    add_common_args(parser)
    parser.add_argument("--name", required=True, help="稳定 session 名称")
    parser.add_argument("--cdp", required=True, help="CDP endpoint，例如 http://127.0.0.1:9223")
    parser.add_argument("--target-url-contains")
    parser.add_argument("--target-title-contains")
    parser.add_argument("--target-index", type=int)
    parser.add_argument("--target-type", default="page")
    parser.add_argument("--allow-remote-cdp", action="store_true", help="仅在另行批准 remote CDP 后使用；默认会被安全策略拒绝")
    parser.add_argument("--no-reuse", action="store_true", help="强制重新 attach 同名 session")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = {
            "name": args.name,
            "cdp": args.cdp,
            "targetType": args.target_type,
            "allowRemoteCdp": args.allow_remote_cdp,
            "reuse": not args.no_reuse,
        }
        if args.target_url_contains:
            payload["targetUrlContains"] = args.target_url_contains
        if args.target_title_contains:
            payload["targetTitleContains"] = args.target_title_contains
        if args.target_index is not None:
            payload["targetIndex"] = args.target_index
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/sessions/attach", payload)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "attach_failed")


if __name__ == "__main__":
    raise SystemExit(main())
