#!/usr/bin/env python3
"""Executor review handoff 的稳定错误类型。"""


class ReviewGateError(Exception):
    """Reviewer 公共契约或 Executor 交接约束不满足。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
