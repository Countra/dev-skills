#!/usr/bin/env python3
"""仅在能力边界不明确时查询 gitlab-pat-ops 注册表。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import GitLabSkillError, UnsupportedCapabilityError, run_cli
from gitlab_ops.output import output_result
from gitlab_ops.registry import PROHIBITED, find_prohibited, registry_document, select_capabilities


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在能力边界不明确时查询 gitlab-pat-ops")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    parser.add_argument("--mode", choices=["read", "write"], help="按读写模式过滤")
    parser.add_argument("--resource", help="按精确资源名过滤")
    parser.add_argument("--capability", help="按精确 capability_id 过滤")
    parser.add_argument("--prohibited", action="store_true", help="只显示明确禁止能力")
    parser.add_argument("--all", action="store_true", help="显示完整注册表；默认仍建议精确过滤")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.prohibited:
        data: object = {"prohibited": list(PROHIBITED)}
    elif args.all:
        data = registry_document()
    else:
        if not any((args.mode, args.resource, args.capability)):
            raise GitLabSkillError("请使用 --capability、--resource、--mode 精确过滤，或显式传入 --all")
        prohibited = find_prohibited(args.capability) if args.capability else None
        if prohibited:
            raise UnsupportedCapabilityError(
                f"能力 {args.capability} 被 gitlab-pat-ops 明确禁止",
                guidance=prohibited["reason"],
            )
        values = select_capabilities(mode=args.mode, resource=args.resource, capability_id=args.capability)
        data = {
            "query": {
                "mode": args.mode,
                "resource": args.resource,
                "capability_id": args.capability,
            },
            "supported": bool(values) if args.capability else None,
            "capabilities": values,
            "usage": "只在不清楚具体能力边界时查询；已知命令无需先运行本脚本。",
        }
    output_result(data, pretty=args.pretty, operation="capabilities.query")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
