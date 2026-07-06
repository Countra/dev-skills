#!/usr/bin/env python3
"""提升或调整 Electron verifier 知识项状态。"""

from __future__ import annotations

import argparse

from ev_common import EVError, add_common_args, fail, load_config, print_json, resolve_config_path
from ev_knowledge_store import VALID_STATUSES, knowledge_paths_from_config, open_store_from_paths


PROMOTE_REQUIRES_EVIDENCE = {"verified", "stable"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="提升或调整本地知识库中的知识状态。")
    add_common_args(parser)
    parser.add_argument("--kind", required=True, choices=("app", "screen", "element", "action", "workflow"))
    parser.add_argument("--id", required=True, help="知识项 ID")
    parser.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    parser.add_argument("--evidence", help="用于支撑提升的 report、artifact、commit 或人工记录")
    parser.add_argument("--user-confirmed", action="store_true", help="用户已确认该知识可提升")
    return parser


def validate_promotion(status: str, evidence: str | None, user_confirmed: bool) -> None:
    if status in PROMOTE_REQUIRES_EVIDENCE and not evidence and not user_confirmed:
        raise EVError(f"--status {status} requires --evidence or --user-confirmed")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_promotion(args.status, args.evidence, args.user_confirmed)
        config = load_config(resolve_config_path(args))
        with open_store_from_paths(knowledge_paths_from_config(config)) as store:
            before = store.get_item(args.kind, args.id)
            after = store.update_status(args.kind, args.id, args.status)
            evidence = None
            if args.evidence:
                evidence = store.add_evidence(
                    {
                        "sourceReport": args.evidence,
                        "artifactRefs": [],
                        "notes": f"status promoted to {args.status} for {args.kind}.{args.id}",
                    }
                )
        print_json(
            {
                "ok": True,
                "result": {
                    "kind": args.kind,
                    "id": args.id,
                    "from": before.get("status"),
                    "to": after.get("status"),
                    "item": after,
                    "evidence": evidence,
                    "userConfirmed": bool(args.user_confirmed),
                },
            }
        )
        return 0
    except EVError as exc:
        return fail(str(exc), "promote_failed")


if __name__ == "__main__":
    raise SystemExit(main())
