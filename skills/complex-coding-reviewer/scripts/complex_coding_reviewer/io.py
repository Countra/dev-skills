"""Reviewer 的安全路径、JSON 与原子写入工具。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .errors import ReviewError


ATOMIC_REPLACE_RETRY_DELAYS = (0.025, 0.05, 0.1, 0.2)


def canonical_json_bytes(value: Any) -> bytes:
    """返回跨平台稳定、无多余空白的 UTF-8 JSON。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    """计算审查制品原始字节的 SHA-256。"""

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReviewError(
            "REVIEW_OUTPUT_UNREADABLE",
            f"无法读取审查制品以计算摘要：{exc}",
            path=str(path),
        ) from exc


def load_json_object(path: Path, *, code: str = "REVIEW_CONTRACT_UNREADABLE") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReviewError(code, "JSON 文件不存在。", path=str(path)) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError(code, f"无法读取 JSON：{exc}", path=str(path)) from exc
    if not isinstance(value, dict):
        raise ReviewError(code, "JSON 根值必须是 object。", path=str(path))
    return value


def resolve_root(path: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReviewError(
            "REVIEW_TARGET_ROOT_INVALID",
            f"{label} 不存在或不可访问：{exc}",
            path=str(path),
        ) from exc
    if not resolved.is_dir():
        raise ReviewError(
            "REVIEW_TARGET_ROOT_INVALID",
            f"{label} 必须是目录。",
            path=str(path),
        )
    return resolved


def normalize_relative_path(value: str) -> str:
    if not isinstance(value, str):
        raise ReviewError(
            "REVIEW_TARGET_PATH_INVALID",
            "目标路径必须是字符串。",
            path=repr(value),
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReviewError(
            "REVIEW_TARGET_PATH_ENCODING_INVALID",
            "目标路径必须可编码为 UTF-8。",
            path=repr(value),
        ) from exc
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ReviewError(
            "REVIEW_TARGET_PATH_INVALID",
            "目标路径必须是非空、无上跳的相对路径。",
            path=value,
        )
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts:
        raise ReviewError(
            "REVIEW_TARGET_PATH_INVALID",
            "目标路径不能只包含当前目录标记。",
            path=value,
        )
    return "/".join(parts)


def resolve_relative_file(root: Path, value: str, *, must_exist: bool = True) -> Path:
    normalized = normalize_relative_path(value)
    candidate = (root / Path(*normalized.split("/"))).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ReviewError(
            "REVIEW_TARGET_PATH_ESCAPE",
            "目标路径经符号链接解析后越出根目录。",
            path=value,
        ) from exc
    if must_exist:
        try:
            strict_candidate = candidate.resolve(strict=True)
        except OSError as exc:
            raise ReviewError(
                "REVIEW_TARGET_MISSING",
                f"目标文件不存在或不可访问：{exc}",
                path=value,
            ) from exc
        try:
            strict_candidate.relative_to(root)
        except ValueError as exc:
            raise ReviewError(
                "REVIEW_TARGET_PATH_ESCAPE",
                "目标文件经符号链接解析后越出根目录。",
                path=value,
            ) from exc
        if not strict_candidate.is_file():
            raise ReviewError(
                "REVIEW_TARGET_NOT_FILE",
                "目标必须是普通文件。",
                path=value,
            )
        candidate = strict_candidate
    return candidate


def read_bytes(path: Path, *, display_path: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ReviewError(
            "REVIEW_TARGET_UNREADABLE",
            f"无法读取目标文件：{exc}",
            path=display_path,
        ) from exc


def resolve_new_output(output: Path, *, review_root: Path | None) -> Path:
    parent = output.parent.resolve(strict=False)
    if review_root is not None:
        try:
            review_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ReviewError(
                "REVIEW_OUTPUT_UNWRITABLE",
                f"无法准备 review root：{exc}",
                path=str(review_root),
            ) from exc
        root = resolve_root(review_root, label="review root")
        try:
            parent.relative_to(root)
        except ValueError as exc:
            raise ReviewError(
                "REVIEW_OUTPUT_PATH_ESCAPE",
                "输出路径必须位于显式 review root 内。",
                path=str(output),
            ) from exc
    if output.exists() or output.is_symlink():
        raise ReviewError(
            "REVIEW_OUTPUT_EXISTS",
            "审查 attempt 不可覆盖已有输出。",
            path=str(output),
        )
    try:
        parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = parent.resolve(strict=True)
    except OSError as exc:
        raise ReviewError(
            "REVIEW_OUTPUT_UNWRITABLE",
            f"无法准备输出目录：{exc}",
            path=str(output),
        ) from exc
    if review_root is not None:
        root = review_root.resolve(strict=True)
        try:
            resolved_parent.relative_to(root)
        except ValueError as exc:
            raise ReviewError(
                "REVIEW_OUTPUT_PATH_ESCAPE",
                "输出目录经符号链接解析后越出 review root。",
                path=str(output),
            ) from exc
    return resolved_parent / output.name


def resolve_review_artifact(path: Path, review_root: Path) -> Path:
    root = resolve_root(review_root, label="review root")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReviewError(
            "REVIEW_OUTPUT_UNREADABLE",
            f"审查产物不存在或不可访问：{exc}",
            path=str(path),
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ReviewError(
            "REVIEW_OUTPUT_PATH_ESCAPE",
            "审查产物必须位于显式 review root 内。",
            path=str(path),
        ) from exc
    if not resolved.is_file():
        raise ReviewError("REVIEW_OUTPUT_UNREADABLE", "审查产物必须是普通文件。", path=str(path))
    return resolved


def review_artifact_ref(path: Path, review_root: Path) -> str:
    """返回 review root 内制品的 canonical 相对引用。"""

    root = resolve_root(review_root, label="review root")
    resolved = resolve_review_artifact(path, root)
    return resolved.relative_to(root).as_posix()


def normalize_review_ref(value: str) -> str:
    """校验并规范化 review root 内的相对制品引用。"""

    if not isinstance(value, str):
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "审查制品引用必须是字符串。",
            path=repr(value),
        )
    normalized = normalize_relative_path(value)
    if normalized != value:
        raise ReviewError(
            "REVIEW_OUTPUT_PATH_ESCAPE",
            "审查制品引用必须使用 canonical 正斜杠相对路径。",
            path=value,
        )
    return normalized


def resolve_review_ref(value: str, review_root: Path) -> Path:
    """解析 review root 内已存在的相对制品引用。"""

    root = resolve_root(review_root, label="review root")
    normalized = normalize_review_ref(value)
    return resolve_review_artifact(root / Path(*normalized.split("/")), root)


def replace_with_bounded_retry(source: Path, destination: Path) -> None:
    """有限重试 Windows 共享冲突，不掩盖持续权限或路径错误。"""

    for attempt in range(len(ATOMIC_REPLACE_RETRY_DELAYS) + 1):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            retryable = isinstance(exc, PermissionError) or getattr(
                exc, "winerror", None
            ) in {5, 32}
            if not retryable or attempt == len(ATOMIC_REPLACE_RETRY_DELAYS):
                raise
            time.sleep(ATOMIC_REPLACE_RETRY_DELAYS[attempt])


def write_new_bytes(output: Path, data: bytes, *, review_root: Path | None = None) -> Path:
    resolved = resolve_new_output(output, review_root=review_root)
    temporary: Path | None = None
    reserved = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            dir=resolved.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            reservation = os.open(resolved, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ReviewError(
                "REVIEW_OUTPUT_EXISTS",
                "审查 attempt 不可覆盖已有输出。",
                path=str(output),
            ) from exc
        os.close(reservation)
        reserved = True
        replace_with_bounded_retry(temporary, resolved)
        reserved = False
    except ReviewError:
        raise
    except OSError as exc:
        raise ReviewError(
            "REVIEW_OUTPUT_UNWRITABLE",
            f"无法原子写入输出：{exc}",
            path=str(output),
        ) from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)
        if reserved and resolved.exists():
            resolved.unlink(missing_ok=True)
    return resolved


def write_new_json(output: Path, value: Any, *, review_root: Path | None = None) -> Path:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return write_new_bytes(output, rendered.encode("utf-8"), review_root=review_root)


def write_new_text(output: Path, value: str, *, review_root: Path | None = None) -> Path:
    rendered = value if value.endswith("\n") else value + "\n"
    return write_new_bytes(output, rendered.encode("utf-8"), review_root=review_root)
