#!/usr/bin/env python3
"""预览或显式执行 verifier workspace 的引用安全清理。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, print_json, resolve_config_path
from electron_verifier.config import ServiceConfig
from electron_verifier.errors import VerifierError
from electron_verifier.retention import RetentionService
from electron_verifier.retention_policy import DAY_SECONDS, RetentionPolicy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="默认只预览 verifier retention 候选；apply 需要 fingerprint 和确认。")
    add_common_args(parser)
    parser.add_argument("mode", nargs="?", choices=("preview", "apply"), default="preview")
    parser.add_argument("--terminal-age-days", type=int, default=30)
    parser.add_argument("--max-runs", type=int, default=200)
    parser.add_argument("--max-total-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--operation-expiration-days", type=int, default=7)
    parser.add_argument("--orphan-grace-days", type=int, default=7)
    parser.add_argument("--include-orphans", action="store_true")
    parser.add_argument("--fingerprint", help="apply 必须使用当前 preview 返回的 fingerprint")
    parser.add_argument("--confirm", action="store_true", help="确认执行 preview 中的精确候选集合")
    return parser


def _policy(args: argparse.Namespace) -> RetentionPolicy:
    values = (
        args.terminal_age_days,
        args.max_runs,
        args.max_total_bytes,
        args.operation_expiration_days,
        args.orphan_grace_days,
    )
    if any(value < 0 for value in values):
        raise EVError("retention policy 参数不能为负数")
    return RetentionPolicy(
        terminal_age_seconds=args.terminal_age_days * DAY_SECONDS,
        max_runs=args.max_runs,
        max_total_bytes=args.max_total_bytes,
        operation_expiration_seconds=args.operation_expiration_days * DAY_SECONDS,
        orphan_grace_seconds=args.orphan_grace_days * DAY_SECONDS,
        include_orphans=args.include_orphans,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = ServiceConfig.load(resolve_config_path(args))
        service = RetentionService(config.state_root)
        policy = _policy(args)
        if args.mode == "preview":
            if args.fingerprint or args.confirm:
                raise EVError("preview 不接受 --fingerprint 或 --confirm")
            result = service.preview(policy)
        else:
            result = service.apply(policy, str(args.fingerprint or ""), confirmed=args.confirm)
        print_json(result)
        return 0 if result.get("ok") is True else 2
    except (EVError, VerifierError) as exc:
        code = exc.code if isinstance(exc, VerifierError) else "prune_failed"
        return fail(str(exc), code)


if __name__ == "__main__":
    raise SystemExit(main())
