"""关键运行数据的原子文件操作。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import VerifierError


def canonical_json_bytes(value: Any) -> bytes:
    """生成跨运行稳定的 JSON 字节。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    mode: int = 0o600,
    max_bytes: int | None = None,
    durable: bool = True,
) -> None:
    """在同目录完成写入、同步与替换，失败时不暴露半文件。"""

    if max_bytes is not None and len(data) > max_bytes:
        raise VerifierError(
            "artifact_too_large",
            f"数据超过允许上限：{len(data)} > {max_bytes}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            if os.name != "nt":
                os.chmod(temp_path, mode)
            handle.write(data)
            if durable:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temp_path, path)
        if os.name != "nt":
            os.chmod(path, mode)
        if durable:
            _sync_directory(path.parent)
    except OSError as exc:
        raise VerifierError(
            "atomic_write_failed",
            f"无法原子写入 {path}: {exc}",
            status=500,
        ) from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def atomic_write_json(
    path: Path,
    value: Any,
    *,
    mode: int = 0o600,
    max_bytes: int | None = None,
    pretty: bool = True,
    durable: bool = True,
) -> None:
    if pretty:
        data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    else:
        data = canonical_json_bytes(value) + b"\n"
    atomic_write_bytes(path, data, mode=mode, max_bytes=max_bytes, durable=durable)


def atomic_write_text(
    path: Path,
    value: str,
    *,
    mode: int = 0o600,
    max_bytes: int | None = None,
) -> None:
    atomic_write_bytes(path, value.encode("utf-8"), mode=mode, max_bytes=max_bytes)


def exclusive_write_json(path: Path, value: Any, *, mode: int = 0o600) -> bool:
    """只在目标不存在时写入决定标记，返回是否由本次创建。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(value) + b"\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        return False
    except OSError as exc:
        raise VerifierError("exclusive_write_failed", f"无法创建决定文件 {path}: {exc}", status=500) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_directory(path.parent)
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise VerifierError("exclusive_write_failed", f"无法提交决定文件 {path}: {exc}", status=500) from exc
    return True


def resolve_under(root: Path, candidate: Path, *, must_exist: bool = False) -> Path:
    """解析受控根目录内路径，阻断目录穿越和外部路径。"""

    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise VerifierError(
            "path_outside_runtime",
            f"路径必须位于 verifier 运行根目录：{resolved_root}",
        )
    if must_exist and not resolved.exists():
        raise VerifierError("path_not_found", f"路径不存在：{resolved}", status=404)
    return resolved
