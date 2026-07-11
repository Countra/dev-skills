#!/usr/bin/env python3
"""process-manager 的 composition root 与 serve loop。"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from process_manager.config import load_manager_config
from process_manager.control_api import ControlServer
from process_manager.manager import ProcessManager
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import failure, print_json, success
from process_manager.runtime import (
    build_manager_identity,
    initialize_runtime,
    read_token,
    remove_manager_identity,
    write_manager_identity,
)
from process_manager.state import StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 process-manager 本地控制服务")
    parser.add_argument("--config", required=True, help="manager config 绝对路径")
    parser.add_argument("--bootstrap-backend", default="direct", help=argparse.SUPPRESS)
    parser.add_argument("--bootstrap-reason", default="direct composition root", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        print_json(failure("manager.start", ValueError("--config 必须是绝对路径")))
        return 2
    instance_id = uuid.uuid4().hex
    config = None
    adapter = None
    manager_lock = None
    server = None
    try:
        config = load_manager_config(config_path)
        adapter = select_platform_adapter(config.workspace_root, config.state_root)
        initialize_runtime(config, adapter)
        manager_lock = adapter.acquire_manager_lock()
        state = StateStore(config, adapter)
        manager = ProcessManager(
            config,
            adapter,
            state,
            instance_id,
            bootstrap_backend=args.bootstrap_backend,
            bootstrap_selection_reason=args.bootstrap_reason,
        )
        token = read_token(config, adapter)
        server = ControlServer((config.host, config.port), manager, token, config.max_request_bytes)
        port = int(server.server_address[1])
        identity = build_manager_identity(
            config,
            adapter,
            instance_id=instance_id,
            port=port,
            bootstrap_backend=args.bootstrap_backend,
            bootstrap_selection_reason=args.bootstrap_reason,
        )
        write_manager_identity(config, adapter, identity)
        print_json(success("manager.start", {"state": "listening", "host": config.host, "port": port}, instance_id=instance_id))
        server.serve_forever(poll_interval=0.2)
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(failure("manager.start", exc, instance_id=instance_id))
        return 1
    finally:
        if server is not None:
            server.server_close()
        if config is not None:
            remove_manager_identity(config, instance_id)
        if manager_lock is not None:
            manager_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
