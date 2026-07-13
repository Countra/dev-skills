"""Skill Evaluation Lab 的稳定错误模型。"""

from __future__ import annotations

from typing import Any


class LabError(Exception):
    """所有可预期错误的基类。"""

    code = "lab_error"
    exit_code = 2

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        guidance: str | None = None,
        outcome: str = "not_started",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
        self.guidance = guidance
        self.outcome = outcome

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "outcome": self.outcome,
        }
        if self.path:
            value["path"] = self.path
        if self.guidance:
            value["guidance"] = self.guidance
        return value


class SuiteError(LabError):
    """Suite 契约无效。"""

    code = "suite_invalid"
    exit_code = 2


class DependencyError(LabError):
    """运行依赖不可用。"""

    code = "dependency_missing"
    exit_code = 3


class AuthorizationError(LabError):
    """调用需要显式授权。"""

    code = "authorization_required"
    exit_code = 4


class UnsupportedError(LabError):
    """当前 runner 或能力不受支持。"""

    code = "unsupported_capability"
    exit_code = 5


class ExecutionError(LabError):
    """已经开始的执行失败。"""

    code = "execution_failed"
    exit_code = 6


class InconclusiveError(LabError):
    """证据不足以得出结论。"""

    code = "inconclusive"
    exit_code = 7
