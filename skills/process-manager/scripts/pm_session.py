#!/usr/bin/env python3
"""管理 workspace-scoped session lease。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_common_args, make_client, output_remote, run_cli
from process_manager.errors import OperationConflictError
from process_manager.manager_lifecycle import ManagerConverger
from process_manager.protocol import print_json
from process_manager.runtime_context import resolve_runtime_context
from process_manager.sessions import DEFAULT_SESSION_TTL_SECONDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="打开、续租、查看或关闭 session")
    commands = parser.add_subparsers(dest="command", required=True)
    opened = commands.add_parser("open", help="创建 session")
    add_common_args(opened)
    opened.add_argument("--kind", choices=("validation", "task"), required=True)
    opened.add_argument("--ttl-seconds", type=int, default=DEFAULT_SESSION_TTL_SECONDS)
    opened.add_argument("--holder", required=True)
    for name in ("renew", "status", "close"):
        command = commands.add_parser(name, help=f"{name} session")
        add_common_args(command)
        command.add_argument("--session-id", required=True)
        if name == "renew":
            command.add_argument("--ttl-seconds", type=int, default=DEFAULT_SESSION_TTL_SECONDS)
        if name == "close":
            command.add_argument("--stop-manager-if-idle", action="store_true")
            command.add_argument("--timeout-seconds", type=float, default=12.0)
    return parser


def _request(args: argparse.Namespace) -> tuple[int, dict]:
    client = make_client(args.config)
    if args.command == "open":
        return client.request(
            "POST",
            "/sessions/open",
            {"kind": args.kind, "ttlSeconds": args.ttl_seconds, "holder": args.holder},
        )
    if args.command == "renew":
        return client.request(
            "POST",
            "/sessions/renew",
            {"sessionId": args.session_id, "ttlSeconds": args.ttl_seconds},
        )
    if args.command == "status":
        return client.request("GET", "/sessions/status", params={"sessionId": args.session_id})
    return client.request("POST", "/sessions/close", {"sessionId": args.session_id})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def execute() -> int:
        status, value = _request(args)
        if status >= 400 or value.get("ok") is not True:
            return output_remote(status, value, pretty=args.pretty)
        if args.command == "close" and args.stop_manager_if_idle:
            data = value.get("data")
            generation = data.get("workGeneration") if isinstance(data, dict) else None
            if isinstance(generation, bool) or not isinstance(generation, int):
                raise ValueError("session close response 缺少 workGeneration")
            context = resolve_runtime_context(config=args.config)
            try:
                stopped = ManagerConverger(context).stop(
                    timeout=args.timeout_seconds,
                    expected_work_generation=generation,
                    require_idle=True,
                )
                data.update({"managerRetained": False, "idleStop": stopped})
            except OperationConflictError as exc:
                data.update(
                    {
                        "managerRetained": True,
                        "idleStop": {
                            "state": "precondition_changed",
                            "error": exc.public_dict(include_diagnostics=True),
                        },
                    }
                )
        print_json(value, pretty=args.pretty)
        return 0

    return run_cli(f"sessions.{args.command}", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
