#!/usr/bin/env python3
"""向已有 verifier run 追加一个 typed action。"""

from __future__ import annotations

import argparse
import uuid

from ev_common import EVError, add_common_args, fail, load_config, operation_exit_code, print_json, read_json_arg, request_json, resolve_config_path, wait_for_operation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="追加 verifier typed action；不会自动生成 report/pending。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--action", help="typed action JSON 文件绝对路径或 JSON 字符串")
    action_group.add_argument("--action-id", help="已批准的 action asset ID")
    parser.add_argument("--bindings", help="参数绑定 JSON 文件绝对路径或 JSON 字符串；值不会写入 journal")
    parser.add_argument("--risk-receipt", help="ev_risk.py approve 签发的一次性 receiptId")
    parser.add_argument("--request-id", help="用于幂等重试的非零 UUID；省略时生成新 UUID")
    parser.add_argument("--deadline-ms", type=int, default=120_000, help="服务端 operation deadline")
    parser.add_argument("--wait-seconds", type=float, default=0, help="大于零时提交后轮询到终态")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        payload: dict[str, object] = {
            "runId": args.run_id,
            "requestId": args.request_id or str(uuid.uuid4()),
            "deadlineMs": args.deadline_ms,
        }
        if args.action_id:
            payload["assetId"] = args.action_id
        else:
            action = read_json_arg(args.action, "--action")
            if not isinstance(action, dict):
                raise EVError("--action 必须解析为 JSON object")
            payload["action"] = action
        if args.bindings:
            payload["bindings"] = read_json_arg(args.bindings, "--bindings")
        if args.risk_receipt:
            payload["riskReceipt"] = args.risk_receipt
        result = request_json(
            config,
            "POST",
            "/actions/run",
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
        return fail(str(exc), "action_failed")


if __name__ == "__main__":
    raise SystemExit(main())
