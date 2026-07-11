from __future__ import annotations

import json
import os
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
TEST_TEMP_ROOT = Path(__file__).resolve().parents[3] / ".harness" / "test-tmp" / "process-manager"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from process_manager.config import create_default_manager_config, load_service_config  # noqa: E402
from process_manager.platforms.base import (  # noqa: E402
    ManagerLock,
    PlatformAdapter,
    PlatformSelection,
    RunOwner,
)


class FakeLock(ManagerLock):
    def close(self) -> None:
        return


class FakeOwner(RunOwner):
    def __init__(self, selection, host, capability_hash):  # noqa: ANN001
        super().__init__(selection, host, capability_hash)
        self.target: dict[str, Any] | None = None
        self.empty = False
        self.forced = False

    @property
    def control_data(self) -> dict[str, Any]:
        return {"mode": "windows-job"}

    def bind_target(self, target: dict[str, Any]) -> None:
        self.target = target

    def graceful_stop(self) -> bool:
        self.empty = True
        if hasattr(self.host, "finish"):
            self.host.finish(0)
        else:
            self.host.returncode = 0
        return True

    def force_stop(self) -> bool:
        self.forced = True
        self.empty = True
        if hasattr(self.host, "finish"):
            self.host.finish(1)
        else:
            self.host.returncode = 1
        return True

    def is_empty(self) -> bool:
        return self.empty

    def close(self) -> None:
        return


class FakeAdapter(PlatformAdapter):
    def __init__(self, workspace: Path, state_root: Path) -> None:
        super().__init__(
            PlatformSelection("test", "fake-owner", "kernel-process-tree", "test fixture"),
            workspace,
            state_root,
        )
        self.host_factory = None
        self.last_owner: FakeOwner | None = None
        self.identity_valid = True

    def secure_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def secure_file(self, path: Path) -> None:
        if not path.is_file():
            raise AssertionError(f"missing file: {path}")

    def verify_file(self, path: Path) -> None:
        self.secure_file(path)

    def acquire_manager_lock(self) -> ManagerLock:
        return FakeLock()

    def spawn_manager(self, command, *, stdout, stderr):  # noqa: ANN001
        raise AssertionError("not used")

    def spawn_service_host(self, command, *, cwd, environment):  # noqa: ANN001
        if self.host_factory is None:
            raise AssertionError("host_factory is not configured")
        return self.host_factory()

    def create_run_owner(self, run_id, host, capability_hash):  # noqa: ANN001
        host.capability_hash = capability_hash
        self.last_owner = FakeOwner(self.selection, host, capability_hash)
        return self.last_owner

    def process_identity(self, pid: int) -> dict[str, Any]:
        return {"pid": pid, "testIdentity": f"id-{pid}"}

    def identity_matches(self, expected: dict[str, Any]) -> bool:
        return self.identity_valid and expected == self.process_identity(int(expected.get("pid", -1)))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def workspace_directory():  # noqa: ANN201
    path = TEST_TEMP_ROOT / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path)


def create_config(workspace: Path):  # noqa: ANN201
    return create_default_manager_config(workspace)


def service_value(workspace: Path, *, name: str = "demo", from_env: list[str] | None = None) -> dict[str, Any]:
    script = workspace / "service.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    return {
        "name": name,
        "kind": "long-running",
        "cwd": str(workspace),
        "launcher": {
            "type": "script",
            "interpreter": os.path.abspath(os.sys.executable),
            "script": str(script),
            "args": [],
            "pathArgs": [],
        },
        "environment": {"inherit": [], "set": {"BROWSER": "none"}, "fromEnv": from_env or []},
        "stop": {"graceSeconds": 0.1},
        "readiness": {"type": "process", "stableSeconds": 0.1, "timeoutSeconds": 2},
        "logs": {"maxBytes": 65536, "backups": 1},
    }


def create_service(workspace: Path, config, *, name: str = "demo", from_env: list[str] | None = None):  # noqa: ANN001,ANN201
    path = workspace / f"{name}.json"
    write_json(path, service_value(workspace, name=name, from_env=from_env))
    return load_service_config(path, config)
