#!/usr/bin/env python3
"""读取 managed process stdout/stderr 日志。"""

from __future__ import annotations

import argparse
import urllib.parse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="查看 service 日志")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--service", help="service 名称")
    parser.add_argument("--process-key", help="processKey")
    parser.add_argument("--stream", choices=["stdout", "stderr"], default="stdout")
    parser.add_argument("--tail", type=int, default=80)
    args = parser.parse_args()
    try:
        query = urllib.parse.urlencode(
            {k: v for k, v in {"service": args.service, "processKey": args.process_key, "stream": args.stream, "tail": args.tail}.items() if v is not None}
        )
        config = load_manager_config(Path(args.config).resolve())
        code, data = http_request(config, "GET", f"/processes/logs?{query}", timeout=10)
        print_json(data)
        return 0 if code < 400 and data.get("ok") else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
