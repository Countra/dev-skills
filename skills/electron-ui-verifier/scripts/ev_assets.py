#!/usr/bin/env python3
"""查询和维护 Electron verifier action/workflow 资产库。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, resolve_config_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询和维护 Electron verifier action/workflow 资产。")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command, kind in (
        ("list-actions", "action_assets"),
        ("list-workflows", "workflow_assets"),
        ("list-exports", "workflow_exports"),
    ):
        list_parser = subparsers.add_parser(command, help=f"列出 {kind}")
        list_parser.set_defaults(kind=kind)
        list_parser.add_argument("--app-id", help="按 appId 过滤")
        list_parser.add_argument("--limit", type=int, default=50)

    get_action = subparsers.add_parser("get-action", help="读取单个 action asset")
    get_action.add_argument("--id", required=True)

    get_workflow = subparsers.add_parser("get-workflow", help="读取单个 workflow asset")
    get_workflow.add_argument("--id", required=True)

    search = subparsers.add_parser("search", help="全文搜索 action/workflow 资产")
    search.add_argument("--query", required=True)
    search.add_argument("--app-id", help="按 appId 过滤")
    search.add_argument("--limit", type=int, default=20)

    cleanup = subparsers.add_parser("cleanup", help="清理非稳定资产")
    cleanup.add_argument("--keep-inactive", type=int, default=200)
    cleanup.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("reset", help="显式重建知识库；旧 knowledge DB 不迁移")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        reset = args.command == "reset"
        with open_store_from_paths(knowledge_paths_from_config(config), reset=reset) as store:
            if args.command in {"list-actions", "list-workflows", "list-exports"}:
                result = {"items": store.list_items(args.kind, app_id=getattr(args, "app_id", None), limit=args.limit)}
            elif args.command == "get-action":
                result = {"item": store.get_action_asset(args.id)}
            elif args.command == "get-workflow":
                result = {"item": store.get_workflow_asset(args.id)}
            elif args.command == "search":
                items = [item for item in store.search(args.query, app_id=args.app_id, limit=args.limit) if item.get("kind") in {"action", "workflow"}]
                result = {"items": items}
            elif args.command == "cleanup":
                result = store.cleanup(keep_inactive=args.keep_inactive, dry_run=args.dry_run, include_assets=True)
            elif args.command == "reset":
                result = store.meta()
            else:
                raise EVError(f"unsupported command: {args.command}")
        print_json({"ok": True, "command": args.command, "result": result})
        return 0
    except EVError as exc:
        return fail(str(exc), "assets_failed")


if __name__ == "__main__":
    raise SystemExit(main())
