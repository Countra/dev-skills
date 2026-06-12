#!/usr/bin/env python3
"""裁剪 manager 进程历史记录。"""

from __future__ import annotations

import argparse
from pathlib import Path

from pm_common import PMError, default_config_path, fail, http_request, load_manager_config, print_json


def main() -> int:
    parser = argparse.ArgumentParser(description="裁剪 inactive process 历史记录")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--apply", action="store_true", help="实际执行裁剪；默认只做 dry-run")
    parser.add_argument("--max-inactive", type=int, help="临时覆盖保留的 inactive 数量")
    parser.add_argument("--keep-runs", action="store_true", help="只裁剪 processes.json，不删除对应 runDir")
    args = parser.parse_args()
    try:
        if args.max_inactive is not None and args.max_inactive < 0:
            raise PMError("--max-inactive 必须是非负整数")
        payload: dict[str, object] = {
            "dryRun": not args.apply,
            "keepRuns": args.keep_runs,
        }
        if args.max_inactive is not None:
            payload["maxInactive"] = args.max_inactive
        config = load_manager_config(Path(args.config).resolve())
        code, data = http_request(config, "POST", "/processes/prune", payload, timeout=20)
        print_json(data)
        return 0 if code < 400 and data.get("ok") else 1
    except PMError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
