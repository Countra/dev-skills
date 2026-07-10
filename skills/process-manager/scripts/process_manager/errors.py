"""process-manager 的稳定错误模型。"""

from __future__ import annotations

from typing import Any


class PMError(RuntimeError):
    """所有可安全返回给调用方的错误基类。"""

    code = "process_manager_error"
    http_status = 400
    exit_code = 2
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        diagnostics: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}
        if retryable is not None:
            self.retryable = retryable

    def public_dict(self, *, include_diagnostics: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if include_diagnostics and self.diagnostics:
            value["diagnostics"] = self.diagnostics
        return value


class ConfigurationError(PMError):
    code = "configuration_error"


class ValidationError(ConfigurationError):
    code = "validation_error"


class ManagerOfflineError(PMError):
    code = "manager_offline"
    http_status = 503
    exit_code = 3
    retryable = True


class ConflictError(PMError):
    code = "state_conflict"
    http_status = 409
    exit_code = 4


class IdentityError(PMError):
    code = "identity_mismatch"
    http_status = 409
    exit_code = 5


class NotFoundError(PMError):
    code = "not_found"
    http_status = 404
    exit_code = 8


class StateError(PMError):
    code = "state_error"
    http_status = 500
    exit_code = 6


class RuntimeRebuildRequiredError(StateError):
    code = "runtime_rebuild_required"


class SupervisorError(PMError):
    code = "supervisor_unavailable"
    http_status = 503
    exit_code = 7


class UnsupportedPlatformError(SupervisorError):
    code = "unsupported_platform"


class RequestError(PMError):
    code = "invalid_request"
    http_status = 400


class ReadinessTimeoutError(PMError):
    code = "readiness_timeout"
    http_status = 408
    exit_code = 9


class ProbeLimitError(PMError):
    code = "probe_limit_exceeded"
    http_status = 422
    exit_code = 9
