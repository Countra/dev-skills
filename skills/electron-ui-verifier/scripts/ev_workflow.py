#!/usr/bin/env python3
"""在已有 run 中执行 typed workflow。"""

from __future__ import annotations

import argparse
import uuid

from ev_asset_runner import load_workflow_asset
from ev_common import EVError, add_common_args, fail, load_config, operation_exit_code, print_json, read_json_arg, request_json, resolve_config_path, wait_for_operation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行 verifier workflow；默认在结束后 finalize。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--workflow", help="workflow JSON 文件绝对路径或 JSON 字符串")
    group.add_argument("--workflow-id", help="已批准的 workflow asset ID")
    parser.add_argument("--no-finalize", action="store_true", help="执行后保持 run open")
    parser.add_argument("--bindings", help="参数绑定 JSON 文件绝对路径或 JSON 字符串；值不会写入 journal")
    parser.add_argument("--risk-receipts", help="按 step id 或索引映射 receiptId 的 JSON 文件或字符串")
    parser.add_argument("--request-id", help="用于幂等重试的非零 UUID；省略时生成新 UUID")
    parser.add_argument("--deadline-ms", type=int, default=300_000, help="服务端 operation deadline")
    parser.add_argument("--wait-seconds", type=float, default=0, help="大于零时提交后轮询到终态")
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
            "requestId": args.request_id or str(uuid.uuid4()),
            "deadlineMs": args.deadline_ms,
        }
        if args.bindings:
            payload["bindings"] = read_json_arg(args.bindings, "--bindings")
        if args.risk_receipts:
            payload["riskReceipts"] = read_json_arg(args.risk_receipts, "--risk-receipts")
        result = request_json(
            config,
            "POST",
            "/workflows/run",
            payload,
            timeout=30.0,
        )
        if args.wait_seconds > 0:
            operation = result.get("operation")
            if not isinstance(operation, dict) or not operation.get("operationId"):
                raise EVError("operation submit response is missing operationId")
            result = wait_for_operation(config, str(operation["operationId"]), args.wait_seconds)
        print_json(result)
        return operation_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
