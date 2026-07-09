#!/usr/bin/env python3
"""检查 GitLab skill 环境变量和认证状态。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_common import add_common_args, load_config, make_client, output_result, run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 GitLab skill 配置和认证状态")
    add_common_args(parser)
    parser.add_argument("--offline-check", action="store_true", help="只检查环境变量和 URL，不访问 GitLab")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()
    if args.offline_check:
        output_result({"environment": config.public_dict(), "live": False}, pretty=args.pretty)
        return 0
    client = make_client(args)
    user = client.request("GET", "/user")
    public_user = {
        "id": user.get("id") if isinstance(user, dict) else None,
        "username": user.get("username") if isinstance(user, dict) else None,
        "name": user.get("name") if isinstance(user, dict) else None,
    }
    output_result({"environment": config.public_dict(), "live": True, "user": public_user}, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
