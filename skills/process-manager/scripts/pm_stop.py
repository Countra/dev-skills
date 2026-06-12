#!/usr/bin/env python3
"""停止一个 managed process。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="停止 service 或 processKey")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--service", help="service 名称")
    parser.add_argument("--process-key", help="processKey")
    args = parser.parse_args()
    try:
        payload = {k: v for k, v in {"service": args.service, "processKey": args.process_key}.items() if v}
        config = load_manager_config(Path(args.config).resolve())
        code, data = http_request(config, "POST", "/processes/stop", payload, timeout=20)
        print_json(data)
        return 0 if code < 400 and data.get("ok") else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
