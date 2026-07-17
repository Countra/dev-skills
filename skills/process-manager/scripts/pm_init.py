#!/usr/bin/env python3
"""初始化当前 process-manager runtime。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_context_args, run_cli
from process_manager.config import create_default_manager_config
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import print_json, success
from process_manager.runtime import initialize_runtime
from process_manager.runtime_context import resolve_runtime_context
from process_manager.state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化 .harness/process-manager")
    add_context_args(parser)
    args = parser.parse_args(argv)

    def execute() -> int:
        context = resolve_runtime_context(workspace=args.workspace, config=args.config)
        config = context.config or create_default_manager_config(context.workspace_root, context.config_path)
        adapter = select_platform_adapter(config.workspace_root, config.state_root)
        initialize_runtime(config, adapter)
        StateStore(config, adapter).load()
        print_json(success("init", config.public_dict()), pretty=args.pretty)
        return 0

    return run_cli("init", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
