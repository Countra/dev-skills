"""所有 pm_* facade 共用的 CLI 工具。"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from .client import ManagerClient
from .errors import PMError, RuntimeUninitializedError
from .platforms import select_platform_adapter
from .protocol import failure, print_json
from .runtime_context import RuntimeContext, resolve_runtime_context


REMOTE_EXIT_CODES = {
    "configuration_error": 2,
    "validation_error": 2,
    "context_invalid": 2,
    "manager_absent": 3,
    "runtime_uninitialized": 4,
    "manager_starting": 3,
    "manager_stopping": 3,
    "manager_stale": 4,
    "manager_unresponsive": 3,
    "runtime_insecure": 7,
    "runtime_permission_denied": 7,
    "environment_unverifiable": 7,
    "runtime_corrupt": 6,
    "operation_conflict": 4,
    "operation_timeout": 9,
    "state_conflict": 4,
    "resource_budget_exceeded": 4,
    "owned_runs_confirmation_required": 4,
    "restart_confirmation_required": 4,
    "stop_confirmation_required": 4,
    "identity_mismatch": 5,
    "not_found": 8,
    "session_not_found": 8,
    "session_expired": 4,
    "state_error": 6,
    "runtime_rebuild_required": 6,
    "supervisor_unavailable": 7,
    "session_cleanup_pending": 7,
    "unsupported_platform": 7,
    "invalid_request": 2,
    "control_timeout": 9,
    "readiness_timeout": 9,
    "probe_limit_exceeded": 9,
}


def add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", help="workspace 绝对路径")
    parser.add_argument("--config", help="manager config 绝对路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")


def resolve_context(args: argparse.Namespace) -> RuntimeContext:
    return resolve_runtime_context(workspace=args.workspace, config=args.config)


def require_config(args: argparse.Namespace):  # noqa: ANN202
    context = resolve_context(args)
    if context.config is None:
        raise RuntimeUninitializedError(
            "process-manager runtime 尚未初始化",
            recommended_action="init",
        )
    return context.config


def make_client(args: argparse.Namespace, *, timeout: float = 35) -> ManagerClient:
    config = require_config(args)
    adapter = select_platform_adapter(config.workspace_root, config.state_root)
    return ManagerClient(config, adapter, timeout=timeout)


def output_remote(status: int, value: dict[str, Any], *, pretty: bool) -> int:
    print_json(value, pretty=pretty)
    if value.get("ok"):
        return 0
    code = value.get("error", {}).get("code")
    return REMOTE_EXIT_CODES.get(str(code), 1 if status >= 500 else 2)


def run_cli(operation: str, handler: Callable[[], int], *, pretty: bool = True) -> int:
    try:
        return handler()
    except PMError as exc:
        print_json(failure(operation, exc), pretty=pretty)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        print_json(failure(operation, exc), pretty=pretty)
        return 1
