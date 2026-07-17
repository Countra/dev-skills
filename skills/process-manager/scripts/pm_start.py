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
    ownership = parser.add_mutually_exclusive_group(required=True)
    ownership.add_argument("--session-id", help="绑定 open session")
    ownership.add_argument("--persistent", action="store_true", help="显式声明长驻 ownership")
    args = parser.parse_args(argv)

    def execute() -> int:
        service_path = Path(args.service).resolve()
        status, value = make_client(args.config).request(
            "POST",
            "/processes/start",
            {
                "servicePath": str(service_path),
                "sessionId": args.session_id,
                "persistent": args.persistent,
            },
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.start", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
