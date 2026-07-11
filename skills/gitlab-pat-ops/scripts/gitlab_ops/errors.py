"""GitLab PAT Ops 的稳定错误模型。"""

from __future__ import annotations

from typing import Any


class GitLabSkillError(Exception):
    """所有可预期 skill 错误的基类。"""

    code = "skill_error"
    exit_code = 2

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        outcome: str = "not_sent",
        request_id: str | None = None,
        retryable: bool = False,
        guidance: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.outcome = outcome
        self.request_id = request_id
        self.retryable = retryable
        self.guidance = guidance

    def to_error_dict(self) -> dict[str, Any]:
        """返回不含请求体和凭据的错误对象。"""
        value: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "outcome": self.outcome,
            "retryable": self.retryable,
        }
        if self.http_status is not None:
            value["http_status"] = self.http_status
        if self.guidance:
            value["guidance"] = self.guidance
        return value


class ConfigurationError(GitLabSkillError):
    """配置缺失或不安全。"""

    code = "configuration_error"
    exit_code = 2


class MissingEnvironmentError(ConfigurationError):
    """缺少必要环境变量。"""

    code = "missing_environment"


class AuthenticationError(GitLabSkillError):
    """PAT 无效或 scope 不满足。"""

    code = "authentication_failed"
    exit_code = 3


class PermissionDeniedError(GitLabSkillError):
    """资源不存在或当前身份无权限。"""

    code = "permission_denied"
    exit_code = 4


class ConflictError(GitLabSkillError):
    """预检状态或写入确认已漂移。"""

    code = "conflict"
    exit_code = 5


class TransientError(GitLabSkillError):
    """限流或服务端瞬时失败。"""

    code = "transient_failure"
    exit_code = 6


class NetworkError(GitLabSkillError):
    """网络、TLS 或协议失败。"""

    code = "network_failure"
    exit_code = 7


class ResponseLimitError(NetworkError):
    """响应、分页或输入超过预算。"""

    code = "response_limit_exceeded"


class UnsupportedCapabilityError(GitLabSkillError):
    """请求的能力被当前 skill 明确禁止。"""

    code = "unsupported_capability"
    exit_code = 8


class UnsafeUrlError(NetworkError):
    """目标 URL 越过已批准的 GitLab API 边界。"""

    code = "unsafe_url"


class GitLabApiError(GitLabSkillError):
    """GitLab API 返回的稳定错误。"""

    def __init__(
        self,
        status: int,
        message: str,
        method: str,
        url: str,
        *,
        request_id: str | None = None,
        outcome: str = "not_sent",
        retryable: bool = False,
        guidance: str | None = None,
    ) -> None:
        error_type = _error_type_for_status(status)
        super().__init__(
            message,
            http_status=status or None,
            outcome=outcome,
            request_id=request_id,
            retryable=retryable,
            guidance=guidance,
        )
        self.code = error_type.code
        self.exit_code = error_type.exit_code
        self.status = status
        self.method = method
        self.url = url


def _error_type_for_status(status: int) -> type[GitLabSkillError]:
    if status == 401:
        return AuthenticationError
    if status in {403, 404}:
        return PermissionDeniedError
    if status in {409, 412, 422}:
        return ConflictError
    if status == 429 or status >= 500:
        return TransientError
    return GitLabSkillError
