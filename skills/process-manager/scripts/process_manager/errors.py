"""process-manager 的稳定错误模型。"""

from __future__ import annotations

from typing import Any

_AUTHENTICATED_HEALTH_ERROR_STATES = {
    "runtime_insecure": ("runtime_insecure", False),
    "runtime_permission_denied": ("runtime_permission_denied", None),
    "environment_unverifiable": ("environment_unverifiable", None),
    "resource_usage_unverifiable": ("environment_unverifiable", None),
}


def authenticated_health_error_state(
    status: int,
    response: dict[str, Any],
    manager_instance_id: str,
) -> tuple[str, bool | None] | None:
    if (
        status < 400
        or set(response) != {"ok", "operation", "error", "meta"}
        or response.get("ok") is not False
        or response.get("operation") != "health"
        or response.get("meta") != {"managerInstanceId": manager_instance_id}
    ):
        return None
    error = response.get("error")
    if (
        not isinstance(error, dict)
        or not {"code", "message", "retryable"} <= set(error)
        or set(error) - {"code", "message", "retryable", "diagnostics", "recommendedAction"}
        or not isinstance(error.get("code"), str)
        or not isinstance(error.get("message"), str)
        or not isinstance(error.get("retryable"), bool)
    ):
        return None
    code = error["code"]
    return _AUTHENTICATED_HEALTH_ERROR_STATES.get(code)


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
        recommended_action: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or {}
        self.recommended_action = recommended_action
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
        if self.recommended_action is not None:
            value["recommendedAction"] = self.recommended_action
        return value


class ConfigurationError(PMError):
    code = "configuration_error"


class ValidationError(ConfigurationError):
    code = "validation_error"


class ContextInvalidError(ValidationError):
    code = "context_invalid"


class ManagerOfflineError(PMError):
    code = "manager_offline"
    http_status = 503
    exit_code = 3
    retryable = True


class ManagerAbsentError(PMError):
    code = "manager_absent"
    http_status = 503
    exit_code = 3


class RuntimeUninitializedError(PMError):
    code = "runtime_uninitialized"
    http_status = 409
    exit_code = 4


class ManagerStartingError(PMError):
    code = "manager_starting"
    http_status = 503
    exit_code = 3
    retryable = True


class ManagerStoppingError(ManagerStartingError):
    code = "manager_stopping"


class ManagerStaleError(PMError):
    code = "manager_stale"
    http_status = 409
    exit_code = 4


class ManagerUnresponsiveError(PMError):
    code = "manager_unresponsive"
    http_status = 503
    exit_code = 3


class RuntimeInsecureError(PMError):
    code = "runtime_insecure"
    http_status = 403
    exit_code = 7


class RuntimePermissionDeniedError(PMError):
    code = "runtime_permission_denied"
    http_status = 403
    exit_code = 7


class EnvironmentUnverifiableError(PMError):
    code = "environment_unverifiable"
    http_status = 503
    exit_code = 7


class RuntimeCorruptError(PMError):
    code = "runtime_corrupt"
    http_status = 500
    exit_code = 6


class OperationConflictError(PMError):
    code = "operation_conflict"
    http_status = 409
    exit_code = 4
    retryable = True


class OperationTimeoutError(PMError):
    code = "operation_timeout"
    http_status = 408
    exit_code = 9
    retryable = True


class ControlTimeoutError(PMError):
    code = "control_timeout"
    http_status = 408
    exit_code = 9
    retryable = True


class ConflictError(PMError):
    code = "state_conflict"
    http_status = 409
    exit_code = 4


class ResourceBudgetError(ConflictError):
    code = "resource_budget_exceeded"


class ResourceUsageUnverifiableError(EnvironmentUnverifiableError):
    code = "resource_usage_unverifiable"


class OwnedRunsConfirmationRequiredError(ConflictError):
    code = "owned_runs_confirmation_required"


class RestartConfirmationRequiredError(OwnedRunsConfirmationRequiredError):
    code = "restart_confirmation_required"


class StopConfirmationRequiredError(OwnedRunsConfirmationRequiredError):
    code = "stop_confirmation_required"


class IdentityError(PMError):
    code = "identity_mismatch"
    http_status = 409
    exit_code = 5


class NotFoundError(PMError):
    code = "not_found"
    http_status = 404
    exit_code = 8


class SessionNotFoundError(NotFoundError):
    code = "session_not_found"


class SessionExpiredError(ConflictError):
    code = "session_expired"


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


class SessionCleanupPendingError(SupervisorError):
    code = "session_cleanup_pending"
    retryable = True


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
