"""所有 pm_* facade 共用的 CLI 工具。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .client import ManagerClient
from .config import default_config_path, load_manager_config
from .errors import PMError
from .platforms import select_platform_adapter
from .protocol import failure, print_json


REMOTE_EXIT_CODES = {
    "configuration_error": 2,
    "validation_error": 2,
    "manager_offline": 3,
    "state_conflict": 4,
    "identity_mismatch": 5,
    "not_found": 8,
    "state_error": 6,
    "supervisor_unavailable": 7,
    "unsupported_platform": 7,
    "readiness_timeout": 9,
    "probe_limit_exceeded": 9,
}


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=str(default_config_path()), help="manager config 路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")


def make_client(config_path: str, *, timeout: float = 35) -> ManagerClient:
    config = load_manager_config(Path(config_path).resolve())
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
