#!/usr/bin/env python3
"""从 canonical asset 提取可执行 payload，不从 report 绕过批准门禁。"""

from __future__ import annotations

import argparse
import urllib.parse
from typing import Any

from ev_common import EVError, add_common_args, fail, load_config, print_json, request_json, resolve_config_path, result_exit_code


def executable_from_asset(asset: Any, expected_kind: str | None = None) -> dict[str, Any]:
    if not isinstance(asset, dict) or asset.get("status") != "approved":
        raise EVError("asset 必须是 approved canonical object")
    kind = str(asset.get("kind") or "")
    if kind not in {"action", "workflow"} or expected_kind and kind != expected_kind:
        raise EVError(f"asset kind 不匹配：expected={expected_kind}, actual={kind}")
    payload = asset.get("payload")
    executable = payload.get(kind) if isinstance(payload, dict) else None
    if not isinstance(executable, dict) or not executable:
        raise EVError(f"canonical {kind} asset 缺少 payload.{kind}")
    return {
        "assetId": asset.get("assetId"),
        "kind": kind,
        "appId": asset.get("appId"),
        "goal": asset.get("goal"),
        "executable": executable,
        "parameterSchema": payload.get("parameterSchema") if isinstance(payload, dict) else {},
        "compatibility": payload.get("compatibility") if isinstance(payload, dict) else {},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读取 approved canonical asset 的可执行 payload。")
    add_common_args(parser)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--kind", choices=("action", "workflow"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        path = "/knowledge/assets/get?" + urllib.parse.urlencode({"assetId": args.asset_id})
        result = request_json(config, "GET", path)
        if result.get("ok") is not False:
            result = {"ok": True, "result": executable_from_asset(result.get("asset"), args.kind)}
        print_json(result)
        return result_exit_code(result)
    except EVError as exc:
        return fail(str(exc), "asset_extract_failed")


if __name__ == "__main__":
    raise SystemExit(main())
