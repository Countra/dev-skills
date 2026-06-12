#!/usr/bin/env python3
"""初始化 process-manager runtime 目录。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import DEFAULT_PORT, DEFAULT_PORT_RETRY_SWITCHES, PMError, create_default_manager_config, fail, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 .harness/process-manager")
    parser.add_argument("--workspace", default=".", help="workspace 绝对路径或当前目录")
    parser.add_argument("--config", help="manager config 输出路径")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="manager 初始端口，默认 18080")
    parser.add_argument("--port-retry-switches", type=int, default=DEFAULT_PORT_RETRY_SWITCHES, help="端口绑定失败时最多向后切换次数，默认 3")
    args = parser.parse_args()
    try:
        workspace = Path(args.workspace).resolve()
        config_path = Path(args.config).resolve() if args.config else None
        config = create_default_manager_config(workspace, config_path, port=args.port, port_retry_switches=args.port_retry_switches)
        print_json({"ok": True, "config": str(config_path or config.state_root / "config.json"), "stateRoot": str(config.state_root), "port": config.port, "portRetry": {"enabled": config.port_retry_enabled, "maxSwitches": config.port_retry_max_switches}})
        return 0
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
