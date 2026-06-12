#!/usr/bin/env python3
"""诊断 process-manager 本地环境。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pm_common import PMError, default_config_path, http_request, is_windows, load_manager_config, print_json, read_token


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断 process-manager 配置和 manager 状态")
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    args = parser.parse_args()
    checks: list[dict[str, object]] = []
    ok = True
    try:
        config_path = Path(args.config).resolve()
        config = load_manager_config(config_path)
        checks.append({"name": "config", "ok": True, "path": str(config_path)})
        checks.append({"name": "windows", "ok": is_windows(), "platform": sys.platform})
        if not is_windows():
            ok = False
        try:
            read_token(config)
            checks.append({"name": "token", "ok": True})
        except PMError as exc:
            ok = False
            checks.append({"name": "token", "ok": False, "error": str(exc)})
        try:
            code, data = http_request(config, "GET", "/health", timeout=5)
            online = code < 400 and data.get("ok")
            checks.append({"name": "manager", "ok": online, "response": data})
            ok = ok and bool(online)
        except PMError as exc:
            ok = False
            checks.append({"name": "manager", "ok": False, "error": str(exc)})
        print_json({"ok": ok, "checks": checks})
        return 0 if ok else 1
    except PMError as exc:
        print_json({"ok": False, "checks": checks, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
