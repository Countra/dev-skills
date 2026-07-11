"""稳定错误码和异常模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
            "error": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


def require(condition: bool, code: str, message: str, **details: Any) -> None:
    """不满足领域前置条件时返回一致错误。"""

    if not condition:
        raise VerifierError(code, message, details=details)
