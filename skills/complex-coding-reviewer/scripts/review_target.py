#!/usr/bin/env python3
"""生成 canonical plan、Git 或显式文件 review target。"""

from __future__ import annotations

import argparse
from pathlib import Path

from complex_coding_reviewer.cli import parse_roles, require_review_root, run_cli
from complex_coding_reviewer.io import write_new_json
from complex_coding_reviewer.target import (
    build_commit_range_target,
    build_file_manifest_target,
    build_plan_bundle_target,
    build_working_tree_target,
)


def _common_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-root", type=Path)


def _git_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="生成 canonical review target")
    subparsers = root.add_subparsers(dest="kind", required=True)

    plan = subparsers.add_parser("plan", help="生成 managed plan-bundle target")
    plan.add_argument("--task-dir", type=Path, required=True)
    _common_output(plan)

    files = subparsers.add_parser("files", help="生成显式 file-manifest target")
    files.add_argument("--workspace", type=Path, required=True)
    files.add_argument("--file", action="append", required=True)
    files.add_argument("--label", default="standalone")
    files.add_argument("--role", action="append", default=[])
    _common_output(files)

    working = subparsers.add_parser("working-tree", help="生成 baseline 到工作树的 git-diff target")
    working.add_argument("--repository", type=Path, required=True)
    working.add_argument("--baseline", default="HEAD")
    working.add_argument("--stage-id")
    working.add_argument("--attempt", type=int)
    _git_selection(working)
    _common_output(working)

    commit = subparsers.add_parser("commit-range", help="生成两个 commit 间的 target")
    commit.add_argument("--repository", type=Path, required=True)
    commit.add_argument("--baseline", required=True)
    commit.add_argument("--head", required=True)
    _git_selection(commit)
    _common_output(commit)
    return root


def main() -> int:
    args = parser().parse_args()

    def handler() -> dict[str, object]:
        require_review_root(args.output, args.review_root)
        if args.kind == "plan":
            target = build_plan_bundle_target(args.task_dir)
        elif args.kind == "files":
            target = build_file_manifest_target(
                args.workspace,
                args.file,
                label=args.label,
                roles=parse_roles(args.role),
            )
        elif args.kind == "working-tree":
            target = build_working_tree_target(
                args.repository,
                baseline=args.baseline,
                paths=args.path,
                excludes=args.exclude,
                stage_id=args.stage_id,
                attempt=args.attempt,
            )
        else:
            target = build_commit_range_target(
                args.repository,
                baseline=args.baseline,
                head=args.head,
                paths=args.path,
                excludes=args.exclude,
            )
        output = None
        if args.output:
            output = str(write_new_json(args.output, target, review_root=args.review_root))
        return {"target": target, "output": output, "agent_calls": 0, "network_calls": 0}

    return run_cli("review.target", handler)


if __name__ == "__main__":
    raise SystemExit(main())
