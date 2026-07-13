"""Skill Evaluation Lab 的稳定、可机器处理错误模型。"""

from __future__ import annotations

from typing import Any


class LabError(Exception):
    """所有可预期错误的基类。"""

    code = "LAB_ERROR"
    exit_code = 2

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        guidance: str | None = None,
        outcome: str = "not_started",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or type(self).code
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


class ContractError(LabError):
    """输入或证据文档不符合闭合契约。"""

    code = "CONTRACT_INVALID"
    exit_code = 2


class PathError(LabError):
    """路径越界、链接或覆盖约束被破坏。"""

    code = "PATH_INVALID"
    exit_code = 3


class SkillError(LabError):
    """目标 Skill 无法形成静态证据。"""

    code = "SKILL_INVALID"
    exit_code = 4


class PacketError(LabError):
    """人工观察工作包无法安全生成或读取。"""

    code = "PACKET_INVALID"
    exit_code = 5


class ObservationError(LabError):
    """用户提供的观察证据不完整或不一致。"""

    code = "OBSERVATION_INVALID"
    exit_code = 6


class ReportError(LabError):
    """证据层不兼容，无法生成透明报告。"""

    code = "REPORT_INVALID"
    exit_code = 7
