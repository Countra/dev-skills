#!/usr/bin/env python3
"""诊断 Electron verifier 本机配置和 server 状态。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ev_common import EVError, add_common_args, load_config, paths_for_workspace, print_json, request_json, resolve_config_path


def check_path(path: Path, must_exist: bool = True) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "ok": path.exists() if must_exist else True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="诊断 electron-ui-verifier 配置和 server。")
    add_common_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks: list[dict[str, Any]] = []
    try:
        config_path = resolve_config_path(args)
        workspace_root = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
        paths = paths_for_workspace(workspace_root)
        checks.append({"name": "environment", **check_path(paths.environment_file)})
        checks.append({"name": "config", **check_path(config_path)})
        checks.append({"name": "token", **check_path(paths.token_file)})
        checks.append({"name": "processManagerService", **check_path(paths.service_file, must_exist=False)})
        config = load_config(config_path)
        health = request_json(config, "GET", "/health", timeout=5.0)
        sessions = request_json(config, "GET", "/sessions", timeout=5.0)
        result = {"ok": health.get("ok") is True, "checks": checks, "health": health, "sessions": sessions}
        print_json(result)
        return 0 if result["ok"] else 2
    except EVError as exc:
        print_json({"ok": False, "checks": checks, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
