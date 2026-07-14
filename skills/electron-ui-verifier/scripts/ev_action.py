#!/usr/bin/env python3
"""向已有 verifier run 追加一个 typed action。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json_arg, request_json, resolve_config_path, result_exit_code
from ev_asset_runner import load_action_asset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="追加 verifier typed action；不会自动生成 report/pending。")
    add_common_args(parser)
    parser.add_argument("--run-id", required=True)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--action", help="typed action JSON 文件绝对路径或 JSON 字符串")
    action_group.add_argument("--action-id", help="已批准的 action asset ID")
    parser.add_argument("--bindings", help="参数绑定 JSON 文件绝对路径或 JSON 字符串；值不会写入 journal")
    parser.add_argument("--risk-receipt", help="ev_risk.py approve 签发的一次性 receiptId")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        usage = None
        if args.action_id:
            action, _, usage = load_action_asset(config, args.action_id)
        else:
            action = read_json_arg(args.action, "--action")
        if not isinstance(action, dict):
            raise EVError("--action 必须解析为 JSON object")
        payload: dict[str, object] = {"runId": args.run_id, "action": action}
        if usage and usage.get("parameterSchema"):
            payload["parameterSchema"] = usage["parameterSchema"]
        if args.bindings:
            payload["bindings"] = read_json_arg(args.bindings, "--bindings")
        if args.risk_receipt:
            payload["riskReceipt"] = args.risk_receipt
        result = request_json(
            config,
            "POST",
            "/actions/run",
            payload,
            timeout=120.0,
        )
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "action_failed")


if __name__ == "__main__":
    raise SystemExit(main())
