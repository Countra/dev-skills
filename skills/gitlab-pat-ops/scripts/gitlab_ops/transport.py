"""带同源、预算和重试边界的 GitLab REST transport。"""

from __future__ import annotations

import email.utils
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from .config import GitLabConfig, TOKEN_MASK, load_config
from .errors import GitLabApiError, NetworkError, ResponseLimitError, UnsafeUrlError


DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_REQUEST_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BUDGET_SECONDS = 8.0
SAFE_METHODS = frozenset({"GET", "HEAD"})
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
UNKNOWN_WRITE_GUIDANCE = "写入结果未知；先重新读取目标资源确认状态，禁止直接重放写请求"


def redact(value: Any, token: str | None = None) -> Any:
    if isinstance(value, dict):
        return {key: redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    if isinstance(value, str) and token:
        return value.replace(token, TOKEN_MASK)
    return value


def parse_json_bytes(data: bytes) -> Any:
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError("GitLab API 返回了无效 JSON") from exc


def _header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return str(value) if value is not None else None


def _read_bounded(response: Any, max_bytes: int) -> bytes:
    content_length = _header(getattr(response, "headers", None), "Content-Length")
    if content_length:
        try:
            parsed_length = int(content_length)
            if parsed_length < 0:
                raise NetworkError("GitLab 返回了负数 Content-Length")
            if parsed_length > max_bytes:
                raise ResponseLimitError("GitLab 响应超过 max-response-bytes")
        except ValueError as exc:
            raise NetworkError("GitLab 返回了无效 Content-Length") from exc
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ResponseLimitError("GitLab 响应超过 max-response-bytes")
    return data


def _message_from_error_body(data: bytes, token: str) -> str:
    try:
        body = parse_json_bytes(data)
    except NetworkError:
        return "GitLab API 请求失败"
    message: Any = None
    if isinstance(body, dict):
        for key in ("message", "error", "error_description"):
            if isinstance(body.get(key), (str, int, float, bool)):
                message = body[key]
                break
    if message is None:
        return "GitLab API 请求失败"
    return str(redact(str(message), token))[:500]


class SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """只允许安全读取在同一 API root 内跳转。"""

    def __init__(self, config: GitLabConfig) -> None:
        super().__init__()
        self.config = config

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if req.get_method().upper() not in SAFE_METHODS:
            raise UnsafeUrlError("写请求不允许自动重定向")
        self.config.validate_api_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _normalize_query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return [_normalize_query_value(item) for item in value]
    return value


class GitLabClient:
    """GitLab REST client，所有 PAT 请求都经过同一安全边界。"""

    def __init__(
        self,
        config: GitLabConfig | None = None,
        opener: Any | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_budget_seconds: float = DEFAULT_RETRY_BUDGET_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self.config = config or load_config()
        self.timeout = timeout
        self.max_response_bytes = max(1, int(max_response_bytes))
        self.max_request_bytes = max(1, int(max_request_bytes))
        self.max_attempts = max(1, max_attempts)
        self.retry_budget_seconds = max(0.0, retry_budget_seconds)
        self.sleep = sleep
        self.clock = clock
        self.wall_clock = wall_clock
        self.random_value = random_value
        self.last_meta: dict[str, Any] = {}
        if opener is None:
            self.opener = urllib.request.build_opener(
                SameOriginRedirectHandler(self.config),
                urllib.request.HTTPSHandler(context=self.config.ssl_context()),
            )
        else:
            self.opener = opener

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith(("http://", "https://")):
            base = self.config.validate_api_url(path)
        else:
            base = f"{self.config.api_url}/{path.lstrip('/')}"
            self.config.validate_api_url(base)
        clean_params = {
            key: _normalize_query_value(value)
            for key, value in (params or {}).items()
            if value is not None and value != ""
        }
        if not clean_params:
            return base
        parsed = urllib.parse.urlsplit(base)
        existing = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query = urllib.parse.urlencode(existing + list(clean_params.items()), doseq=True)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))

    def _open(self, request: urllib.request.Request) -> Any:
        if callable(self.opener):
            return self.opener(request, timeout=self.timeout)
        return self.opener.open(request, timeout=self.timeout)

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        *,
        raw: bool = False,
        include_headers: bool = False,
    ) -> Any:
        normalized_method = method.upper()
        url = self.build_url(path, params)
        body_bytes = None if json_body is None else json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        if body_bytes is not None and len(body_bytes) > self.max_request_bytes:
            raise ResponseLimitError("GitLab 请求体超过 max-request-bytes")
        headers = {
            "Accept": "application/octet-stream" if raw else "application/json",
            "PRIVATE-TOKEN": self.config.token,
            "User-Agent": "dev-skills-gitlab-pat-ops",
        }
        if body_bytes is not None:
            headers["Content-Type"] = "application/json"
        started = self.clock()
        attempt = 0
        while True:
            attempt += 1
            request = urllib.request.Request(url, data=body_bytes, headers=headers, method=normalized_method)
            try:
                response = self._open(request)
                response_headers = getattr(response, "headers", {})
                self.last_meta = self._response_meta(response_headers, attempt)
                try:
                    data = _read_bounded(response, self.max_response_bytes)
                except ResponseLimitError as exc:
                    if normalized_method not in SAFE_METHODS:
                        raise ResponseLimitError(
                            exc.message,
                            outcome="unknown",
                            request_id=_header(response_headers, "X-Request-Id"),
                            retryable=False,
                            guidance=UNKNOWN_WRITE_GUIDANCE,
                        ) from exc
                    raise
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
                if raw:
                    value = data
                else:
                    try:
                        value = redact(parse_json_bytes(data), self.config.token)
                    except NetworkError as exc:
                        if normalized_method not in SAFE_METHODS:
                            raise NetworkError(
                                exc.message,
                                outcome="unknown",
                                request_id=_header(response_headers, "X-Request-Id"),
                                retryable=False,
                                guidance=UNKNOWN_WRITE_GUIDANCE,
                            ) from exc
                        raise
                return (value, response_headers) if include_headers else value
            except urllib.error.HTTPError as exc:
                status = int(exc.code)
                request_id = _header(exc.headers, "X-Request-Id")
                self.last_meta = self._response_meta(exc.headers, attempt)
                try:
                    data = _read_bounded(exc, self.max_response_bytes)
                except ResponseLimitError as limit_error:
                    ambiguous = normalized_method not in SAFE_METHODS
                    raise ResponseLimitError(
                        limit_error.message,
                        http_status=status,
                        outcome="unknown" if ambiguous else "rejected",
                        request_id=request_id,
                        retryable=False,
                        guidance=UNKNOWN_WRITE_GUIDANCE if ambiguous else None,
                    ) from limit_error
                finally:
                    exc.close()
                if self._can_retry(normalized_method, status, attempt, started):
                    self._sleep_before_retry(exc.headers, attempt, started)
                    continue
                message = _message_from_error_body(data, self.config.token)
                ambiguous = normalized_method not in SAFE_METHODS and status >= 500
                raise GitLabApiError(
                    status,
                    message,
                    normalized_method,
                    str(redact(url, self.config.token)),
                    request_id=request_id,
                    outcome="unknown" if ambiguous else "rejected",
                    retryable=normalized_method in SAFE_METHODS and status in RETRYABLE_STATUS,
                    guidance=UNKNOWN_WRITE_GUIDANCE if ambiguous else None,
                ) from exc
            except UnsafeUrlError:
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if self._can_retry(normalized_method, 0, attempt, started):
                    self._sleep_before_retry(None, attempt, started)
                    continue
                outcome = "unknown" if normalized_method not in SAFE_METHODS else "not_sent"
                raise NetworkError(
                    "GitLab 网络或 TLS 请求失败",
                    outcome=outcome,
                    retryable=normalized_method in SAFE_METHODS,
                    guidance=UNKNOWN_WRITE_GUIDANCE if outcome == "unknown" else None,
                ) from exc

    def paginate(self, path: str, params: dict[str, Any] | None = None, **limits: Any) -> list[Any]:
        from .pagination import paginate

        return paginate(self, path, params=params, **limits)

    def preview(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
        *,
        operation: str = "gitlab.write",
        target: dict[str, Any] | None = None,
        preflight: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .safety import build_write_preview

        return build_write_preview(
            self,
            operation=operation,
            method=method,
            path=path,
            params=params,
            json_body=json_body,
            target=target,
            preflight=preflight,
        )

    def _can_retry(self, method: str, status: int, attempt: int, started: float) -> bool:
        retryable = status == 0 or status in RETRYABLE_STATUS
        return (
            method in SAFE_METHODS
            and retryable
            and attempt < self.max_attempts
            and self.clock() - started < self.retry_budget_seconds
        )

    def _sleep_before_retry(self, headers: Any, attempt: int, started: float) -> None:
        delay = self._retry_delay(headers, attempt)
        remaining = self.retry_budget_seconds - (self.clock() - started)
        self.sleep(max(0.0, min(delay, remaining)))

    def _retry_delay(self, headers: Any, attempt: int) -> float:
        retry_after = _header(headers, "Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    parsed = email.utils.parsedate_to_datetime(retry_after)
                except (TypeError, ValueError):
                    parsed = None
                if parsed is not None:
                    return max(0.0, parsed.timestamp() - self.wall_clock())
        reset = _header(headers, "RateLimit-Reset")
        if reset:
            try:
                return max(0.0, float(reset) - self.wall_clock())
            except ValueError:
                pass
        return min(0.5 * (2 ** (attempt - 1)) + self.random_value() * 0.25, 4.0)

    @staticmethod
    def _response_meta(headers: Any, attempts: int) -> dict[str, Any]:
        return {
            "request_id": _header(headers, "X-Request-Id"),
            "pagination": None,
            "rate_limit": {
                "remaining": _header(headers, "RateLimit-Remaining"),
                "reset": _header(headers, "RateLimit-Reset"),
            },
            "attempts": attempts,
        }
