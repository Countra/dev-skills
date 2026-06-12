#!/usr/bin/env python3
"""列出 manager 已知进程。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="列出 managed processes")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    args = parser.parse_args()
    try:
        config = load_manager_config(Path(args.config).resolve())
        code, data = http_request(config, "GET", "/processes", timeout=10)
        print_json(data)
        return 0 if code < 400 and data.get("ok") else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
