#!/usr/bin/env python3
"""列出或读取 approved canonical action/workflow assets。"""

from __future__ import annotations

import argparse
import urllib.parse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 current canonical assets；不修改资产状态。")
    add_common_args(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--app-id")
    listing.add_argument("--kind", choices=("action", "workflow"))
    listing.add_argument("--limit", type=int, default=50)
    get = commands.add_parser("get")
    get.add_argument("--asset-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.command == "get":
            path = "/knowledge/assets/get?" + urllib.parse.urlencode({"assetId": args.asset_id})
        else:
            query = {"limit": args.limit}
            if args.app_id:
                query["appId"] = args.app_id
            if args.kind:
                query["kind"] = args.kind
            path = "/knowledge/assets?" + urllib.parse.urlencode(query)
        result = request_json(config, "GET", path)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "assets_failed")


if __name__ == "__main__":
    raise SystemExit(main())
