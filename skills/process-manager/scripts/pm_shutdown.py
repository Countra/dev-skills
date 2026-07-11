#!/usr/bin/env python3
"""通过认证控制面关闭 manager。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_common_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="关闭 process-manager")
    add_common_args(parser)
    args = parser.parse_args(argv)

    def execute() -> int:
        status, value = make_client(args.config, timeout=60).request("POST", "/shutdown", {})
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("shutdown", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
