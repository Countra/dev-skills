#!/usr/bin/env python3
"""Executor 状态与证据契约的稳定错误类型。"""

from __future__ import annotations


class StateError(Exception):
    """ledger、run-state 或其证据违反状态机约束。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
