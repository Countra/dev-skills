"""Reviewer 对外稳定错误。"""

from __future__ import annotations


class ReviewError(Exception):
    """表示目标、契约或写入边界违反 reviewer 规则。"""

    def __init__(self, code: str, message: str, *, path: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def as_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "message": self.message, "path": self.path}

    def __str__(self) -> str:
        location = f" ({self.path})" if self.path else ""
        return f"[{self.code}] {self.message}{location}"
