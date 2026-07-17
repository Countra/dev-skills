#!/usr/bin/env python3
"""process-manager 的 composition root 与 serve loop。"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from process_manager.config import load_manager_config
from process_manager.control_api import ControlServer
from process_manager.errors import RuntimeCorruptError
from process_manager.manager import ProcessManager
from process_manager.platforms import select_platform_adapter
from process_manager.protocol import failure, print_json, success
from process_manager.bootstrap import remove_bootstrap_capture, write_bootstrap_capture
from process_manager.runtime import (
    OperationStore,
    build_manager_identity,
    config_digest,
    initialize_runtime,
    read_token,
    remove_manager_identity,
    write_manager_identity,
)
from process_manager.runtime_context import resolve_runtime_context
from process_manager.runtime_fingerprint import compute_runtime_fingerprint
from process_manager.state import StateStore


START_CHECKPOINTS = {"runtime-verified", "bootstrap-launched"}


def require_parent_operation(
    store: OperationStore,
    *,
    operation_id: str,
    runtime_fingerprint: str,
) -> dict:
    operation = store.read()
    if (
        operation is None
        or operation["operationId"] != operation_id
        or operation["state"] != "pending"
        or operation["kind"] not in {"ensure", "restart"}
        or operation["checkpoint"] not in START_CHECKPOINTS
        or operation["expectedRuntimeFingerprint"] != runtime_fingerprint
    ):
        raise RuntimeCorruptError("manager child 未绑定有效 parent operation")
    return operation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 process-manager 本地控制服务")
    parser.add_argument("--config", required=True, help="manager config 绝对路径")
    parser.add_argument("--bootstrap-backend", default="direct", help=argparse.SUPPRESS)
    parser.add_argument("--bootstrap-reason", default="direct composition root", help=argparse.SUPPRESS)
    parser.add_argument("--operation-id", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-fingerprint", required=True, help=argparse.SUPPRESS)
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
    manager = None
    server = None
    capture = None
    try:
        config = load_manager_config(config_path)
        adapter = select_platform_adapter(config.workspace_root, config.state_root)
        context = resolve_runtime_context(config=config_path)
        operation_store = OperationStore(
            config,
            adapter,
            workspace_digest=context.workspace_digest,
            expected_config_digest=config_digest(config),
        )
        require_parent_operation(
            operation_store,
            operation_id=args.operation_id,
            runtime_fingerprint=args.runtime_fingerprint,
        )
        capture = write_bootstrap_capture(
            config,
            adapter,
            operation_id=args.operation_id,
            backend=args.bootstrap_backend,
            runtime_fingerprint=args.runtime_fingerprint,
        )
        current_fingerprint = compute_runtime_fingerprint()
        if current_fingerprint != args.runtime_fingerprint:
            raise RuntimeCorruptError("manager child runtime fingerprint 与 parent 不匹配")
        require_parent_operation(
            operation_store,
            operation_id=args.operation_id,
            runtime_fingerprint=current_fingerprint,
        )
        initialize_runtime(config, adapter)
        manager_lock = adapter.acquire_manager_lock()
        state = StateStore(config, adapter)
        manager = ProcessManager(
            config,
            adapter,
            state,
            instance_id,
            operation_id=args.operation_id,
            runtime_fingerprint=current_fingerprint,
            bootstrap_backend=args.bootstrap_backend,
            bootstrap_selection_reason=args.bootstrap_reason,
        )
        token = read_token(config, adapter)
        server = ControlServer((config.host, config.port), manager, token, config.max_request_bytes)
        port = int(server.server_address[1])
        identity = build_manager_identity(
            config,
            adapter,
            operation_id=args.operation_id,
            instance_id=instance_id,
            port=port,
            bootstrap_backend=args.bootstrap_backend,
            bootstrap_selection_reason=args.bootstrap_reason,
            runtime_fingerprint=current_fingerprint,
        )
        require_parent_operation(
            operation_store,
            operation_id=args.operation_id,
            runtime_fingerprint=current_fingerprint,
        )
        write_manager_identity(config, adapter, identity)
        if not remove_bootstrap_capture(
            config,
            adapter,
            operation_id=args.operation_id,
            process_identity=capture["processIdentity"],
        ):
            raise RuntimeCorruptError("manager child bootstrap capture 清理不匹配")
        capture = None
        print_json(success("manager.start", {"state": "listening", "host": config.host, "port": port}, instance_id=instance_id))
        server.serve_forever(poll_interval=0.2)
        server.wait_for_shutdown(timeout=30)
        if server.shutdown_error is not None:
            raise server.shutdown_error
        return 0
    except Exception as exc:  # noqa: BLE001
        print_json(failure("manager.start", exc, instance_id=instance_id))
        return 1
    finally:
        if manager is not None and (server is None or server.shutdown_result is None):
            try:
                manager.shutdown()
            except Exception:
                pass
        if server is not None:
            server.server_close()
        if config is not None and adapter is not None:
            remove_manager_identity(config, adapter, instance_id)
        if config is not None and adapter is not None and capture is not None:
            try:
                remove_bootstrap_capture(
                    config,
                    adapter,
                    operation_id=args.operation_id,
                    process_identity=capture["processIdentity"],
                )
            except Exception:
                pass
        if manager_lock is not None:
            manager_lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
