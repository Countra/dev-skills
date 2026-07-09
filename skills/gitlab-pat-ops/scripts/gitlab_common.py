#!/usr/bin/env python3
"""GitLab PAT Ops 脚本的共享 REST 客户端。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


BASE_URL_ENV = "SKILL_GITLAB_BASE_URL"
TOKEN_ENVS = ("SKILL_GITLAB_PAT", "SKILL_GITLAB_TOKEN")
TOKEN_MASK = "***redacted***"
DEFAULT_TIMEOUT = 30


class GitLabSkillError(Exception):
    """skill 可预期错误的基类。"""


class MissingEnvironmentError(GitLabSkillError):
    """缺少必要环境变量。"""


class GitLabApiError(GitLabSkillError):
    """GitLab API 返回失败。"""

    def __init__(self, status: int, message: str, method: str, url: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.method = method
        self.url = url

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": self.status,
            "message": self.message,
            "method": self.method,
            "url": self.url,
        }


@dataclass(frozen=True)
class GitLabConfig:
    base_url: str
    api_url: str
    token: str
    token_source: str

    def public_dict(self) -> dict[str, str]:
        return {
            "base_url": self.base_url,
            "api_url": self.api_url,
            "token_source": self.token_source,
            "token": TOKEN_MASK,
        }


def normalize_api_url(value: str) -> tuple[str, str]:
    base = value.strip().rstrip("/")
    if not base:
        raise MissingEnvironmentError(f"{BASE_URL_ENV} 不能为空")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MissingEnvironmentError(f"{BASE_URL_ENV} 必须是 http(s) URL")
    if base.endswith("/api/v4"):
        root = base[: -len("/api/v4")]
        return root, base
    return base, f"{base}/api/v4"


def load_config() -> GitLabConfig:
    raw_base = os.environ.get(BASE_URL_ENV, "")
    token_source = ""
    token = ""
    for name in TOKEN_ENVS:
        value = os.environ.get(name, "")
        if value:
            token_source = name
            token = value
            break
    missing: list[str] = []
    if not raw_base:
        missing.append(BASE_URL_ENV)
    if not token:
        missing.append(" or ".join(TOKEN_ENVS))
    if missing:
        raise MissingEnvironmentError("缺少环境变量: " + ", ".join(missing))
    base_url, api_url = normalize_api_url(raw_base)
    return GitLabConfig(base_url=base_url, api_url=api_url, token=token, token_source=token_source)


def quote_id(value: str | int) -> str:
    return urllib.parse.quote(str(value), safe="")


def quote_file_path(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def redact(value: Any, token: str | None = None) -> Any:
    if isinstance(value, dict):
        return {key: redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    if isinstance(value, str):
        result = value
        if token:
            result = result.replace(token, TOKEN_MASK)
        for env_name in TOKEN_ENVS:
            env_value = os.environ.get(env_name)
            if env_value:
                result = result.replace(env_value, TOKEN_MASK)
        return result
    return value


def json_dumps(value: Any, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def print_json(value: Any, pretty: bool = False) -> None:
    print(json_dumps(value, pretty=pretty))


def parse_json_bytes(data: bytes) -> Any:
    if not data:
        return None
    text = data.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def error_message_from_body(body: Any) -> str:
    if isinstance(body, dict):
        for key in ("message", "error", "error_description"):
            if key in body:
                return str(body[key])
    if isinstance(body, list):
        return "; ".join(str(item) for item in body[:5])
    if body is None:
        return "GitLab API request failed"
    return str(body)


class GitLabClient:
    def __init__(
        self,
        config: GitLabConfig | None = None,
        opener: Any | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        sleep: Any = time.sleep,
    ) -> None:
        self.config = config or load_config()
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self.sleep = sleep

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            base = path
        else:
            base = f"{self.config.api_url}/{path.lstrip('/')}"
        clean_params = {
            key: value
            for key, value in (params or {}).items()
            if value is not None and value != "" and value is not False
        }
        if not clean_params:
            return base
        return f"{base}?{urllib.parse.urlencode(clean_params, doseq=True)}"

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        raw: bool = False,
        retry: int = 1,
        include_headers: bool = False,
    ) -> Any:
        url = self.build_url(path, params)
        body_bytes = None
        headers = {
            "Accept": "application/json",
            "PRIVATE-TOKEN": self.config.token,
            "User-Agent": "dev-skills-gitlab/1",
        }
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            request = urllib.request.Request(url, data=body_bytes, headers=headers, method=method.upper())
            try:
                response = self.opener(request, timeout=self.timeout)
                data = response.read()
                value = data if raw else parse_json_bytes(data)
                if include_headers:
                    return value, response.headers
                return value
            except urllib.error.HTTPError as exc:
                body = parse_json_bytes(exc.read())
                status = int(exc.code)
                if status in {429, 500, 502, 503, 504} and attempt < retry:
                    attempt += 1
                    self._sleep_before_retry(exc)
                    continue
                message = redact(error_message_from_body(body), self.config.token)
                raise GitLabApiError(status, str(message), method.upper(), redact(url, self.config.token)) from exc
            except urllib.error.URLError as exc:
                raise GitLabApiError(0, str(exc.reason), method.upper(), redact(url, self.config.token)) from exc

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        per_page: int = 100,
        max_pages: int | None = None,
    ) -> list[Any]:
        current_params = dict(params or {})
        current_params["per_page"] = min(max(int(per_page), 1), 100)
        current_params.setdefault("page", 1)
        values: list[Any] = []
        pages = 0
        next_url: str | None = None
        while True:
            if next_url:
                page_value, headers = self.request("GET", next_url, include_headers=True)
            else:
                page_value, headers = self.request("GET", path, params=current_params, include_headers=True)
            if isinstance(page_value, list):
                values.extend(page_value)
            else:
                values.append(page_value)
            pages += 1
            if max_pages is not None and pages >= max_pages:
                break
            next_url = next_url_from_headers(headers)
            if next_url:
                continue
            next_page = headers.get("X-Next-Page") or headers.get("x-next-page")
            if not next_page:
                break
            current_params["page"] = next_page
        return values

    def preview(self, method: str, path: str, params: dict[str, Any] | None, json_body: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "dry_run": True,
            "method": method.upper(),
            "url": redact(self.build_url(path, params), self.config.token),
            "json_body": summarize_body(json_body or {}),
        }

    def _sleep_before_retry(self, exc: urllib.error.HTTPError) -> None:
        retry_after = exc.headers.get("Retry-After")
        try:
            delay = min(float(retry_after), 2.0) if retry_after else 0.5
        except ValueError:
            delay = 0.5
        self.sleep(delay)


def next_url_from_headers(headers: Any) -> str | None:
    link_header = headers.get("Link") or headers.get("link")
    if not link_header:
        return None
    for part in str(link_header).split(","):
        if 'rel="next"' not in part and "rel=next" not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start >= 0 and end > start:
            return part[start + 1 : end]
    return None


def summarize_body(body: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in body.items():
        if key == "body" and isinstance(value, str):
            result[key] = {"length": len(value), "preview": value[:80]}
        elif key in {"description"} and isinstance(value, str):
            result[key] = {"length": len(value), "preview": value[:80]}
        else:
            result[key] = value
    return result


def parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_csv(value: str | None, label: str) -> list[int] | None:
    items = parse_csv(value)
    if items is None:
        return None
    result: list[int] = []
    for item in items:
        try:
            result.append(int(item))
        except ValueError as exc:
            raise GitLabSkillError(f"{label} 必须是逗号分隔的整数") from exc
    return result


def validate_yyyy_mm_dd(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise GitLabSkillError(f"{label} 必须使用 YYYY-MM-DD 格式") from exc
    return value


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP 超时时间，单位秒")


def add_pagination_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="自动读取全部分页")
    parser.add_argument("--page", type=int, default=1, help="页码")
    parser.add_argument("--per-page", type=int, default=100, help="每页数量，最大 100")


def output_result(value: Any, pretty: bool = False) -> None:
    print_json({"ok": True, "result": value}, pretty=pretty)


def output_error(error: Exception, pretty: bool = False) -> int:
    if isinstance(error, MissingEnvironmentError):
        value = {
            "ok": False,
            "error": str(error),
            "required": [BASE_URL_ENV, " or ".join(TOKEN_ENVS)],
            "powershell": [
                '$env:SKILL_GITLAB_BASE_URL="https://gitlab.example.com"',
                '$env:SKILL_GITLAB_PAT="..."',
            ],
        }
        print_json(value, pretty=pretty)
        return 2
    if isinstance(error, GitLabApiError):
        print_json(error.to_dict(), pretty=pretty)
        return 1
    print_json({"ok": False, "error": str(error)}, pretty=pretty)
    return 1


def make_client(args: argparse.Namespace) -> GitLabClient:
    return GitLabClient(timeout=getattr(args, "timeout", DEFAULT_TIMEOUT))


def request_list(
    client: GitLabClient,
    path: str,
    args: argparse.Namespace,
    params: dict[str, Any] | None = None,
) -> Any:
    final_params = dict(params or {})
    if getattr(args, "all", False):
        return client.paginate(path, params=final_params, per_page=getattr(args, "per_page", 100))
    final_params["page"] = getattr(args, "page", 1)
    final_params["per_page"] = min(max(int(getattr(args, "per_page", 100)), 1), 100)
    return client.request("GET", path, params=final_params)


def read_body_from_args(args: argparse.Namespace) -> tuple[str, str]:
    body_file = getattr(args, "body_file", None)
    body = getattr(args, "body", None)
    use_stdin = getattr(args, "stdin", False)
    provided = [bool(body_file), body is not None, bool(use_stdin)]
    if sum(1 for item in provided if item) != 1:
        raise GitLabSkillError("必须且只能使用 --body-file、--body 或 --stdin 之一提供正文")
    if body_file:
        with open(body_file, "r", encoding="utf-8") as handle:
            return handle.read(), "body-file"
    if body is not None:
        return body, "body-argument"
    return sys.stdin.read(), "stdin"


def read_optional_text_from_args(
    args: argparse.Namespace,
    text_attr: str,
    file_attr: str,
    stdin_attr: str,
    label: str,
) -> tuple[str | None, str]:
    text_value = getattr(args, text_attr, None)
    file_value = getattr(args, file_attr, None)
    stdin_value = getattr(args, stdin_attr, False)
    provided = [text_value is not None, bool(file_value), bool(stdin_value)]
    if sum(1 for item in provided if item) > 1:
        raise GitLabSkillError(f"{label} 只能从参数、文件或标准输入中选择一种来源")
    if file_value:
        with open(file_value, "r", encoding="utf-8") as handle:
            return handle.read(), f"{file_attr.replace('_', '-')}"
    if text_value is not None:
        return text_value, f"{text_attr.replace('_', '-')}"
    if stdin_value:
        return sys.stdin.read(), "stdin"
    return None, "none"


def add_body_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body-file", help="从 UTF-8 文本文件读取正文")
    group.add_argument("--body", help="直接传入正文；可能进入 shell history，优先使用 --body-file")
    group.add_argument("--stdin", action="store_true", help="从标准输入读取正文")


def add_optional_description_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--description", help="直接传入描述；较长内容优先使用 --description-file")
    group.add_argument("--description-file", help="从 UTF-8 文本文件读取描述")
    group.add_argument("--stdin", action="store_true", help="从标准输入读取描述")


def run_cli(handler: Any, argv: Iterable[str] | None = None) -> int:
    try:
        return int(handler(argv))
    except Exception as exc:  # noqa: BLE001
        return output_error(exc, pretty=False)
