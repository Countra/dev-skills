#!/usr/bin/env python3
"""校验或生成 Reviewer 的用户独立会话观察工作包。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LAB_SCRIPT_ROOT = REPO_ROOT / "skills" / "skill-evaluation-lab" / "scripts"
DEFAULT_SUITE = Path(__file__).with_name("observation-suite.json")
IMPORT_SCHEMA = REPO_ROOT / "skills" / "skill-evaluation-lab" / "schemas" / "imported-observation.schema.json"
if str(LAB_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_SCRIPT_ROOT))

from skill_evaluation_lab.contracts import load_suite, validate_packet
from skill_evaluation_lab.errors import LabError
from skill_evaluation_lab.packets import build_packet, suite_receipt, write_packet
from skill_evaluation_lab.paths import resolve_input, resolve_output, resolve_workspace


def render(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def dispatch_checklist() -> str:
    return """# Reviewer Dispatch Observation Checklist

本工作包只能由用户在独立 Codex 会话中操作；脚本不会启动 Agent、模型或目标程序。

对每个正式 `plan-review` 或 `code-review` case：

1. 记录 coordinator 是否显式创建且只创建一个 Reviewer 子 Agent。
2. 确认 `fork_context=false`，子 Agent 未继续派发下一层 Agent。
3. 确认 `wait_agent` 单次窗口不超过 60 秒、每个未终态窗口均回报进度，且总 timeout 未因轮询重置。
4. 确认 prompt 未包含父代理 findings、预期 verdict 或实现者 framing。
5. 记录 immutable dispatch、semantic result 与 canonical receipt 路径及摘要。
6. 运行 `review_validate.py`，记录 expected dispatch policy 与校验结果。
7. 确认 `close_agent` 已执行且 final dispatch 的 close status 为 `closed`。

对 trigger near-miss case，记录没有创建 Reviewer 子 Agent、没有生成 receipt。

宿主工具调用无法由静态文件独立证明。观察者必须同时保留宿主活动记录和 dispatch/receipt，并在导入结果中披露缺失证据。
"""


def validation_report(
    workspace: Path,
    suite: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    validated = validate_packet(packet)
    receipt = suite_receipt(workspace, suite)
    inputs: dict[str, dict[str, Any]] = {}
    for case in validated["cases"]:
        for item in case["inputs"]:
            inputs[item["path"]] = item
    kinds: dict[str, int] = {}
    for case in validated["cases"]:
        kinds[case["kind"]] = kinds.get(case["kind"], 0) + 1
    return {
        "suite": "complex-coding-reviewer-observation-packet",
        "passed": True,
        "packet": {
            "packet_id": validated["packet_id"],
            "packet_fingerprint": validated["packet_fingerprint"],
            "execution_mode": validated["execution_mode"],
            "candidate": validated["sources"]["candidate"],
            "baseline": validated["sources"]["baseline"],
            "case_variant_count": len(validated["cases"]),
            "case_kinds": kinds,
            "fixed_inputs": [inputs[path] for path in sorted(inputs)],
        },
        "suite_receipt": receipt,
        "result_import": {
            "schema_path": IMPORT_SCHEMA.relative_to(workspace).as_posix(),
            "declared_by": "user",
            "import_mode": "validation_only",
            "source_drift_policy": "regenerate_packet",
            "missing_sessions_policy": "preserve_partial_coverage",
        },
        "evidence_layers": {
            "deterministic_contract": "separate_evidence",
            "same_context_semantic": "separate_evidence",
            "fresh_context_semantic": "not_observed",
        },
        "delegated_review_contract": {
            "formal_review_agent_count": 1,
            "fork_context": False,
            "recursive_delegation_allowed": False,
            "parent_judgment_included": False,
            "receipt_validation_required": True,
            "agent_close_status": "closed",
            "max_wait_slice_seconds": 60,
            "wait_budget_reset_allowed": False,
            "progress_reporting_required": True,
            "host_activity_evidence_required": True,
        },
        "claim_boundaries": {
            "agent_calls": 0,
            "network_calls": 0,
            "target_executions": 0,
            "fresh_context_quality_observed": False,
            "next_action": "user_operated_independent_sessions",
        },
    }


def write_report(
    workspace: Path,
    output: Path | None,
    report: dict[str, Any],
    *,
    source_roots: tuple[Path, ...],
) -> None:
    rendered = render(report)
    if output is not None:
        raw = output if output.is_absolute() else workspace / output
        destination = Path(os.path.abspath(raw)).resolve(strict=False)
        if destination != workspace and not destination.is_relative_to(workspace):
            raise ValueError("output 必须位于 workspace 内")
        for source_root in source_roots:
            resolved_source = source_root.resolve(strict=True)
            if destination == resolved_source or destination.is_relative_to(resolved_source):
                raise ValueError("output 不得写入 observation packet 的 candidate/baseline source")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验或生成 Reviewer 的不可执行 observation packet")
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true", help="只校验 packet，不创建工作包目录")
    mode.add_argument("--prepare-dir", type=Path, help="新建供用户操作的 packet 目录")
    parser.add_argument("--output", type=Path, help="可选校验结果 JSON")
    args = parser.parse_args()

    try:
        workspace = resolve_workspace(args.workspace)
        suite_path = resolve_input(workspace, args.suite, label="observation suite", expect="file")
        suite = load_suite(suite_path)
        packet, source_roots = build_packet(workspace, suite)
        report = validation_report(workspace, suite, packet)
        if args.prepare_dir is not None:
            packet_dir = resolve_output(
                workspace,
                args.prepare_dir,
                label="observation packet directory",
                source_roots=source_roots,
            )
            prepared = write_packet(packet_dir, packet)
            checklist = packet_dir / "REVIEWER-DISPATCH-CHECKLIST.md"
            checklist.write_text(dispatch_checklist(), encoding="utf-8")
            prepared["dispatch_checklist"] = checklist.name
            report["prepared_packet"] = prepared
        write_report(workspace, args.output, report, source_roots=source_roots)
    except (OSError, UnicodeError, json.JSONDecodeError, LabError, ValueError) as exc:
        error = {
            "suite": "complex-coding-reviewer-observation-packet",
            "passed": False,
            "error": {
                "code": getattr(exc, "code", "OBSERVATION_PACKET_INVALID"),
                "message": str(exc),
            },
            "claim_boundaries": {
                "agent_calls": 0,
                "network_calls": 0,
                "target_executions": 0,
                "fresh_context_quality_observed": False,
            },
        }
        print(render(error), end="")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
