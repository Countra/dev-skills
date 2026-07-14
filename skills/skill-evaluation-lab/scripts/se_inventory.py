#!/usr/bin/env python3
"""扫描 Skill、测试、eval 和 CI coverage。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.errors import ContractError
from skill_evaluation_lab.inventory import scan_repository
from skill_evaluation_lab.output import write_new_json
from skill_evaluation_lab.paths import resolve_output, resolve_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="只读扫描 Skill、测试、eval 和 CI coverage")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="仓库根目录")
    parser.add_argument("--require-valid-skill", action="append", default=[], help="要求指定 Skill metadata 有效；可重复")
    parser.add_argument("--output", type=Path, help="可选的新建 inventory JSON")
    parser.add_argument("--pretty", action="store_true", help="格式化标准输出 JSON")
    args = parser.parse_args()

    def handler() -> object:
        root = resolve_workspace(args.root)
        result = scan_repository(root)
        by_name = {item["name"]: item for item in result["skills"]}
        for name in args.require_valid_skill:
            if name not in by_name:
                raise ContractError(
                    f"未发现要求的 Skill：{name}",
                    code="SKILL_INVENTORY_MISSING",
                    path="$.skills",
                )
            if not by_name[name]["valid"]:
                raise ContractError(
                    f"Skill metadata 校验失败：{name}",
                    code="SKILL_INVENTORY_INVALID",
                    path="$.skills",
                    guidance=str(by_name[name]["issues"]),
                )
        if args.output:
            output = resolve_output(root, args.output, label="inventory output")
            write_new_json(output, result)
        return result

    return run_cli("inventory.scan", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
