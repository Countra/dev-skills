#!/usr/bin/env python3
"""查询和维护 Electron verifier 本地知识库。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, resolve_config_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


LIST_KINDS = ("apps", "screens", "elements", "evidences")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 Electron verifier 本地知识库。")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("meta", help="输出知识库元数据和计数")

    list_parser = subparsers.add_parser("list", help="列出知识项")
    list_parser.add_argument("--kind", required=True, choices=LIST_KINDS)
    list_parser.add_argument("--app-id", help="按 appId 过滤")
    list_parser.add_argument("--limit", type=int, default=50)

    for command, kind in (
        ("list-apps", "apps"),
        ("screens", "screens"),
        ("elements", "elements"),
        ("evidences", "evidences"),
    ):
        alias_parser = subparsers.add_parser(command, help=f"列出 {kind}")
        alias_parser.set_defaults(alias_kind=kind)
        alias_parser.add_argument("--app-id", help="按 appId 过滤")
        alias_parser.add_argument("--limit", type=int, default=50)

    get_parser = subparsers.add_parser("get", help="读取单个知识项")
    get_parser.add_argument("--kind", required=True, choices=("app", "screen", "element", "evidence"))
    get_parser.add_argument("--id", required=True, help="知识项 ID")

    search_parser = subparsers.add_parser("search", help="全文搜索知识库")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--app-id", help="按 appId 过滤")
    search_parser.add_argument("--limit", type=int, default=20)

    cleanup_parser = subparsers.add_parser("cleanup", help="清理过期或废弃基础知识；资产清理使用 ev_assets.py cleanup")
    cleanup_parser.add_argument("--keep-inactive", type=int, default=200)
    cleanup_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(resolve_config_path(args))
        with open_store_from_paths(knowledge_paths_from_config(config)) as store:
            if args.command == "meta":
                result = store.meta()
            elif args.command == "list":
                result = {"items": store.list_items(args.kind, app_id=args.app_id, limit=args.limit)}
            elif getattr(args, "alias_kind", None):
                result = {"items": store.list_items(args.alias_kind, app_id=args.app_id, limit=args.limit)}
            elif args.command == "get":
                result = {"item": store.get_item(args.kind, args.id)}
            elif args.command == "search":
                result = {"items": store.search(args.query, app_id=args.app_id, limit=args.limit)}
            elif args.command == "cleanup":
                result = store.cleanup(keep_inactive=args.keep_inactive, dry_run=args.dry_run, include_assets=False)
            else:
                raise EVError(f"unsupported command: {args.command}")
        print_json({"ok": True, "command": args.command, "result": result})
        return 0
    except EVError as exc:
        return fail(str(exc), "knowledge_failed")


if __name__ == "__main__":
    raise SystemExit(main())
