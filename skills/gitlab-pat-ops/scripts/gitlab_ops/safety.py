"""GitLab 写操作的预览、指纹和预检绑定。"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from .errors import ConflictError, GitLabSkillError


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _redact_secret(value: Any, secret: str) -> Any:
    if isinstance(value, dict):
        return {key: _redact_secret(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret(item, secret) for item in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "***redacted***")
    return value


def _summarize_value(key: str, value: Any) -> Any:
    if key in {"body", "description"} and isinstance(value, str):
        return {
            "length": len(value),
            "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        }
    if isinstance(value, dict):
        return {item_key: _summarize_value(item_key, item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_summarize_value(key, item) for item in value]
    return value


def summarize_body(body: dict[str, Any]) -> dict[str, Any]:
    return {key: _summarize_value(key, value) for key, value in body.items()}


def preflight_snapshot(
    value: Any,
    fields: tuple[str, ...],
    *,
    hash_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """只保留写入竞态检测所需字段，正文仅记录哈希。"""
    if not isinstance(value, dict):
        raise GitLabSkillError("预检响应不是 JSON object")
    result: dict[str, Any] = {}
    for field in fields:
        item = value.get(field)
        if field in hash_fields and isinstance(item, str):
            result[field + "_sha256"] = hashlib.sha256(item.encode("utf-8")).hexdigest()
        else:
            result[field] = item
    return result


def build_write_preview(
    client: Any,
    *,
    operation: str,
    method: str,
    path: str,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
    target: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = client.build_url(path, params)
    parsed = urllib.parse.urlsplit(url)
    canonical = {
        "origin": list(client.config.origin),
        "operation": operation,
        "method": method.upper(),
        "path": parsed.path,
        "query": sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)),
        "body": json_body or {},
        "target": target or {},
        "preflight": preflight or {},
    }
    fingerprint = "sha256:" + hashlib.sha256(_canonical_json(canonical)).hexdigest()
    token = str(getattr(client.config, "token", ""))
    return {
        "dry_run": True,
        "operation": operation,
        "method": method.upper(),
        "path": parsed.path,
        "params": _redact_secret(dict(params or {}), token),
        "target": _redact_secret(target or {}, token),
        "json_body": _redact_secret(summarize_body(json_body or {}), token),
        "preflight": _redact_secret(preflight or {}, token),
        "confirm_fingerprint": fingerprint,
    }


def add_confirmation_arg(parser: Any) -> None:
    parser.add_argument(
        "--confirm",
        metavar="SHA256_FINGERPRINT",
        help="只接受前一次 dry-run 输出的完整 confirm_fingerprint",
    )


@dataclass(frozen=True)
class WriteIntent:
    """一次受控写入的规范化意图。"""

    operation: str
    method: str
    path: str
    params: dict[str, Any] | None
    json_body: dict[str, Any] | None
    target: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None

    def preview(self, client: Any) -> dict[str, Any]:
        return build_write_preview(
            client,
            operation=self.operation,
            method=self.method,
            path=self.path,
            params=self.params,
            json_body=self.json_body,
            target=self.target,
            preflight=self.preflight,
        )


class WriteGuard:
    """集中执行指纹确认、漂移检查和单次写请求。"""

    def __init__(self, client: Any) -> None:
        self.client = client

    def execute(
        self,
        intent: WriteIntent,
        *,
        confirm: str | None,
        reread_preflight: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        preview = intent.preview(self.client)
        if not confirm:
            return preview
        if confirm != preview["confirm_fingerprint"]:
            raise ConflictError("确认指纹与当前目标、参数或预检状态不匹配")
        if reread_preflight is not None and reread_preflight() != (intent.preflight or {}):
            raise ConflictError("写入前目标状态已变化，请重新 dry-run")
        if intent.method.upper() not in {"POST", "PUT"}:
            raise GitLabSkillError("受控写只允许 POST 或 PUT")
        result = self.client.request(
            intent.method,
            intent.path,
            params=intent.params,
            json_body=intent.json_body,
        )
        return {
            "applied": True,
            "operation": intent.operation,
            "confirm_fingerprint": confirm,
            "result": result,
        }


def execute_guarded_write(
    client: Any,
    *,
    operation: str,
    method: str,
    path: str,
    params: dict[str, Any] | None,
    json_body: dict[str, Any] | None,
    confirm: str | None,
    target: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
    reread_preflight: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    intent = WriteIntent(
        operation=operation,
        method=method,
        path=path,
        params=params,
        json_body=json_body,
        target=target,
        preflight=preflight,
    )
    return WriteGuard(client).execute(intent, confirm=confirm, reread_preflight=reread_preflight)
