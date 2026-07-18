#!/usr/bin/env python3
"""读取有界 service 日志。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_context_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读取 managed process 日志")
    add_context_args(parser)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--service")
    selector.add_argument("--process-key")
    parser.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    parser.add_argument("--tail", type=int, default=80)
    parser.add_argument("--max-bytes", type=int, default=262144, help="最多读取 1 MiB")
    args = parser.parse_args(argv)

    def execute() -> int:
        status, value = make_client(args, timeout=10).request(
            "GET",
            "/processes/logs",
            params={
                "service": args.service,
                "processKey": args.process_key,
                "stream": args.stream,
                "tail": args.tail,
                "maxBytes": args.max_bytes,
            },
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.logs", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
