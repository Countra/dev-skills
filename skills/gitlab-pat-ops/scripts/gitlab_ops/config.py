"""GitLab PAT Ops 的封闭环境配置。"""

from __future__ import annotations

import ipaddress
import os
import ssl
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError, MissingEnvironmentError, UnsafeUrlError


BASE_URL_ENV = "SKILL_GITLAB_BASE_URL"
TOKEN_ENV = "SKILL_GITLAB_PAT"
CA_BUNDLE_ENV = "SKILL_GITLAB_CA_BUNDLE"
ALLOW_HTTP_ENV = "SKILL_GITLAB_ALLOW_HTTP"
TEST_PROJECT_ENV = "SKILL_GITLAB_TEST_PROJECT"
TOKEN_MASK = "***redacted***"


def _parse_bool(name: str, value: str | None) -> bool:
    if value is None or value.strip() == "":
        return False
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} 必须是 true 或 false")


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _effective_port(parsed: urllib.parse.SplitResult) -> int:
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme.lower() == "https" else 80


def _validate_path(path: str, label: str) -> str:
    normalized = path.rstrip("/") or "/"
    decoded_parts = urllib.parse.unquote(normalized).split("/")
    if any(part in {".", ".."} for part in decoded_parts):
        raise ConfigurationError(f"{label} 不能包含路径穿越片段")
    return normalized


@dataclass(frozen=True)
class GitLabConfig:
    """只包含进程内需要的 GitLab 连接配置。"""

    base_url: str
    api_url: str
    api_path: str
    token: str
    token_source: str = TOKEN_ENV
    ca_bundle: str | None = None
    allow_http: bool = False
    test_project: str | None = None

    @property
    def origin(self) -> tuple[str, str, int]:
        parsed = urllib.parse.urlsplit(self.api_url)
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), _effective_port(parsed)

    def public_dict(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "api_url": self.api_url,
            "token_source": self.token_source,
            "token": TOKEN_MASK,
            "ca_bundle": self.ca_bundle,
            "http_allowed": self.allow_http,
            "test_project": self.test_project,
        }

    def validate_api_url(self, value: str) -> str:
        parsed = urllib.parse.urlsplit(value)
        if parsed.username or parsed.password:
            raise UnsafeUrlError("GitLab API URL 不合法")
        try:
            origin = (parsed.scheme.lower(), (parsed.hostname or "").lower(), _effective_port(parsed))
        except ValueError as exc:
            raise UnsafeUrlError("GitLab API URL 端口不合法") from exc
        path = _validate_path(parsed.path, "GitLab API URL")
        if origin != self.origin or not (path == self.api_path or path.startswith(self.api_path + "/")):
            raise UnsafeUrlError("GitLab API URL 已越过配置的 origin 或 API path")
        if parsed.fragment:
            raise UnsafeUrlError("GitLab API URL 不能包含 fragment")
        return urllib.parse.urlunsplit(parsed)

    def ssl_context(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=self.ca_bundle)


def normalize_api_url(value: str, *, allow_http: bool = False) -> tuple[str, str]:
    raw = value.strip().rstrip("/")
    if not raw:
        raise MissingEnvironmentError(f"{BASE_URL_ENV} 不能为空")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError(f"{BASE_URL_ENV} 必须是完整的 http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError(f"{BASE_URL_ENV} 不能包含 userinfo、query 或 fragment")
    try:
        parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{BASE_URL_ENV} 端口不合法") from exc
    if parsed.scheme.lower() == "http" and not (allow_http or _is_loopback(parsed.hostname)):
        raise ConfigurationError(f"非 loopback HTTP 需要显式设置 {ALLOW_HTTP_ENV}=true")
    path = _validate_path(parsed.path, BASE_URL_ENV)
    if path.endswith("/api/v4"):
        api_path = path
        base_path = path[: -len("/api/v4")] or "/"
    else:
        base_path = path
        api_path = ("" if path == "/" else path) + "/api/v4"
    authority = parsed.netloc
    base_url = urllib.parse.urlunsplit((parsed.scheme.lower(), authority, "" if base_path == "/" else base_path, "", ""))
    api_url = urllib.parse.urlunsplit((parsed.scheme.lower(), authority, api_path, "", ""))
    return base_url.rstrip("/"), api_url.rstrip("/")


def load_config() -> GitLabConfig:
    raw_base = os.environ.get(BASE_URL_ENV, "")
    token = os.environ.get(TOKEN_ENV, "")
    missing = [name for name, value in ((BASE_URL_ENV, raw_base), (TOKEN_ENV, token)) if not value.strip()]
    if missing:
        raise MissingEnvironmentError("缺少环境变量: " + ", ".join(missing))
    allow_http = _parse_bool(ALLOW_HTTP_ENV, os.environ.get(ALLOW_HTTP_ENV))
    base_url, api_url = normalize_api_url(raw_base, allow_http=allow_http)
    ca_bundle = os.environ.get(CA_BUNDLE_ENV) or None
    if ca_bundle:
        path = Path(ca_bundle)
        if not path.is_absolute() or not path.is_file():
            raise ConfigurationError(f"{CA_BUNDLE_ENV} 必须指向现存的绝对文件")
        ca_bundle = str(path.resolve())
    api_path = urllib.parse.urlsplit(api_url).path
    return GitLabConfig(
        base_url=base_url,
        api_url=api_url,
        api_path=api_path,
        token=token,
        ca_bundle=ca_bundle,
        allow_http=allow_http,
        test_project=os.environ.get(TEST_PROJECT_ENV) or None,
    )
