#!/usr/bin/env python3
"""读取 verifier artifact 元数据。"""

from __future__ import annotations

import argparse
import urllib.parse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 artifact 元数据。")
    add_common_args(parser)
    parser.add_argument("--path", required=True, help="stateRoot 下 artifact 的绝对路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        query = urllib.parse.urlencode({"path": args.path})
        result = request_json(config, "GET", f"/artifacts/get?{query}", timeout=60.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "artifact_failed")


if __name__ == "__main__":
    raise SystemExit(main())
