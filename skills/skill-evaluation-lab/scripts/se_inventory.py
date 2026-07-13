#!/usr/bin/env python3
"""扫描 skill、测试、eval 和 CI coverage。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.inventory import scan_repository


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描 skill、测试、eval 和 CI coverage")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="仓库根目录")
    parser.add_argument("--require-valid-skill", action="append", default=[], help="要求指定 skill 通过规范校验；可重复")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        result = scan_repository(args.root)
        by_name = {item["name"]: item for item in result["skills"]}
        for name in args.require_valid_skill:
            if name not in by_name:
                raise SuiteError(f"未发现要求的 skill：{name}", path="$.skills")
            if not by_name[name]["valid"]:
                raise SuiteError(f"skill 校验失败：{name}", path="$.skills", guidance=str(by_name[name]["issues"]))
        return result

    return run_cli("inventory.scan", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
