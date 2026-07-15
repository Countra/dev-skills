"""Verifier retention 的封闭策略模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import VerifierError


DAY_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class RetentionPolicy:
    terminal_age_seconds: int = 30 * DAY_SECONDS
    max_runs: int = 200
    max_total_bytes: int = 2 * 1024 * 1024 * 1024
    operation_expiration_seconds: int = 7 * DAY_SECONDS
    orphan_grace_seconds: int = 7 * DAY_SECONDS
    include_orphans: bool = False

    def __post_init__(self) -> None:
        numeric = {
            "terminalAgeSeconds": self.terminal_age_seconds,
            "maxRuns": self.max_runs,
            "maxTotalBytes": self.max_total_bytes,
            "operationExpirationSeconds": self.operation_expiration_seconds,
            "orphanGraceSeconds": self.orphan_grace_seconds,
        }
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in numeric.values()):
            raise VerifierError("retention_policy_invalid", "retention policy 数值必须是非负整数")
        if not isinstance(self.include_orphans, bool):
            raise VerifierError("retention_policy_invalid", "includeOrphans 必须是 boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "terminalAgeSeconds": self.terminal_age_seconds,
            "maxRuns": self.max_runs,
            "maxTotalBytes": self.max_total_bytes,
            "operationExpirationSeconds": self.operation_expiration_seconds,
            "orphanGraceSeconds": self.orphan_grace_seconds,
            "includeOrphans": self.include_orphans,
        }
