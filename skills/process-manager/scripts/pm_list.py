#!/usr/bin/env python3
"""列出 current run；历史必须显式请求。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_context_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="列出 managed processes")
    add_context_args(parser)
    parser.add_argument("--history", action="store_true", help="包含有界历史记录")
    args = parser.parse_args(argv)

    def execute() -> int:
        status, value = make_client(args, timeout=10).request(
            "GET",
            "/processes",
            params={"history": "true" if args.history else "false"},
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.list", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
