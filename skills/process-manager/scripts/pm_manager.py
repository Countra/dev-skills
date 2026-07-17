#!/usr/bin/env python3
"""平台透明的 manager bootstrap facade。"""

from __future__ import annotations

import argparse
import time

from process_manager.bootstrap import ManagerBootstrap
from process_manager.cli import add_context_args, output_remote, run_cli
from process_manager.client import ManagerClient
from process_manager.errors import SupervisorError
from process_manager.manager_lifecycle import ManagerConverger, ManagerStateResolver
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import print_json, success
from process_manager.runtime import read_manager_identity
from process_manager.runtime_context import resolve_runtime_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动、查看或关闭 process-manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("ensure", "幂等确保 manager ready"),
        ("start", "启动 manager"),
        ("status", "查看 manager 状态"),
        ("stop", "通过认证控制面关闭 manager"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        add_context_args(subparser)
    return parser


def _context(args: argparse.Namespace):  # noqa: ANN202
    return resolve_runtime_context(
        workspace=getattr(args, "workspace", None),
        config=getattr(args, "config", None),
    )


def _client(args: argparse.Namespace, *, timeout: float = 5):  # noqa: ANN202
    context = _context(args)
    if context.config is None:
        return None, None, None
    config = context.config
    adapter = select_platform_adapter(config.workspace_root, config.state_root)
    return config, adapter, ManagerClient(config, adapter, timeout=timeout)


def _ensure(args: argparse.Namespace) -> int:
    value = ManagerConverger(_context(args)).ensure()
    print_json(success("manager.ensure", value), pretty=args.pretty)
    return 0


def _status(args: argparse.Namespace) -> int:
    value = ManagerStateResolver(_context(args)).resolve().public_dict()
    print_json(success("manager.status", value), pretty=args.pretty)
    return 0


def _stop(args: argparse.Namespace) -> int:
    context = _context(args)
    config, adapter, client = _client(args, timeout=3600)
    if config is None or adapter is None or client is None:
        value = ManagerStateResolver(context).resolve().public_dict()
        print_json(success("manager.stop", {**value, "changed": False}), pretty=args.pretty)
        return 0
    identity = read_manager_identity(config, adapter)
    status, value = client.request("POST", "/shutdown", {})
    if value.get("ok"):
        deadline = time.monotonic() + 10
        while config.paths.manager.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        manager_stopped = not config.paths.manager.exists()
        if not manager_stopped:
            raise SupervisorError("manager shutdown 后 identity 仍存在")
        bootstrap_cleaned = ManagerBootstrap(config, adapter).cleanup(str(identity["bootstrapBackend"]))
        if not bootstrap_cleaned:
            raise SupervisorError("manager 已停止，但 bootstrap cleanup 未验证")
        value["data"]["managerStopped"] = True
        value["data"]["bootstrapCleaned"] = True
    return output_remote(status, value, pretty=args.pretty)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    operations = {"ensure": _ensure, "start": _ensure, "status": _status, "stop": _stop}
    return run_cli(f"manager.{args.command}", lambda: operations[args.command](args), pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
