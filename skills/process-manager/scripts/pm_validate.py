#!/usr/bin/env python3
"""校验 manager config 或 service config。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, load_manager_config, print_json, service_from_path, validate_service_config


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 process-manager 配置")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--service", help="service JSON 路径")
    args = parser.parse_args()
    try:
        config = load_manager_config(Path(args.config).resolve())
        result: dict[str, object] = {"ok": True, "managerConfig": str(Path(args.config).resolve())}
        if args.service:
            service_path = Path(args.service).resolve()
            normalized = validate_service_config(service_from_path(service_path), config.workspace_root)
            result["service"] = normalized["name"]
            result["servicePath"] = str(service_path)
        print_json(result)
        return 0
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
