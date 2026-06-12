#!/usr/bin/env python3
"""检查 process-manager manager 是否在线。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 manager health")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    args = parser.parse_args()
    try:
        config = load_manager_config(Path(args.config).resolve())
        code, data = http_request(config, "GET", "/health", timeout=5)
        print_json(data)
        return 0 if code < 400 and data.get("ok") else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
