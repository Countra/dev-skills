#!/usr/bin/env python3
"""通过 manager 启动 service。"""

from __future__ import annotations

import argparse
from pathlib import Path

from process_manager.cli import add_common_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通过 manager 启动 service")
    add_common_args(parser)
    parser.add_argument("--service", required=True, help="service JSON 路径")
    args = parser.parse_args(argv)

    def execute() -> int:
        service_path = Path(args.service).resolve()
        status, value = make_client(args.config).request(
            "POST",
            "/processes/start",
            {"servicePath": str(service_path)},
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.start", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
