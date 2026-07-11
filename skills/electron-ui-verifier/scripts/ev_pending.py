#!/usr/bin/env python3
"""预览 sealed pending bundle 的批准完整性和 fingerprint。"""

from __future__ import annotations

import argparse
import urllib.parse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验 verifier pending bundle；不执行写入。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        query = urllib.parse.urlencode({"runId": args.run_id})
        result = request_json(config, "GET", f"/pending/preview?{query}", timeout=30.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "pending_preview_failed")


if __name__ == "__main__":
    raise SystemExit(main())
