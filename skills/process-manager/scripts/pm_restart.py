#!/usr/bin/env python3
"""由 manager 原子执行 stop 后 start。"""

from __future__ import annotations

import argparse
from pathlib import Path

from process_manager.cli import add_context_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重启 managed service")
    add_context_args(parser)
    parser.add_argument("--service", required=True, help="service JSON 路径")
    parser.add_argument("--timeout", type=float, help="ready timeout 覆盖")
    ownership = parser.add_mutually_exclusive_group()
    ownership.add_argument("--session-id", help="仅在没有 active run 时声明 session ownership")
    ownership.add_argument("--persistent", action="store_true", help="仅在没有 active run 时声明长驻 ownership")
    args = parser.parse_args(argv)

    def execute() -> int:
        ready_timeout = args.timeout if args.timeout is not None else 0
        status, value = make_client(args, timeout=ready_timeout + 320).request(
            "POST",
            "/processes/restart",
            {
                "servicePath": str(Path(args.service).resolve()),
                "timeoutSeconds": args.timeout,
                "sessionId": args.session_id,
                "persistent": args.persistent,
            },
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.restart", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
