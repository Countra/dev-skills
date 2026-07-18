#!/usr/bin/env python3
"""按需显示 manager 与内部 owner 诊断。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_context_args, output_remote, resolve_context, run_cli
from process_manager.client import ManagerClient
from process_manager.errors import PMError
from process_manager.manager_lifecycle import ManagerStateResolver
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import print_json, success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="诊断 process-manager 配置和 manager 状态")
    add_context_args(parser)
    args = parser.parse_args(argv)

    def execute() -> int:
        context = resolve_context(args)
        adapter = select_platform_adapter(context.workspace_root, context.state_root)
        snapshot = ManagerStateResolver(
            context,
            adapter_factory=lambda _workspace, _state: adapter,
        ).resolve()
        manager_error = None
        if context.config is not None and snapshot.manager_ready:
            try:
                status, value = ManagerClient(context.config, adapter, timeout=5).request("GET", "/doctor")
                return output_remote(status, value, pretty=args.pretty)
            except PMError as exc:
                manager_error = exc.public_dict()
        print_json(
            success(
                "doctor",
                {
                    "manager": snapshot.public_dict(),
                    "diagnostics": adapter.diagnostics(),
                    "managerError": manager_error,
                },
            ),
            pretty=args.pretty,
        )
        return 0

    return run_cli("doctor", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
