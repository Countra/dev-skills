"""生成只供用户独立会话使用、不可执行的观察工作包。"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import SCHEMA_VERSION, validate_packet, validate_suite
from .errors import LabError, PacketError
from .output import write_new_json, write_new_text
from .paths import (
    hash_document,
    relative_path,
    resolve_input,
    resolve_workspace,
    sha256_file,
    source_identity,
)


def _compact_identity(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": identity["path"],
        "tree_sha256": identity["tree_sha256"],
        "file_count": identity["file_count"],
        "total_bytes": identity["total_bytes"],
    }


def validate_suite_resources(workspace: Path, suite: dict[str, Any]) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    validate_suite(suite)
    candidate = resolve_input(
        workspace,
        Path(suite["candidate"]),
        label="suite candidate",
        expect="directory",
    )
    baseline = (
        resolve_input(
            workspace,
            Path(suite["baseline"]),
            label="suite baseline",
            expect="directory",
        )
        if suite["baseline"] is not None
        else None
    )
    inputs: dict[str, dict[str, Any]] = {}
    for case in suite["cases"]:
        for value in case["inputs"]:
            if value in inputs:
                continue
            path = resolve_input(
                workspace,
                Path(value),
                label=f"case input {value}",
                expect="file",
            )
            size = path.stat().st_size
            if size > 1_048_576:
                raise PacketError(
                    "case input 超过 1 MiB 上限",
                    code="PACKET_INPUT_TOO_LARGE",
                    path=value,
                )
            inputs[value] = {
                "path": relative_path(workspace, path),
                "size": size,
                "sha256": sha256_file(path),
            }
    return {"candidate": candidate, "baseline": baseline, "inputs": inputs}


def suite_receipt(workspace: Path, suite: dict[str, Any]) -> dict[str, Any]:
    resources = validate_suite_resources(workspace, suite)
    kinds = {kind: 0 for kind in ("trigger-positive", "trigger-near-miss", "behavior")}
    for case in suite["cases"]:
        kinds[case["kind"]] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "suite_id": suite["suite_id"],
        "valid": True,
        "candidate": relative_path(resolve_workspace(workspace), resources["candidate"]),
        "baseline": (
            relative_path(resolve_workspace(workspace), resources["baseline"])
            if resources["baseline"]
            else None
        ),
        "case_count": len(suite["cases"]),
        "case_kinds": kinds,
        "required_variants": list(suite["observation_policy"]["required_variants"]),
        "input_count": len(resources["inputs"]),
        "execution_mode": "user_operated_independent_session",
        "agent_calls": 0,
        "network_calls": 0,
    }


def build_packet(workspace: Path, suite: dict[str, Any]) -> tuple[dict[str, Any], tuple[Path, ...]]:
    workspace = resolve_workspace(workspace)
    resources = validate_suite_resources(workspace, suite)
    candidate_identity = source_identity(workspace, resources["candidate"])
    baseline_identity = (
        source_identity(workspace, resources["baseline"])
        if resources["baseline"] is not None
        else None
    )
    sources = {
        "candidate": _compact_identity(candidate_identity),
        "baseline": _compact_identity(baseline_identity) if baseline_identity else None,
    }
    packet_cases: list[dict[str, Any]] = []
    for case in suite["cases"]:
        input_evidence = [resources["inputs"][value] for value in case["inputs"]]
        for variant in suite["observation_policy"]["required_variants"]:
            case_document = {
                "case_id": case["id"],
                "kind": case["kind"],
                "variant": variant,
                "prompt": case["prompt"],
                "expected_observation": case["expected_observation"],
                "inputs": input_evidence,
            }
            case_document["case_fingerprint"] = hash_document(case_document)
            packet_cases.append(case_document)
    packet_id = f"{suite['suite_id'][:50]}-{candidate_identity['tree_sha256'][:12]}"
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "packet_id": packet_id,
        "suite_id": suite["suite_id"],
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_mode": "user_operated_independent_session",
        "sources": sources,
        "cases": packet_cases,
    }
    packet["packet_fingerprint"] = hash_document(packet)
    source_roots = (resources["candidate"],)
    if resources["baseline"] is not None:
        source_roots += (resources["baseline"],)
    return validate_packet(packet), source_roots


def _instructions(packet: dict[str, Any]) -> str:
    return (
        "# 人工观察工作包\n\n"
        f"Packet：`{packet['packet_id']}`\n\n"
        "1. 当前评估会话在此停止，不得自动启动任何 Agent、模型或目标脚本。\n"
        "2. 用户为每个 case/variant 新建独立会话，并原样提供 packet 中的 prompt 与 inputs。\n"
        "3. 用户记录 session reference、结果、说明和 workspace 内 artifact 路径。\n"
        "4. 用户填写 `observation-template.json`，再交回原评估会话导入。\n"
        "5. expected observation 只用于回到原会话后核对，不应作为隐藏答案注入独立会话。\n\n"
        "本工作包没有可执行命令、模型配置或凭据。\n"
    )


def write_packet(output_dir: Path, packet: dict[str, Any]) -> dict[str, Any]:
    if output_dir.exists():
        raise PacketError(
            "packet 输出目录已存在",
            code="PACKET_OUTPUT_EXISTS",
            path=str(output_dir),
        )
    template = {
        "schema_version": SCHEMA_VERSION,
        "packet_fingerprint": packet["packet_fingerprint"],
        "declared_by": "user",
        "sessions": [],
    }
    created = False
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
        created = True
        write_new_json(output_dir / "packet.json", packet)
        write_new_json(output_dir / "observation-template.json", template)
        write_new_text(output_dir / "INSTRUCTIONS.md", _instructions(packet))
    except (OSError, LabError) as exc:
        if created:
            try:
                shutil.rmtree(output_dir)
            except OSError as cleanup_error:
                raise PacketError(
                    "packet 写入失败且新建目录无法完整回滚",
                    code="PACKET_ROLLBACK_FAILED",
                    path=str(output_dir),
                    guidance=str(cleanup_error),
                    outcome="partial",
                ) from exc
        if isinstance(exc, LabError):
            raise
        raise PacketError(
            "packet 写入失败，已清理本次新建目录",
            code="PACKET_WRITE_FAILED",
            path=str(output_dir),
        ) from exc
    return {
        "packet_id": packet["packet_id"],
        "packet_fingerprint": packet["packet_fingerprint"],
        "case_variant_count": len(packet["cases"]),
        "execution_mode": packet["execution_mode"],
        "files": ["packet.json", "observation-template.json", "INSTRUCTIONS.md"],
        "next_action": "stop_and_wait_for_user_operated_independent_sessions",
        "agent_calls": 0,
        "network_calls": 0,
    }
