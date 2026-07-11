"""GitLab PAT Ops 公共脚本 façade。"""

from __future__ import annotations

import argparse
import urllib.parse
from typing import Any, Iterable

from .config import (
    ALLOW_HTTP_ENV,
    BASE_URL_ENV,
    CA_BUNDLE_ENV,
    TEST_PROJECT_ENV,
    TOKEN_ENV,
    GitLabConfig,
    load_config,
    normalize_api_url,
)
from .errors import (
    ConfigurationError,
    ConflictError,
    GitLabApiError,
    GitLabSkillError,
    MissingEnvironmentError,
    NetworkError,
    PermissionDeniedError,
    ResponseLimitError,
    UnsupportedCapabilityError,
    UnsafeUrlError,
)
from .metadata import (
    add_description_update_args,
    add_due_date_update_args,
    add_id_list_update_args,
    add_label_update_args,
    add_milestone_update_args,
    description_update,
    due_date_update,
    id_list_update,
    label_update,
    milestone_update,
)
from .output import json_dumps, output_client_result, output_error, output_result, print_json
from .pagination import add_pagination_args, next_url_from_headers, request_list
from .resources import discussion_snapshot, project_path, project_snapshot, resource_path, resource_snapshot
from .safety import (
    WriteGuard,
    WriteIntent,
    add_confirmation_arg,
    execute_guarded_write,
    preflight_snapshot,
    summarize_body,
)
from .text_input import (
    add_body_args,
    add_optional_description_args,
    parse_csv,
    parse_bool,
    parse_int_csv,
    read_body_from_args,
    read_optional_text_from_args,
    require_nonempty_update,
    validate_iso8601,
    validate_yyyy_mm_dd,
)
from .templates import TEMPLATE_TYPES, read_template_content, template_params, template_snapshot
from .transport import DEFAULT_TIMEOUT, GitLabClient, parse_json_bytes, redact


def quote_id(value: str | int) -> str:
    return urllib.parse.quote(str(value), safe="")


def quote_file_path(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP 超时时间，单位秒")


def make_client(args: argparse.Namespace) -> GitLabClient:
    timeout = int(getattr(args, "timeout", DEFAULT_TIMEOUT))
    if timeout <= 0:
        raise GitLabSkillError("timeout 必须大于 0")
    return GitLabClient(timeout=timeout)


def run_cli(handler: Any, argv: Iterable[str] | None = None) -> int:
    try:
        return int(handler(argv))
    except Exception as exc:  # noqa: BLE001
        return output_error(exc, pretty=False)


__all__ = [
    "ALLOW_HTTP_ENV",
    "BASE_URL_ENV",
    "CA_BUNDLE_ENV",
    "TEST_PROJECT_ENV",
    "TOKEN_ENV",
    "TEMPLATE_TYPES",
    "ConfigurationError",
    "ConflictError",
    "GitLabApiError",
    "GitLabClient",
    "GitLabConfig",
    "GitLabSkillError",
    "MissingEnvironmentError",
    "NetworkError",
    "PermissionDeniedError",
    "ResponseLimitError",
    "UnsupportedCapabilityError",
    "UnsafeUrlError",
    "WriteGuard",
    "WriteIntent",
    "add_body_args",
    "add_common_args",
    "add_confirmation_arg",
    "add_description_update_args",
    "add_due_date_update_args",
    "add_id_list_update_args",
    "add_label_update_args",
    "add_milestone_update_args",
    "add_optional_description_args",
    "add_pagination_args",
    "execute_guarded_write",
    "json_dumps",
    "load_config",
    "description_update",
    "due_date_update",
    "id_list_update",
    "label_update",
    "make_client",
    "milestone_update",
    "next_url_from_headers",
    "normalize_api_url",
    "output_client_result",
    "output_error",
    "output_result",
    "parse_csv",
    "parse_bool",
    "parse_int_csv",
    "parse_json_bytes",
    "preflight_snapshot",
    "project_path",
    "project_snapshot",
    "print_json",
    "quote_file_path",
    "quote_id",
    "read_body_from_args",
    "read_optional_text_from_args",
    "read_template_content",
    "require_nonempty_update",
    "resource_path",
    "resource_snapshot",
    "discussion_snapshot",
    "redact",
    "request_list",
    "run_cli",
    "summarize_body",
    "template_params",
    "template_snapshot",
    "validate_iso8601",
    "validate_yyyy_mm_dd",
]
