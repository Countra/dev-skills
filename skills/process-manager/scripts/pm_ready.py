#!/usr/bin/env python3
"""等待 managed process readiness。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="等待 service ready")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--service", help="service 名称")
    parser.add_argument("--process-key", help="processKey")
    parser.add_argument("--timeout", type=float, help="覆盖 readiness timeoutSeconds")
    args = parser.parse_args()
    try:
        payload = {"service": args.service, "processKey": args.process_key, "timeoutSeconds": args.timeout}
        payload = {k: v for k, v in payload.items() if v is not None}
        config = load_manager_config(Path(args.config).resolve())
        code, data = http_request(config, "POST", "/processes/ready", payload, timeout=(args.timeout or 35) + 5)
        print_json(data)
        return 0 if code < 400 and data.get("status") == "ready" else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
