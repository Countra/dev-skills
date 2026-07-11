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
    shutdown_grace_seconds: float = 8.0


DEFAULT_LIMITS = RuntimeLimits()
