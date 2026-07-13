"""子进程环境、敏感值识别与证据脱敏。"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from .errors import SuiteError


SAFE_ENV_NAMES = {
    "COMSPEC",
    "HOME",
    "LANG",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "USERPROFILE",
    "WINDIR",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
}
SAFE_ENV_PREFIXES = ("LC_",)
SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:AUTH|AUTHORIZATION|COOKIE|CREDENTIAL|PASS(?:WORD|WD)?|PAT|SECRET|TOKEN)(?:$|[_-])"
    r"|(?:API|ACCESS|PRIVATE)[_-]?KEY",
    re.IGNORECASE,
)
REDACTED = "[REDACTED]"


def is_sensitive_key(name: str) -> bool:
    """判断环境变量或结构化字段名是否表达凭据语义。"""
    return bool(SENSITIVE_KEY.search(name))


def build_child_env(
    source: Mapping[str, str] | None = None,
    *,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """只继承运行必需的非敏感环境，并拒绝显式注入凭据。"""
    source_env = os.environ if source is None else source
    result: dict[str, str] = {}
    for name, value in source_env.items():
        upper = name.upper()
        allowed = upper in SAFE_ENV_NAMES or upper.startswith(SAFE_ENV_PREFIXES)
        if allowed and not is_sensitive_key(name):
            result[name] = value
    for name, value in (extra or {}).items():
        if is_sensitive_key(name):
            raise SuiteError(
                f"拒绝向子进程注入敏感环境变量：{name}",
                path="$.runner.environment",
                guidance="使用本机认证存储，不要把凭据写入 suite 或证据",
            )
        result[name] = value
    result.setdefault("PYTHONUTF8", "1")
    result.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return result


def sensitive_values(source: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """收集可用于证据脱敏的环境凭据值，忽略过短值以减少误替换。"""
    source_env = os.environ if source is None else source
    values = {value for name, value in source_env.items() if is_sensitive_key(name) and len(value) >= 4}
    return tuple(sorted(values, key=len, reverse=True))


def redact_text(value: str, *, secrets: tuple[str, ...] = ()) -> str:
    """替换已知敏感值，不尝试猜测普通业务文本。"""
    result = value
    for secret in secrets:
        result = result.replace(secret, REDACTED)
    return result


def redact_value(value: Any, *, secrets: tuple[str, ...] = ()) -> Any:
    """递归清理准备写入证据文件的结构化值。"""
    if isinstance(value, dict):
        return {
            str(key): REDACTED if is_sensitive_key(str(key)) else redact_value(item, secrets=secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item, secrets=secrets) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets=secrets)
    return value
