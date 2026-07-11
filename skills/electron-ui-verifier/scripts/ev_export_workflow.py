#!/usr/bin/env python3
"""将 approved canonical workflow asset 导出为 portable typed workflow。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ev_asset_runner import load_workflow_asset
from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json, resolve_config_path, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出 approved workflow asset；report candidate 必须先经 pending 批准。")
    add_common_args(parser)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--output", required=True, help="输出 JSON 的绝对路径")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = Path(args.output)
        if not output.is_absolute():
            raise EVError("--output 必须是绝对路径")
        if output.exists() and not args.overwrite and not args.dry_run:
            raise EVError(f"输出已存在；需要覆盖时使用 --overwrite：{output}")
        config = load_config(resolve_config_path(args))
        workflow, _, usage = load_workflow_asset(config, args.workflow_id)
        if not isinstance(workflow.get("steps"), list) or not workflow["steps"]:
            raise EVError("workflow asset 不可执行")
        if args.dry_run:
            result = {"ok": True, "dryRun": True, "output": str(output), "workflow": workflow, "usage": usage}
        else:
            write_json(output, workflow)
            written = read_json(output)
            if written != workflow:
                raise EVError("导出后回读内容不一致")
            result = {"ok": True, "dryRun": False, "output": str(output), "bytes": output.stat().st_size, "usage": usage}
        print_json(result)
        return 0
    except (EVError, OSError) as exc:
        return fail(str(exc), "export_workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
