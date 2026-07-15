"""服务端默认资源上限。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeLimits:
    """集中定义可审计的软硬资源上限。"""

    request_body_bytes: int = 1 * 1024 * 1024
    response_body_bytes: int = 4 * 1024 * 1024
    artifact_bytes: int = 32 * 1024 * 1024
    evaluate_result_bytes: int = 256 * 1024
    command_queue_size: int = 64
    event_count: int = 500
    event_bytes: int = 2 * 1024 * 1024
    workflow_steps: int = 200
    json_depth: int = 32
    action_timeout_ms: int = 30_000
    workflow_timeout_ms: int = 300_000
    operation_deadline_max_ms: int = 600_000
    operation_record_bytes: int = 4 * 1024 * 1024
    operation_history_limit: int = 1_000
    operation_cancel_grace_seconds: float = 2.0
    automation_start_timeout_seconds: float = 60.0
    readiness_timeout_margin_seconds: float = 15.0
    shutdown_grace_seconds: float = 8.0

    @property
    def service_readiness_timeout_seconds(self) -> float:
        """确保外层 readiness 晚于 automation 启动预算到期。"""
        return self.automation_start_timeout_seconds + self.readiness_timeout_margin_seconds


DEFAULT_LIMITS = RuntimeLimits()
