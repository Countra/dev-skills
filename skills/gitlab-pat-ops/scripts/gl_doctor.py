#!/usr/bin/env python3
"""检查 GitLab PAT Ops 环境变量和认证状态。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import (
    GitLabApiError,
    add_common_args,
    load_config,
    make_client,
    output_client_result,
    output_result,
    run_cli,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 GitLab PAT Ops 配置和认证状态")
    add_common_args(parser)
    parser.add_argument("--offline-check", action="store_true", help="只检查环境变量和 URL，不访问 GitLab")
    return parser


def configuration_warnings(base_url: str) -> list[str]:
    if base_url.lower().startswith("http://"):
        return ["当前 GitLab 连接使用明文 HTTP，PAT 可能被网络路径观察。"]
    return []


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()
    warnings = configuration_warnings(config.base_url)
    if args.offline_check:
        output_result(
            {"environment": config.public_dict(), "live": False, "warnings": warnings},
            pretty=args.pretty,
            operation="doctor.offline",
        )
        return 0
    client = make_client(args)
    user = client.request("GET", "/user")
    public_user = {
        "id": user.get("id") if isinstance(user, dict) else None,
        "username": user.get("username") if isinstance(user, dict) else None,
        "name": user.get("name") if isinstance(user, dict) else None,
    }
    optional: dict[str, object] = {}
    for name, path, fields in (
        ("personal_access_token", "/personal_access_tokens/self", ("id", "name", "scopes", "active", "revoked", "expires_at", "last_used_at")),
        ("metadata", "/metadata", ("version", "revision", "enterprise")),
    ):
        try:
            value = client.request("GET", path)
        except GitLabApiError as exc:
            if exc.status not in {403, 404}:
                raise
            optional[name] = {
                "available": False,
                "http_status": exc.status,
                "request_id": exc.request_id,
            }
            continue
        optional[name] = {
            "available": True,
            "value": {field: value.get(field) for field in fields} if isinstance(value, dict) else None,
        }
    output_client_result(
        client,
        {"environment": config.public_dict(), "live": True, "warnings": warnings, "user": public_user, **optional},
        pretty=args.pretty,
        operation="doctor.live",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
