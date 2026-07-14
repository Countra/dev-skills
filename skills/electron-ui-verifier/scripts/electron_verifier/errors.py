"""稳定错误码和异常模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|credential|private[_-]?key)",
    re.IGNORECASE,
)
URL_TEXT = re.compile(r"(?:https?|file|app)://[^\s'\"<>]+", re.IGNORECASE)
WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\r\n'\"]+")
POSIX_PATH = re.compile(r"(?<![A-Za-z0-9_:])/(?:[^/\s'\":]+/)+[^\s'\":]*")


def _public_text(value: str) -> str:
    value = URL_TEXT.sub("[URL]", value)
    value = WINDOWS_PATH.sub("[LOCAL_PATH]", value)
    return POSIX_PATH.sub("[LOCAL_PATH]", value)


def _public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else _public_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    if isinstance(value, tuple):
        return [_public_value(item) for item in value]
    if isinstance(value, str):
        return _public_text(value)
    return value


@dataclass(eq=False)
class VerifierError(RuntimeError):
    """携带稳定错误码、HTTP 状态和安全详情的领域错误。"""

    code: str
    message: str
    status: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def envelope(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "code": self.code,
            "error": _public_text(self.message),
        }
        if self.details:
            result["details"] = _public_value(self.details)
        return result


def require(condition: bool, code: str, message: str, **details: Any) -> None:
    """不满足领域前置条件时返回一致错误。"""

    if not condition:
        raise VerifierError(code, message, details=details)
