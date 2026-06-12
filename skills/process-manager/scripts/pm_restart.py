#!/usr/bin/env python3
"""重启一个 service。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json, service_from_path, validate_service_config


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 stop/start 重启 service")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--service", required=True, help="service JSON 路径")
    parser.add_argument("--timeout", type=float, help="ready timeout 覆盖")
    args = parser.parse_args()
    try:
        config = load_manager_config(Path(args.config).resolve())
        service_path = Path(args.service).resolve()
        normalized = validate_service_config(service_from_path(service_path), config.workspace_root)
        stop_code, stop_data = http_request(config, "POST", "/processes/stop", {"service": normalized["name"]}, timeout=20)
        start_code, start_data = http_request(config, "POST", "/processes/start", {"servicePath": str(service_path)}, timeout=35)
        result = {"ok": start_code < 400 and start_data.get("ok"), "stop": stop_data, "start": start_data}
        if result["ok"] and normalized.get("readiness"):
            ready_payload = {"service": normalized["name"]}
            if args.timeout:
                ready_payload["timeoutSeconds"] = args.timeout
            _, ready_data = http_request(config, "POST", "/processes/ready", ready_payload, timeout=(args.timeout or 35) + 5)
            result["ready"] = ready_data
            result["ok"] = ready_data.get("status") == "ready"
        print_json(result)
        return 0 if result["ok"] and stop_code < 500 else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
