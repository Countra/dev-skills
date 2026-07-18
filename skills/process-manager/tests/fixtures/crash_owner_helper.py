from __future__ import annotations

import argparse
import json
import os
import sys
import time
import types
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from process_manager.config import create_default_manager_config  # noqa: E402
from process_manager.errors import RuntimePermissionDeniedError, SupervisorError  # noqa: E402
from process_manager.manager import ProcessManager  # noqa: E402
from process_manager.platforms import select_platform_adapter  # noqa: E402
from process_manager.runtime import initialize_runtime  # noqa: E402
from process_manager.state import StateStore  # noqa: E402


def enable_permission_harness(adapter) -> None:  # noqa: ANN001
    def secure_directory(self, path: Path) -> None:  # noqa: ANN001
        path.mkdir(parents=True, exist_ok=True)

    def secure_file(self, path: Path) -> None:  # noqa: ANN001
        if not path.is_file():
            raise SupervisorError(f"crash fixture 文件不存在: {path}")

    adapter.secure_directory = types.MethodType(secure_directory, adapter)
    adapter.secure_file = types.MethodType(secure_file, adapter)
    adapter.verify_directory = types.MethodType(secure_directory, adapter)
    adapter.verify_file = types.MethodType(secure_file, adapter)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--crash", type=Path, required=True)
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=True)
    args.identity.touch()
    config = create_default_manager_config(args.workspace)
    adapter = select_platform_adapter(config.workspace_root, config.state_root)
    try:
        initialize_runtime(config, adapter)
    except RuntimePermissionDeniedError:
        if adapter.selection.platform != "windows":
            raise
        enable_permission_harness(adapter)
        initialize_runtime(config, adapter)
    state = StateStore(config, adapter)
    state.load()
    manager = ProcessManager(
        config,
        adapter,
        state,
        uuid.uuid4().hex,
        operation_id=uuid.uuid4().hex,
    )
    fixture = Path(__file__).resolve().with_name("process_tree_service.py")
    inherit = [
        name
        for name in ("SystemRoot", "WINDIR", "ComSpec", "TEMP", "TMP", "PATH", "HOME", "USERPROFILE", "LANG")
        if name in os.environ
    ]
    service_path = args.workspace / "crash-service.json"
    service_path.write_text(
        json.dumps(
            {
                "name": "crash-smoke",
                "kind": "long-running",
                "cwd": str(args.workspace),
                "launcher": {
                    "type": "script",
                    "interpreter": str(Path(sys.executable).resolve()),
                    "script": str(fixture),
                    "args": [],
                    "pathArgs": [str(args.identity.resolve())],
                },
                "environment": {"inherit": inherit, "set": {}, "fromEnv": ["PM_SMOKE_SECRET"]},
                "stop": {"graceSeconds": 0.5},
                "readiness": {"type": "process", "stableSeconds": 0.1, "timeoutSeconds": 5},
                "logs": {"maxBytes": 65536, "backups": 1},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manager.start(service_path, persistent=True)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and args.identity.stat().st_size == 0:
        time.sleep(0.05)
    if args.identity.stat().st_size == 0:
        manager.shutdown()
        return 2
    args.ready.write_text("ready\n", encoding="ascii")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not args.crash.exists():
        time.sleep(0.05)
    if not args.crash.exists():
        manager.shutdown()
        return 3
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
