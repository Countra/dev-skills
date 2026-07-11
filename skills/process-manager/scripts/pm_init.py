#!/usr/bin/env python3
"""初始化当前 process-manager runtime。"""

from __future__ import annotations

import argparse
from pathlib import Path

from process_manager.cli import run_cli
from process_manager.config import create_default_manager_config
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import print_json, success
from process_manager.runtime import initialize_runtime
from process_manager.state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化 .harness/process-manager")
    parser.add_argument("--workspace", default=".", help="workspace 路径")
    parser.add_argument("--config", help="manager config 输出路径")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    def execute() -> int:
        workspace = Path(args.workspace).resolve()
        config_path = Path(args.config).resolve() if args.config else None
        config = create_default_manager_config(workspace, config_path)
        adapter = select_platform_adapter(config.workspace_root, config.state_root)
        initialize_runtime(config, adapter)
        StateStore(config, adapter).load()
        print_json(success("init", config.public_dict()), pretty=args.pretty)
        return 0

    return run_cli("init", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
