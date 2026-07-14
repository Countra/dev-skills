#!/usr/bin/env python3
"""生成不可执行的用户 observation packet。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.packets import build_packet, write_packet
from skill_evaluation_lab.paths import resolve_input, resolve_output, resolve_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="生成人工独立会话 observation packet")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace 根目录")
    parser.add_argument("--suite", type=Path, required=True, help="已校验的 observation suite JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="必须尚不存在的 packet 输出目录")
    parser.add_argument("--pretty", action="store_true", help="格式化标准输出 JSON")
    args = parser.parse_args()

    def handler() -> object:
        workspace = resolve_workspace(args.workspace)
        suite_path = resolve_input(workspace, args.suite, label="suite", expect="file")
        suite = load_suite(suite_path)
        packet, source_roots = build_packet(workspace, suite)
        output_dir = resolve_output(
            workspace,
            args.output_dir,
            label="packet output directory",
            source_roots=source_roots,
        )
        return write_packet(output_dir, packet)

    return run_cli("packet.prepare", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
