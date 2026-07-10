#!/usr/bin/env python3
"""校验封闭 manager/service schema。"""

from __future__ import annotations

import argparse
from pathlib import Path

from process_manager.cli import add_common_args, run_cli
from process_manager.config import load_manager_config, load_service_config
from process_manager.protocol import print_json, success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 process-manager 配置")
    add_common_args(parser)
    parser.add_argument("--service", help="service JSON 路径")
    args = parser.parse_args(argv)

    def execute() -> int:
        config = load_manager_config(Path(args.config).resolve())
        data = {"manager": config.public_dict()}
        if args.service:
            service = load_service_config(Path(args.service).resolve(), config)
            data["service"] = service.public_summary()
        print_json(success("validate", data), pretty=args.pretty)
        return 0

    return run_cli("validate", execute, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
