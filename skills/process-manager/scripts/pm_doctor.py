#!/usr/bin/env python3
"""按需显示 manager 与内部 owner 诊断。"""

from __future__ import annotations

import argparse
from pathlib import Path

from process_manager.cli import add_common_args, output_remote, run_cli
from process_manager.client import ManagerClient
from process_manager.config import load_manager_config
from process_manager.errors import PMError
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import print_json, success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="诊断 process-manager 配置和 manager 状态")
    add_common_args(parser)
    args = parser.parse_args(argv)

    def execute() -> int:
        config = load_manager_config(Path(args.config).resolve())
        adapter = select_platform_adapter(config.workspace_root, config.state_root)
        try:
            status, value = ManagerClient(config, adapter, timeout=5).request("GET", "/doctor")
            return output_remote(status, value, pretty=args.pretty)
        except PMError as exc:
            print_json(
                success(
                    "doctor",
                    {
                        "managerReady": False,
                        "supervisorReady": False,
                        "diagnostics": adapter.diagnostics(),
                        "managerError": exc.public_dict(),
                    },
                ),
                pretty=args.pretty,
            )
            return 0

    return run_cli("doctor", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
