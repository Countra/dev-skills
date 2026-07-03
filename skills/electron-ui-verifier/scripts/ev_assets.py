#!/usr/bin/env python3
"""查询和维护 Electron verifier action/workflow 资产库。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, resolve_config_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


def matches_filters(item: dict[str, object], args: argparse.Namespace) -> bool:
    screen_id = getattr(args, "screen_id", None)
    kind = getattr(args, "kind_filter", None)
    status = getattr(args, "status", None)
    goal = getattr(args, "goal", None)
    if screen_id and item.get("screen_id") != screen_id:
        return False
    if kind and item.get("kind") != kind:
        return False
    if status and item.get("status") != status:
        return False
    if goal and goal not in str(item.get("goal") or ""):
        return False
    return True


def filter_items(items: list[dict[str, object]], args: argparse.Namespace) -> list[dict[str, object]]:
    return [item for item in items if matches_filters(item, args)]


def result_summary(items: list[dict[str, object]]) -> dict[str, object]:
    statuses: dict[str, int] = {}
    kinds: dict[str, int] = {}
    reusable_count = 0
    for item in items:
        status = str(item.get("status") or "unknown")
        kind = str(item.get("kind") or item.get("goal") or "workflow")
        statuses[status] = statuses.get(status, 0) + 1
        kinds[kind] = kinds.get(kind, 0) + 1
        if item.get("workflow_id") or item.get("action_id"):
            reusable_count += 1
    return {
        "count": len(items),
        "reusableCount": reusable_count,
        "statuses": statuses,
        "kinds": kinds,
        "recommendedNextAction": "命中可执行 workflow/action asset 时优先通过 --workflow-id 或 --action-id 现场复验；不可复用时再探索",
        "directRunHint": "workflow asset 用 ev_workflow.py --workflow-id <id>，action asset 用 ev_action.py --action-id <id>；低置信或坐标兜底资产需要谨慎复验。",
    }


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
        list_parser.add_argument("--status", help="按状态过滤")
        list_parser.add_argument("--limit", type=int, default=50)
        if command == "list-actions":
            list_parser.add_argument("--screen-id", help="按 screenId 过滤")
            list_parser.add_argument("--kind", dest="kind_filter", help="按 action kind 过滤")
        if command == "list-workflows":
            list_parser.add_argument("--goal", help="按 goal 子串过滤")

    get_action = subparsers.add_parser("get-action", help="读取单个 action asset")
    get_action.add_argument("--id", required=True)

    get_workflow = subparsers.add_parser("get-workflow", help="读取单个 workflow asset")
    get_workflow.add_argument("--id", required=True)

    search = subparsers.add_parser("search", help="全文搜索 action/workflow 资产")
    search.add_argument("--query", required=True)
    search.add_argument("--app-id", help="按 appId 过滤")
    search.add_argument("--status", help="按状态过滤")
    search.add_argument("--screen-id", help="按 screenId 过滤 action")
    search.add_argument("--kind", dest="kind_filter", help="按 action kind 过滤")
    search.add_argument("--goal", help="按 workflow goal 子串过滤")
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
                items = store.list_items(args.kind, app_id=getattr(args, "app_id", None), limit=max(args.limit * 4, args.limit))
                filtered = filter_items(items, args)[: args.limit]
                result = {"items": filtered, "summary": result_summary(filtered)}
            elif args.command == "get-action":
                result = {"item": store.get_action_asset(args.id)}
            elif args.command == "get-workflow":
                result = {"item": store.get_workflow_asset(args.id)}
            elif args.command == "search":
                hits = [item for item in store.search(args.query, app_id=args.app_id, limit=max(args.limit * 4, args.limit)) if item.get("kind") in {"action", "workflow"}]
                filtered = filter_items(hits, args)[: args.limit]
                result = {"items": filtered, "summary": result_summary(filtered)}
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
