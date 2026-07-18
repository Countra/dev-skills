#!/usr/bin/env python3
"""平台透明的 manager bootstrap facade。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_context_args, run_cli
from process_manager.manager_lifecycle import ManagerConverger, ManagerStateResolver
from process_manager.protocol import print_json, success
from process_manager.runtime_context import resolve_runtime_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="确保、查看、重启或关闭 process-manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("ensure", "幂等确保 manager ready"),
        ("status", "查看 manager 状态"),
        ("restart", "重启 manager 且不恢复旧 service"),
        ("stop", "通过认证控制面关闭 manager"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        add_context_args(subparser)
        if name in {"ensure", "restart", "stop"}:
            subparser.add_argument("--timeout-seconds", type=float, default=12.0)
        if name in {"restart", "stop"}:
            subparser.add_argument("--confirm-stop-owned-runs", action="store_true")
    return parser


def _context(args: argparse.Namespace):  # noqa: ANN202
    return resolve_runtime_context(
        workspace=getattr(args, "workspace", None),
        config=getattr(args, "config", None),
    )


def _ensure(args: argparse.Namespace) -> int:
    value = ManagerConverger(_context(args)).ensure(timeout=args.timeout_seconds)
    print_json(success("manager.ensure", value), pretty=args.pretty)
    return 0


def _status(args: argparse.Namespace) -> int:
    value = ManagerStateResolver(_context(args)).resolve().public_dict()
    print_json(success("manager.status", value), pretty=args.pretty)
    return 0


def _stop(args: argparse.Namespace) -> int:
    value = ManagerConverger(_context(args)).stop(
        timeout=args.timeout_seconds,
        confirm_stop_owned_runs=args.confirm_stop_owned_runs,
    )
    print_json(success("manager.stop", value), pretty=args.pretty)
    return 0


def _restart(args: argparse.Namespace) -> int:
    value = ManagerConverger(_context(args)).restart(
        timeout=args.timeout_seconds,
        confirm_stop_owned_runs=args.confirm_stop_owned_runs,
    )
    print_json(success("manager.restart", value), pretty=args.pretty)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    operations = {
        "ensure": _ensure,
        "status": _status,
        "restart": _restart,
        "stop": _stop,
    }
    return run_cli(f"manager.{args.command}", lambda: operations[args.command](args), pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
