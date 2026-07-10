#!/usr/bin/env python3
"""检查 manager 的平台无关健康状态。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_common_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 manager health")
    add_common_args(parser)
    args = parser.parse_args(argv)

    def execute() -> int:
        status, value = make_client(args.config, timeout=5).request("GET", "/health")
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("health", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
