#!/usr/bin/env python3
"""在已有 run 中执行 typed workflow。"""

from __future__ import annotations

import argparse

from ev_asset_runner import load_workflow_asset
from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json_arg, request_json, resolve_config_path, result_exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 verifier workflow；默认在结束后 finalize。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workflow", help="workflow JSON 文件绝对路径或 JSON 字符串")
    group.add_argument("--workflow-id", help="已批准的 workflow asset ID")
    parser.add_argument("--no-finalize", action="store_true", help="执行后保持 run open")
    parser.add_argument("--bindings", help="参数绑定 JSON 文件绝对路径或 JSON 字符串；值不会写入 journal")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        if args.workflow_id:
            workflow, _, _ = load_workflow_asset(config, args.workflow_id)
        else:
            workflow = read_json_arg(args.workflow, "--workflow")
        if not isinstance(workflow, dict):
            raise EVError("--workflow 必须解析为 JSON object")
        payload: dict[str, object] = {
            "runId": args.run_id,
            "workflow": workflow,
            "autoFinalize": not args.no_finalize,
        }
        if args.bindings:
            payload["bindings"] = read_json_arg(args.bindings, "--bindings")
        result = request_json(
            config,
            "POST",
            "/workflows/run",
            payload,
            timeout=600.0,
        )
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
