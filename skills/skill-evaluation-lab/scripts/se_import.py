#!/usr/bin/env python3
"""导入并校验用户声明的独立会话观察证据。"""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.contracts import load_observation_bundle, load_packet
from skill_evaluation_lab.observations import import_observations
from skill_evaluation_lab.output import write_new_json
from skill_evaluation_lab.paths import resolve_input, resolve_output, resolve_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="校验并导入用户 observation bundle")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace 根目录")
    parser.add_argument("--packet", type=Path, required=True, help="se_prepare.py 生成的 packet.json")
    parser.add_argument("--observation", type=Path, required=True, help="用户填写的 observation bundle JSON")
    parser.add_argument("--output", type=Path, required=True, help="新建 imported observation JSON")
    parser.add_argument("--pretty", action="store_true", help="格式化标准输出 JSON")
    args = parser.parse_args()

    def handler() -> object:
        workspace = resolve_workspace(args.workspace)
        packet_path = resolve_input(workspace, args.packet, label="packet", expect="file")
        observation_path = resolve_input(
            workspace,
            args.observation,
            label="observation bundle",
            expect="file",
        )
        packet = load_packet(packet_path)
        bundle = load_observation_bundle(observation_path)
        evidence = import_observations(workspace, packet, bundle)
        source_roots = tuple(
            resolve_input(
                workspace,
                Path(binding["path"]),
                label=f"packet {variant} source",
                expect="directory",
            )
            for variant, binding in packet["sources"].items()
            if binding is not None
        )
        output = resolve_output(
            workspace,
            args.output,
            label="imported observation output",
            source_roots=source_roots,
        )
        write_new_json(output, evidence)
        return evidence

    return run_cli("observation.import", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
