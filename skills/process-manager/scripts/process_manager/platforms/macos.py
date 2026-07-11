"""macOS process-group guardian 与 kqueue 补充监控。"""

from __future__ import annotations

import os
import select
import subprocess
from pathlib import Path
from typing import Any

from ..errors import IdentityError
from .base import PlatformSelection, RunOwner
from .posix import PosixAdapter, PosixRunOwner


class MacRunOwner(PosixRunOwner):
    def __init__(self, selection: PlatformSelection, host: subprocess.Popen[str], capability_hash: str) -> None:
        super().__init__(selection, host, capability_hash)
        self._kqueue: Any | None = None
        self._target_exit_observed = False

    def bind_target(self, target: dict[str, Any]) -> None:
        super().bind_target(target)
        pid = target.get("pid")
        if hasattr(select, "kqueue") and isinstance(pid, int):
            queue = select.kqueue()
            event = select.kevent(
                pid,
                filter=select.KQ_FILTER_PROC,
                flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                fflags=select.KQ_NOTE_EXIT,
            )
            queue.control([event], 0, 0)
            self._kqueue = queue

    def _poll_target_exit(self) -> None:
        if self._kqueue is None or self._target_exit_observed:
            return
        try:
            self._target_exit_observed = bool(self._kqueue.control(None, 1, 0))
        except OSError:
            return

    def is_empty(self) -> bool:
        self._poll_target_exit()
        return super().is_empty()

    def internal_identity(self) -> dict[str, Any]:
        return {
            **super().internal_identity(),
            "targetExitMonitor": "kqueue" if self._kqueue is not None else "process-group",
        }

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._kqueue is not None:
                self._kqueue.close()
                self._kqueue = None


class MacOSAdapter(PosixAdapter):
    def create_run_owner(
        self,
        run_id: str,
        host: subprocess.Popen[str],
        capability_hash: str,
    ) -> RunOwner:
        if host.poll() is not None:
            from ..errors import SupervisorError

            raise SupervisorError("service-host 在 owner 建立前退出")
        return MacRunOwner(self.selection, host, capability_hash)

    def process_identity(self, pid: int) -> dict[str, Any]:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        try:
            result = subprocess.run(
                ["/bin/ps", "-p", str(pid), "-o", "lstart=", "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise IdentityError("macOS 进程身份不可读取") from exc
        fields = result.stdout.strip().split(None, 5)
        if result.returncode != 0 or len(fields) != 6:
            raise IdentityError("macOS 进程身份不可读取")
        return {
            "pid": pid,
            "startTime": " ".join(fields[:5]),
            "executable": fields[5],
        }

    def identity_matches(self, expected: dict[str, Any]) -> bool:
        pid = expected.get("pid")
        if not isinstance(pid, int):
            return False
        try:
            return self.process_identity(pid) == expected
        except IdentityError:
            return False
