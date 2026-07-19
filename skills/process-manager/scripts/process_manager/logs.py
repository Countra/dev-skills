"""轮转日志、有界 JSON 写入与 runtime 精确字节核算。"""

from __future__ import annotations

import io
import json
import os
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .atomic import atomic_write_bytes, open_private_binary_append, retry_windows_file_operation
from .errors import RequestError, ResourceUsageUnverifiableError, StateError

MAX_TAIL_LINES, MAX_TAIL_BYTES, MAX_HOST_STATE_BYTES = 10000, 1024 * 1024, 64 * 1024
RESOURCE_CAPS = {
    "state": 16 * 1024 * 1024, "transaction": 32 * 1024 * 1024, "config": 1024 * 1024,
    "identity": 64 * 1024, "operation": 64 * 1024, "bootstrap": 64 * 1024, "tombstone": 16 * 1024,
    "token": 4 * 1024, "session": 64 * 1024, "run": 1024 * 1024, "host": MAX_HOST_STATE_BYTES,
}


def serialized_json(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StateError("JSON 值无法序列化") from exc


def write_capped_json(path: Path, value: Any, max_bytes: int) -> None:
    data = serialized_json(value)
    if len(data) > max_bytes:
        raise StateError(f"JSON 文件超过写入上限: {path.name}")
    atomic_write_bytes(path, data)


def write_capped_bytes(path: Path, data: bytes, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise StateError(f"文件超过写入上限: {path.name}")
    atomic_write_bytes(path, data)


class RotatingTextLog(io.TextIOBase):
    """在每次写入前执行 bounded rotation，不回退到无界 append。"""

    def __init__(self, path: Path, max_bytes: int, backups: int, adapter: Any) -> None:
        self.path = adapter.validate_runtime_path(path)
        self.max_bytes, self.backups, self.adapter = max_bytes, backups, adapter
        self._lock = threading.Lock()
        self._failed = False
        self.adapter.secure_directory(self.path.parent)
        self._validate_generations()
        self._handle = self._open_handle()

    def _open_handle(self) -> BinaryIO:
        handle = open_private_binary_append(self.path)
        try:
            self.adapter.secure_file(self.path)
        except BaseException:
            handle.close()
            self._failed = True
            raise
        return handle

    @property
    def encoding(self) -> str:
        return "utf-8"

    def _validate_generations(self) -> None:
        for index in range(self.backups + 2):
            candidate = self.path if index == 0 else self.path.with_name(f"{self.path.name}.{index}")
            candidate = self.adapter.validate_runtime_path(candidate)
            if not candidate.exists():
                continue
            if index > self.backups:
                raise StateError(f"manager 日志 generation 超出配置: {candidate.name}")
            self.adapter.verify_file(candidate)
            if candidate.stat().st_size > self.max_bytes:
                raise StateError(f"manager 日志 generation 超过 maxBytes: {candidate.name}")

    def _rotate(self) -> None:
        self._handle.close()
        try:
            if self.backups:
                oldest = self.path.with_name(f"{self.path.name}.{self.backups}")
                retry_windows_file_operation(lambda: oldest.unlink(missing_ok=True))
                for index in range(self.backups - 1, 0, -1):
                    source = self.path.with_name(f"{self.path.name}.{index}")
                    target = self.path.with_name(f"{self.path.name}.{index + 1}")
                    if source.exists():
                        retry_windows_file_operation(lambda s=source, t=target: s.replace(t))
                if self.path.exists():
                    target = self.path.with_name(f"{self.path.name}.1")
                    retry_windows_file_operation(lambda: self.path.replace(target))
            else:
                retry_windows_file_operation(lambda: self.path.unlink(missing_ok=True))
        finally:
            self._handle = self._open_handle()

    def write(self, value: str) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed manager log")
        if self._failed:
            raise StateError("manager 日志 writer 已进入失败状态")
        if not isinstance(value, str):
            raise TypeError("manager log 只接受 text")
        data = value.encode("utf-8", errors="replace")
        with self._lock:
            current = self.path.stat().st_size
            if current and current + len(data) > self.max_bytes:
                self._rotate()
            if len(data) > self.max_bytes:
                data = data[-self.max_bytes:]
            self._handle.write(data)
        return len(value)

    def flush(self) -> None:
        if not self.closed and hasattr(self, "_handle") and not self._handle.closed:
            with self._lock:
                self._handle.flush()

    def close(self) -> None:
        if not self.closed:
            try:
                super().close()
            finally:
                handle = getattr(self, "_handle", None)
                if handle is not None:
                    with self._lock:
                        handle.close()

    def isatty(self) -> bool:
        return False


@dataclass
class RuntimeUsage:
    used: int = 0
    fixed: int = 0
    metadata: int = 0
    manager_logs: int = 0
    run_capacity: int = 0

    @property
    def reserved(self) -> int:
        return self.fixed + self.metadata + self.manager_logs + self.run_capacity


class RuntimeAccountant:
    """只核算中央索引能够证明的 exact contained runtime 文件。"""
    def __init__(self, store: Any, state: dict[str, Any]) -> None:
        self.store, self.state = store, state
        self.config, self.adapter, self.paths = store.config, store.adapter, store.paths
        self.usage = RuntimeUsage()
        self._seen: set[str] = set()
        self._deadline = time.monotonic() + 2.0
        self._operations = 0

    def _failure(self, message: str, path: Path | None = None) -> ResourceUsageUnverifiableError:
        diagnostics = {"pathName": path.name} if path is not None else {}
        return ResourceUsageUnverifiableError(message, diagnostics=diagnostics, recommended_action="doctor")

    def _file(self, path: Path, *, cap: int | None = None, required: bool = False) -> int:
        try:
            self._operations += 1
            if self._operations > 20000 or time.monotonic() > self._deadline:
                raise self._failure("runtime 核算超过全局工作预算", path)
            path = self.adapter.validate_runtime_path(path)
            if not path.exists():
                if required:
                    raise self._failure("indexed runtime 文件缺失", path)
                return 0
            self.adapter.verify_file(path)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise self._failure("runtime 路径不是 regular file", path)
            size = int(info.st_size)
            if cap is not None and size > cap:
                raise self._failure("runtime 文件超过 closed metadata cap", path)
            identity = os.path.normcase(str(path))
            if identity not in self._seen:
                self._seen.add(identity)
                self.usage.used += size
            return size
        except ResourceUsageUnverifiableError:
            raise
        except (OSError, StateError) as exc:
            raise self._failure("runtime 文件字节无法验证", path) from exc

    def tree_bytes(self, root: Path, *, max_entries: int = 128, max_depth: int = 4) -> int:
        deadline, entries, total = min(self._deadline, time.monotonic() + 0.5), 0, 0

        def visit(path: Path, depth: int) -> None:
            nonlocal entries, total
            if depth > max_depth or entries >= max_entries or time.monotonic() > deadline:
                raise self._failure("runtime 目录核算超过 bounded limit", root)
            self._operations += 1
            if self._operations > 20000:
                raise self._failure("runtime 核算超过全局工作预算", root)
            try:
                checked = self.adapter.validate_runtime_path(path)
                info = checked.lstat()
                entries += 1
                if stat.S_ISREG(info.st_mode):
                    total += self._file(checked)
                    return
                if not stat.S_ISDIR(info.st_mode):
                    raise self._failure("runtime 目录包含非 regular entry", checked)
                self.adapter.verify_directory(checked)
                for child in checked.iterdir():
                    visit(child, depth + 1)
            except ResourceUsageUnverifiableError:
                raise
            except (OSError, StateError) as exc:
                raise self._failure("runtime 目录字节无法验证", path) from exc

        visit(root, 0)
        return total

    def _control(self) -> None:
        caps = (
            (self.paths.config, RESOURCE_CAPS["config"]),
            (self.paths.processes, RESOURCE_CAPS["state"]),
            (self.paths.processes_backup, RESOURCE_CAPS["state"]),
            (self.paths.state_root / "processes.pending.json", RESOURCE_CAPS["transaction"]),
            (self.paths.manager, RESOURCE_CAPS["identity"]),
            (self.paths.operation, RESOURCE_CAPS["operation"]),
            (self.paths.bootstrap, RESOURCE_CAPS["bootstrap"]),
            (self.paths.state_root / "manager-launchd.plist", RESOURCE_CAPS["bootstrap"]),
            (self.paths.token, RESOURCE_CAPS["token"]),
        )
        for path, cap in caps:
            self._file(path, cap=cap)
        for path in (self.paths.manager_lock, self.paths.operation_lock, self.paths.repository_lock):
            self._file(path, cap=RESOURCE_CAPS["token"])
        self.usage.metadata += (
            2 * RESOURCE_CAPS["config"] + 3 * RESOURCE_CAPS["state"]
            + 2 * RESOURCE_CAPS["transaction"]
            + 2 * (RESOURCE_CAPS["identity"] + RESOURCE_CAPS["operation"] + RESOURCE_CAPS["bootstrap"])
            + RESOURCE_CAPS["token"]
        )

    def _log_stream(self, path: Path, max_bytes: int, backups: int) -> int:
        total = 0
        for index in range(backups + 2):
            candidate = path if index == 0 else path.with_name(f"{path.name}.{index}")
            if index > backups and self.adapter.validate_runtime_path(candidate).exists():
                raise self._failure("日志 generation 超出配置", candidate)
            if index <= backups:
                total += self._file(candidate, cap=max_bytes)
        return total

    def _manager_logs(self) -> None:
        for stream in ("stdout", "stderr"):
            self._log_stream(
                self.paths.logs / f"manager-{stream}.log",
                self.config.log_max_bytes,
                self.config.log_backups,
            )
        self.usage.manager_logs = 2 * self.config.log_max_bytes * (self.config.log_backups + 1)

    def _run(self, record: dict[str, Any]) -> None:
        run_dir = self.adapter.validate_runtime_path(Path(record["runDir"]))
        if not run_dir.is_dir():
            raise self._failure("indexed runDir 缺失", run_dir)
        before = self.usage.used
        total = self.tree_bytes(run_dir)
        self._file(Path(record["processFile"]), cap=RESOURCE_CAPS["run"], required=True)
        self._file(run_dir / "host-state.json", cap=RESOURCE_CAPS["host"])
        logs = record.get("public", {}).get("serviceConfig", {}).get("logs", {})
        max_bytes, backups = logs.get("maxBytes"), logs.get("backups")
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or isinstance(backups, bool)
            or not isinstance(backups, int)
            or max_bytes <= 0
            or not 0 <= backups <= 10
        ):
            raise self._failure("run log config 无法核算", run_dir)
        log_actual = sum(
            self._log_stream(run_dir / f"{stream}.log", max_bytes, backups)
            for stream in ("stdout", "stderr")
        )
        if record.get("status") in self.store.active_states:
            self.usage.metadata += 2 * (RESOURCE_CAPS["run"] + RESOURCE_CAPS["host"])
            self.usage.run_capacity += 2 * max_bytes * (backups + 1)
        else:
            self.usage.fixed += total
        if self.usage.used - before < total:
            raise self._failure("runDir 文件 identity 发生重叠", run_dir)
        if log_actual > 2 * max_bytes * (backups + 1):
            raise self._failure("run log actual 超过 reservation", run_dir)

    def measure(self) -> RuntimeUsage:
        self._control()
        self._manager_logs()
        transaction = self.store._read_pending_transaction()  # noqa: SLF001
        for session_id in transaction["deleteSessions"] if transaction else []:
            self.usage.fixed += self._file(
                self.store.schema.session_path(session_id), cap=RESOURCE_CAPS["session"], required=True)
        for session_id in self.state["sessions"]:
            self._file(
                self.store.schema.session_path(session_id),
                cap=RESOURCE_CAPS["session"],
                required=True,
            )
            self.usage.metadata += 2 * RESOURCE_CAPS["session"]
        moved: dict[str, Path] = {}
        for journal in self.state["pendingPrunes"].values():
            if journal["phase"] not in {"intent", "quarantined"}:
                continue
            source = self.paths.state_root / Path(journal["source"])
            quarantine = self.paths.state_root / Path(journal["quarantine"])
            if journal["keepRun"]:
                stable = (source / "process.json").is_file() and not quarantine.exists()
                relocated, target = quarantine.is_file() and not (source / "process.json").exists(), source
            else:
                stable = source.is_dir() and not quarantine.exists()
                relocated, target = quarantine.is_dir() and not source.exists(), quarantine
            if (journal["phase"] == "quarantined" and not relocated) or (
                not stable and not relocated
            ):
                raise self._failure("pending prune 路径组合无法核算", target)
            if relocated:
                moved[journal["processKey"]] = target
        for key, record in self.state["processes"].items():
            target = moved.get(key)
            if target is None:
                self._run(record)
                continue
            self.usage.fixed += self.tree_bytes(target)
        for tombstone in self.state["tombstones"].values():
            retained = tombstone.get("retainedPath")
            if retained is not None:
                self.usage.fixed += self.tree_bytes(self.paths.state_root / Path(retained))
        for journal in self.state["pendingPrunes"].values():
            source, quarantine = (self.paths.state_root / Path(journal[key])
                                  for key in ("source", "quarantine"))
            if journal["phase"] == "committed" and not journal["keepRun"]:
                if source.exists():
                    raise self._failure("committed prune source 仍然存在", source)
                if quarantine.exists():
                    self.usage.fixed += self.tree_bytes(quarantine)
        return self.usage


def rotated_paths(path: Path, backups: int) -> list[Path]:
    return [*(path.with_name(f"{path.name}.{index}") for index in range(backups, 0, -1)), path]


def _open_log(path: Path) -> BinaryIO | None:
    try:
        if path.is_symlink():
            raise StateError(f"日志路径不能是 symlink: {path.name}")
        return path.open("rb")
    except FileNotFoundError:
        return None
    except StateError:
        raise
    except OSError as exc:
        raise StateError(f"日志不可读: {path.name}") from exc


def read_log_tail(path: Path, backups: int, *, tail_lines: int, max_bytes: int) -> dict[str, Any]:
    if not 1 <= tail_lines <= MAX_TAIL_LINES:
        raise RequestError(f"tail 必须是 1-{MAX_TAIL_LINES}")
    if not 1024 <= max_bytes <= MAX_TAIL_BYTES:
        raise RequestError(f"maxBytes 必须是 1024-{MAX_TAIL_BYTES}")
    total_bytes = 0
    remaining = max_bytes
    selected: list[tuple[Path, bytes]] = []
    identities: set[tuple[int, int]] = set()
    for candidate in reversed(rotated_paths(path, backups)):
        handle = _open_log(candidate)
        if handle is None:
            continue
        try:
            with handle:
                stat = os.fstat(handle.fileno())
                identity = (int(stat.st_dev), int(stat.st_ino))
                if identity in identities:
                    continue
                identities.add(identity)
                size = int(stat.st_size)
                total_bytes += size
                if remaining <= 0:
                    continue
                take = min(size, remaining)
                handle.seek(size - take)
                data = handle.read(take)
                selected.append((candidate, data))
                remaining -= len(data)
        except OSError as exc:
            raise StateError(f"日志读取失败: {candidate.name}") from exc
    selected.reverse()
    payload = b"".join(data for _, data in selected)
    text = payload.decode("utf-8", errors="replace")
    lines = text.splitlines()
    truncated = total_bytes > len(payload) or len(lines) > tail_lines
    return {
        "lines": lines[-tail_lines:],
        "bytesRead": len(payload),
        "availableBytes": total_bytes,
        "truncated": truncated,
        "files": [{"name": candidate.name, "bytesRead": len(data)} for candidate, data in selected],
    }


class IncrementalLogScanner:
    """按文件身份跟踪轮转日志，整个 probe 只读取 scanBytes。"""

    def __init__(self, path: Path, backups: int, scan_bytes: int) -> None:
        self.path = path
        self.backups = backups
        self.scan_bytes = scan_bytes
        self.bytes_scanned = 0
        self._offsets: dict[tuple[int, int], int] = {}
        self._buffer = bytearray()
        self._initialized = False

    @property
    def exhausted(self) -> bool:
        return self.bytes_scanned >= self.scan_bytes

    @property
    def text(self) -> str:
        return bytes(self._buffer).decode("utf-8", errors="replace")

    def scan(self) -> bool:
        remaining = self.scan_bytes - self.bytes_scanned
        if remaining <= 0:
            return False
        appended = False
        if not self._initialized:
            chunks: list[bytes] = []
            identities: set[tuple[int, int]] = set()
            for candidate in reversed(rotated_paths(self.path, self.backups)):
                handle = _open_log(candidate)
                if handle is None:
                    continue
                try:
                    with handle:
                        stat = os.fstat(handle.fileno())
                        identity = (int(stat.st_dev), int(stat.st_ino))
                        if identity in identities:
                            continue
                        identities.add(identity)
                        size = int(stat.st_size)
                        self._offsets[identity] = size
                        if remaining <= 0:
                            continue
                        take = min(size, remaining)
                        handle.seek(size - take)
                        data = handle.read(take)
                        chunks.append(data)
                        self.bytes_scanned += len(data)
                        remaining -= len(data)
                except OSError as exc:
                    raise StateError("readiness 日志读取失败") from exc
            for data in reversed(chunks):
                self._buffer.extend(data)
                appended = appended or bool(data)
            self._initialized = True
            return appended
        current_identities: set[tuple[int, int]] = set()
        for candidate in rotated_paths(self.path, self.backups):
            if remaining <= 0:
                break
            handle = _open_log(candidate)
            if handle is None:
                continue
            try:
                with handle:
                    stat = os.fstat(handle.fileno())
                    identity = (int(stat.st_dev), int(stat.st_ino))
                    if identity in current_identities:
                        continue
                    current_identities.add(identity)
                    size = int(stat.st_size)
                    offset = self._offsets.get(identity, 0)
                    offset = 0 if size < offset else offset
                    take = min(size - offset, remaining)
                    if take > 0:
                        handle.seek(offset)
                        data = handle.read(take)
                        self._buffer.extend(data)
                        self.bytes_scanned += len(data)
                        remaining -= len(data)
                        offset += len(data)
                        appended = appended or bool(data)
                    self._offsets[identity] = offset
            except OSError as exc:
                raise StateError("readiness 日志读取失败") from exc
        self._offsets = {identity: offset for identity, offset in self._offsets.items() if identity in current_identities}
        return appended
