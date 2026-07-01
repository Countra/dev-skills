#!/usr/bin/env python3
"""检查 Electron verifier server 健康状态。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 electron-ui-verifier server /health。")
    add_common_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        print_json(request_json(config, "GET", "/health"))
        return 0
    except EVError as exc:
        return fail(str(exc), "health_failed")


if __name__ == "__main__":
    raise SystemExit(main())
