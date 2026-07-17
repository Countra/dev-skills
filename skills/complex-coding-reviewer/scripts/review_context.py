#!/usr/bin/env python3
"""构建或校验 review brief 与 context target。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.cli import require_review_root, run_cli
from complex_coding_reviewer.context import (
    build_context_target,
    load_context_brief,
    validate_context_target_shape,
    validate_review_brief,
    verify_context_freshness,
)
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.io import load_json_object, write_new_json


def _output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)


def _entries(values: list[str]) -> list[tuple[str, str]]:
    result = []
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ReviewError("REVIEW_CONTEXT_ENTRY_INVALID", "--entry 必须使用 PATH=ROLE。", path=value)
        path, role = value.split("=", 1)
        if not path or not role or path in seen:
            raise ReviewError("REVIEW_CONTEXT_ENTRY_INVALID", "context entry 必须完整且路径唯一。", path=value)
        seen.add(path)
        result.append((path, role))
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="构建或校验 review context")
    subparsers = root.add_subparsers(dest="mode", required=True)

    brief = subparsers.add_parser("brief", help="校验并原子写入 review brief")
    brief.add_argument("--input", type=Path, required=True)
    _output(brief)

    target = subparsers.add_parser("target", help="构建 context target")
    target.add_argument("--root", type=Path, required=True)
    target.add_argument("--root-kind", choices=["workspace", "task-dir"], required=True)
    target.add_argument("--label", required=True)
    target.add_argument("--entry", action="append", required=True)
    _output(target)

    check = subparsers.add_parser("check", help="校验 context shape、freshness 与 brief")
    check.add_argument("--context", type=Path, required=True)
    check.add_argument("--workspace", type=Path)
    check.add_argument("--task-dir", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()

    def handler() -> dict[str, object]:
        if args.mode == "brief":
            require_review_root(args.output, args.review_root)
            brief = validate_review_brief(
                load_json_object(args.input, code="REVIEW_CONTEXT_BRIEF_INVALID")
            )
            output = write_new_json(args.output, brief, review_root=args.review_root)
            return {"brief": brief, "output": str(output), "agent_calls": 0, "network_calls": 0}
        if args.mode == "target":
            require_review_root(args.output, args.review_root)
            context = build_context_target(
                args.root,
                root_kind=args.root_kind,
                label=args.label,
                entries=_entries(args.entry),
            )
            output = write_new_json(args.output, context, review_root=args.review_root)
            return {"context": context, "output": str(output), "agent_calls": 0, "network_calls": 0}
        context = validate_context_target_shape(
            load_json_object(args.context, code="REVIEW_CONTEXT_INVALID")
        )
        verify_context_freshness(context, workspace=args.workspace, task_dir=args.task_dir)
        brief = load_context_brief(context, workspace=args.workspace, task_dir=args.task_dir)
        return {
            "context_digest": context["digest"],
            "brief": brief,
            "agent_calls": 0,
            "network_calls": 0,
        }

    return run_cli("review.context", handler)


if __name__ == "__main__":
    raise SystemExit(main())

