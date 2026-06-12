#!/usr/bin/env python3
"""启动一个已配置的长期后台进程。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json, service_from_path, validate_service_config


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 manager 启动 service")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--service", required=True, help="service JSON 路径")
    args = parser.parse_args()
    try:
        config = load_manager_config(Path(args.config).resolve())
        service_path = Path(args.service).resolve()
        validate_service_config(service_from_path(service_path), config.workspace_root)
        code, data = http_request(config, "POST", "/processes/start", {"servicePath": str(service_path)})
        print_json(data)
        return 0 if code < 400 and data.get("ok") else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
