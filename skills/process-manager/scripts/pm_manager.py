#!/usr/bin/env python3
"""平台透明的 manager bootstrap facade。"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from process_manager.bootstrap import ManagerBootstrap
from process_manager.cli import add_common_args, output_remote, run_cli
from process_manager.client import ManagerClient
from process_manager.config import load_manager_config
from process_manager.errors import ManagerOfflineError, PMError, SupervisorError
from process_manager.platforms import select_platform_adapter
from process_manager.runtime import initialize_runtime, read_manager_identity


START_TIMEOUT_SECONDS = 12


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动、查看或关闭 process-manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("start", "启动 manager"),
        ("status", "查看 manager 状态"),
        ("stop", "通过认证控制面关闭 manager"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        add_common_args(subparser)
    return parser


def _client(config_path: str, *, timeout: float = 5) -> tuple[Any, Any, ManagerClient]:
    config = load_manager_config(Path(config_path).resolve())
    adapter = select_platform_adapter(config.workspace_root, config.state_root)
    return config, adapter, ManagerClient(config, adapter, timeout=timeout)


def _rotate(path: Path, max_bytes: int, backups: int) -> None:
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    oldest = path.with_name(f"{path.name}.{backups}")
    if backups > 0:
        oldest.unlink(missing_ok=True)
        for index in range(backups - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
    else:
        path.unlink()


def _start(args: argparse.Namespace) -> int:
    config, adapter, client = _client(args.config)
    initialize_runtime(config, adapter)
    try:
        status, value = client.request("GET", "/health")
        if value.get("ok"):
            value["data"]["state"] = "already_running"
            return output_remote(status, value, pretty=args.pretty)
    except ManagerOfflineError as exc:
        if config.paths.manager.exists():
            raise ManagerOfflineError("manager identity 存在但控制面不可用；请运行 pm_doctor.py") from exc
    stdout_path = config.paths.logs / "manager-stdout.log"
    stderr_path = config.paths.logs / "manager-stderr.log"
    _rotate(stdout_path, config.log_max_bytes, config.log_backups)
    _rotate(stderr_path, config.log_max_bytes, config.log_backups)
    manager_script = Path(__file__).resolve().with_name("manager_server.py")

    def command_factory(backend: str, reason: str) -> list[str]:
        return [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(manager_script),
            "--config",
            str(config.config_path),
            "--bootstrap-backend",
            backend,
            "--bootstrap-reason",
            reason,
        ]

    bootstrap = ManagerBootstrap(config, adapter)
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        launched = bootstrap.start(
            command_factory,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout=stdout,
            stderr=stderr,
        )
    adapter.secure_file(stdout_path)
    adapter.secure_file(stderr_path)
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    last_error: PMError | None = None
    while time.monotonic() < deadline:
        if launched.process is not None and launched.process.poll() is not None:
            raise ManagerOfflineError("manager bootstrap 提前退出")
        try:
            status, value = client.request("GET", "/health")
            if value.get("ok"):
                value["data"]["state"] = "running"
                return output_remote(status, value, pretty=args.pretty)
        except PMError as exc:
            last_error = exc
        time.sleep(0.1)
    if launched.process is not None and launched.process.poll() is None:
        launched.process.terminate()
        try:
            launched.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            launched.process.kill()
    else:
        bootstrap.cleanup(launched.backend)
    raise ManagerOfflineError("manager bootstrap 未在期限内就绪") from last_error


def _status(args: argparse.Namespace) -> int:
    _, _, client = _client(args.config)
    status, value = client.request("GET", "/health")
    return output_remote(status, value, pretty=args.pretty)


def _stop(args: argparse.Namespace) -> int:
    config, adapter, client = _client(args.config, timeout=3600)
    identity = read_manager_identity(config, adapter)
    status, value = client.request("POST", "/shutdown", {})
    if value.get("ok"):
        deadline = time.monotonic() + 10
        while config.paths.manager.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        manager_stopped = not config.paths.manager.exists()
        if not manager_stopped:
            raise SupervisorError("manager shutdown 后 identity 仍存在")
        bootstrap_cleaned = ManagerBootstrap(config, adapter).cleanup(str(identity["bootstrapBackend"]))
        if not bootstrap_cleaned:
            raise SupervisorError("manager 已停止，但 bootstrap cleanup 未验证")
        value["data"]["managerStopped"] = True
        value["data"]["bootstrapCleaned"] = True
    return output_remote(status, value, pretty=args.pretty)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    operations = {"start": _start, "status": _status, "stop": _stop}
    return run_cli(f"manager.{args.command}", lambda: operations[args.command](args), pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
