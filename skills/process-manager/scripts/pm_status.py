#!/usr/bin/env python3
"""查看 service 或 processKey 状态。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_common_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="查看 managed process 状态")
    add_common_args(parser)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--service", help="service 名称")
    selector.add_argument("--process-key", help="processKey")
    args = parser.parse_args(argv)

    def execute() -> int:
        status, value = make_client(args.config, timeout=10).request(
            "GET",
            "/processes/status",
            params={"service": args.service, "processKey": args.process_key},
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.status", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
