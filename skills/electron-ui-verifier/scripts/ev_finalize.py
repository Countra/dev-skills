#!/usr/bin/env python3
"""幂等 finalize verifier run，并一次生成 report/pending。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="finalize verifier run。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        result = request_json(config, "POST", "/runs/finalize", {"runId": args.run_id}, timeout=60.0)
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "finalize_failed")


if __name__ == "__main__":
    raise SystemExit(main())
