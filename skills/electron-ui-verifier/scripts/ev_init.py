#!/usr/bin/env python3
"""初始化 Electron verifier server 的本机运行环境。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ev_common import (
    EVError,
    config_to_data,
    discover_workspace_root,
    ensure_runtime_dirs,
    ensure_token,
    normalize_port,
    paths_for_workspace,
    print_json,
    require_absolute_path,
    write_environment,
    write_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="初始化 electron-ui-verifier server runtime。")
    parser.add_argument("--workspace", help="workspace 根目录绝对路径；未指定时使用当前目录")
    parser.add_argument("--python", dest="python_path", help="verifier server 使用的 Python 解释器绝对路径")
    parser.add_argument("--port", type=int, help="verifier server 初始端口，默认 18180")
    return parser


def service_config(workspace_root: Path, python_path: Path, config_file: Path, port: int) -> dict[str, Any]:
    server_script = workspace_root / "skills" / "electron-ui-verifier" / "scripts" / "ev_server.py"
    if not server_script.exists():
        raise EVError(f"ev_server.py does not exist: {server_script}")
    return {
        "name": "electron-ui-verifier",
        "kind": "long-running",
        "cwd": str(workspace_root),
        "launcher": {
            "type": "direct",
            "argv": [
                str(python_path),
                str(server_script),
                "--config",
                str(config_file),
            ],
        },
        "window": "hidden",
        "readiness": {
            "type": "log",
            "pattern": "EV_READY",
            "extract": {
                "urls": [
                    "EV_READY\\s+(http://127\\.0\\.0\\.1:\\d+/health)"
                ]
            },
            "timeoutSeconds": 30,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace_root = discover_workspace_root(args.workspace)
        paths = paths_for_workspace(workspace_root)
        python_path = require_absolute_path(args.python_path, "--python", must_exist=True) if args.python_path else Path(sys.executable).resolve()
        if not python_path.exists():
            raise EVError(f"python does not exist: {python_path}")
        port = normalize_port(args.port)
        ensure_runtime_dirs(paths)
        environment = write_environment(paths, python_path=python_path, port=port)
        ensure_token(paths)
        config = config_to_data(paths, environment)
        write_json(paths.config_file, config)
        write_json(paths.server_file, {"status": "initialized", "host": "127.0.0.1", "port": port, "processManagerService": "electron-ui-verifier"})
        write_json(paths.sessions_file, {"sessions": []})
        write_json(paths.service_file, service_config(workspace_root, python_path, paths.config_file, port))
        print_json(
            {
                "ok": True,
                "environment": str(paths.environment_file),
                "config": str(paths.config_file),
                "service": str(paths.service_file),
                "python": str(python_path),
                "port": port,
            }
        )
        return 0
    except EVError as exc:
        print_json({"ok": False, "code": "init_failed", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
