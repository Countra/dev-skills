#!/usr/bin/env python3
"""等待 service readiness。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_common_args, make_client, output_remote, run_cli


MAX_SERVICE_READINESS_TIMEOUT_SECONDS = 600


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="等待 managed process ready")
    add_common_args(parser)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--service")
    selector.add_argument("--process-key")
    parser.add_argument("--timeout", type=float, help="覆盖 readiness timeoutSeconds")
    args = parser.parse_args(argv)

    def execute() -> int:
        # 未覆盖时 manager 会采用 service 配置，transport 必须覆盖 schema 的完整上限。
        timeout = args.timeout if args.timeout is not None else MAX_SERVICE_READINESS_TIMEOUT_SECONDS
        status, value = make_client(args.config, timeout=timeout + 5).request(
            "POST",
            "/processes/ready",
            {"service": args.service, "processKey": args.process_key, "timeoutSeconds": args.timeout},
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.ready", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
