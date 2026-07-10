#!/usr/bin/env python3
"""有界裁剪 inactive run 历史。"""

from __future__ import annotations

import argparse

from process_manager.cli import add_common_args, make_client, output_remote, run_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="裁剪 inactive process 历史")
    add_common_args(parser)
    parser.add_argument("--apply", action="store_true", help="实际裁剪；默认 dry-run")
    parser.add_argument("--max-inactive", type=int)
    parser.add_argument("--keep-runs", action="store_true")
    args = parser.parse_args(argv)

    def execute() -> int:
        status, value = make_client(args.config, timeout=20).request(
            "POST",
            "/processes/prune",
            {
                "dryRun": not args.apply,
                "maxInactive": args.max_inactive,
                "keepRuns": args.keep_runs,
            },
        )
        return output_remote(status, value, pretty=args.pretty)

    return run_cli("processes.prune", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
