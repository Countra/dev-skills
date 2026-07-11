"""端点、认证和输出脱敏策略。"""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from .errors import VerifierError


SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|credential|private[_-]?key)",
    re.IGNORECASE,
)


def normalize_loopback_endpoint(value: str) -> str:
    """只接受显式 loopback HTTP CDP endpoint。"""

    candidate = value.strip().rstrip("/")
    if not candidate:
        raise VerifierError("cdp_endpoint_required", "CDP endpoint 不能为空")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise VerifierError("unsafe_cdp_endpoint", "CDP endpoint 只支持 http 或 https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerifierError("unsafe_cdp_endpoint", "CDP endpoint 不允许凭据、query 或 fragment")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc:
        raise VerifierError("unsafe_cdp_endpoint", "CDP endpoint 必须使用 loopback IP 字面量") from exc
    if not address.is_loopback:
        raise VerifierError("remote_cdp_not_allowed", "默认策略禁止连接远程 CDP endpoint")
    if parsed.port is None:
        raise VerifierError("cdp_port_required", "CDP endpoint 必须显式指定端口")
    if parsed.path not in {"", "/"}:
        raise VerifierError("unsafe_cdp_endpoint", "CDP endpoint 不能包含资源路径")
    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"{parsed.scheme}://{host}:{parsed.port}"


def validate_loopback_websocket(value: str) -> str:
    """校验 CDP discovery 返回的 WebSocket URL 未越出 loopback。"""

    candidate = value.strip()
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in {"ws", "wss"}:
        raise VerifierError("unsafe_cdp_websocket", "CDP WebSocket 只支持 ws 或 wss")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerifierError("unsafe_cdp_websocket", "CDP WebSocket 不允许凭据、query 或 fragment")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc:
        raise VerifierError("unsafe_cdp_websocket", "CDP WebSocket 必须使用 loopback IP 字面量") from exc
    if not address.is_loopback:
        raise VerifierError("remote_cdp_not_allowed", "CDP discovery 返回了远程 WebSocket")
    if parsed.port is None or not parsed.path.startswith("/devtools/"):
        raise VerifierError("unsafe_cdp_websocket", "CDP WebSocket 缺少端口或 devtools path")
    host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"{parsed.scheme}://{host}:{parsed.port}{parsed.path}"


def validate_bind_host(value: str) -> str:
    if value != "127.0.0.1":
        raise VerifierError("unsafe_bind_host", "verifier service 只允许绑定 127.0.0.1")
    return value


def token_matches(expected: str, authorization: str) -> bool:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return False
    return hmac.compare_digest(expected.encode("utf-8"), authorization[len(prefix) :].encode("utf-8"))


def redact(value: Any, *, text_limit: int = 20_000) -> Any:
    """递归移除敏感字段并限制文本体积。"""

    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item, text_limit=text_limit)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, text_limit=text_limit) for item in value]
    if isinstance(value, str) and len(value) > text_limit:
        return value[:text_limit] + "...[TRUNCATED]"
    return value


def secure_mode(path: Path, mode: int = 0o600) -> None:
    """使用 POSIX mode 或 Windows DACL 收紧到当前用户。"""

    try:
        os.chmod(path, mode)
        if os.name != "nt":
            return
        identity = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        principal = identity.stdout.strip()
        if identity.returncode != 0 or not principal:
            raise OSError(identity.stderr.strip() or "whoami 未返回当前用户")
        permission = f"{principal}:(OI)(CI)F" if path.is_dir() else f"{principal}:(F)"
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", permission],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or result.stdout.strip() or "icacls 执行失败")
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerifierError(
            "permission_hardening_failed",
            f"无法收紧敏感路径权限 {path}: {exc}",
            status=500,
        ) from exc
