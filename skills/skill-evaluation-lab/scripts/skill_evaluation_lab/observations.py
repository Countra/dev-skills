"""校验并规范化用户在独立会话中声明的观察证据。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import SCHEMA_VERSION, validate_imported_observation, validate_observation_bundle, validate_packet
from .errors import ObservationError
from .paths import relative_path, resolve_input, resolve_workspace, sha256_file, source_identity


def _key(case_id: str, variant: str) -> str:
    return f"{case_id}::{variant}"


def _verify_sources(workspace: Path, packet: dict[str, Any]) -> dict[str, Path]:
    source_paths: dict[str, Path] = {}
    for variant in ("candidate", "baseline"):
        binding = packet["sources"][variant]
        if binding is None:
            continue
        source = resolve_input(
            workspace,
            Path(binding["path"]),
            label=f"packet {variant} source",
            expect="directory",
        )
        current = source_identity(workspace, source)
        if current["tree_sha256"] != binding["tree_sha256"]:
            raise ObservationError(
                "packet source 已变化，观察证据不能导入当前 source",
                code="OBSERVATION_SOURCE_DRIFT",
                path=binding["path"],
                guidance="基于当前 source 重新生成 packet，并由用户重新完成对应观察。",
            )
        source_paths[variant] = source
    return source_paths


def _normalize_artifact(
    workspace: Path,
    raw: dict[str, Any],
    source_paths: dict[str, Path],
) -> dict[str, Any]:
    path = resolve_input(
        workspace,
        Path(raw["path"]),
        label="observation artifact",
        expect="file",
    )
    if any(path.is_relative_to(source) for source in source_paths.values()):
        raise ObservationError(
            "observation artifact 不能位于 candidate 或 baseline source 内",
            code="OBSERVATION_ARTIFACT_IN_SOURCE",
            path=raw["path"],
        )
    size = path.stat().st_size
    if size > 1_048_576:
        raise ObservationError(
            "observation artifact 超过 1 MiB 上限",
            code="OBSERVATION_ARTIFACT_TOO_LARGE",
            path=raw["path"],
        )
    digest = sha256_file(path)
    if raw.get("sha256") is not None and raw["sha256"] != digest:
        raise ObservationError(
            "observation artifact hash 不匹配",
            code="OBSERVATION_ARTIFACT_HASH",
            path=raw["path"],
        )
    return {"path": relative_path(workspace, path), "size": size, "sha256": digest}


def import_observations(
    workspace: Path,
    packet: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    validate_packet(packet)
    validate_observation_bundle(bundle)
    if bundle["packet_fingerprint"] != packet["packet_fingerprint"]:
        raise ObservationError(
            "observation bundle 与 packet fingerprint 不匹配",
            code="OBSERVATION_PACKET_MISMATCH",
            path="$.packet_fingerprint",
        )
    source_paths = _verify_sources(workspace, packet)
    packet_cases = {
        (case["case_id"], case["variant"]): case
        for case in packet["cases"]
    }
    normalized_sessions: list[dict[str, Any]] = []
    for index, session in enumerate(bundle["sessions"]):
        key = (session["case_id"], session["variant"])
        if key not in packet_cases:
            raise ObservationError(
                "observation 引用了 packet 中不存在的 case/variant",
                code="OBSERVATION_CASE_UNKNOWN",
                path=f"$.sessions[{index}]",
            )
        normalized_sessions.append(
            {
                "case_id": session["case_id"],
                "variant": session["variant"],
                "case_fingerprint": packet_cases[key]["case_fingerprint"],
                "session_ref": session["session_ref"],
                "status": session["status"],
                "notes": session["notes"],
                "artifacts": [
                    _normalize_artifact(workspace, artifact, source_paths)
                    for artifact in session["artifacts"]
                ],
            }
        )
    expected = sorted(_key(*key) for key in packet_cases)
    observed = sorted(_key(session["case_id"], session["variant"]) for session in normalized_sessions)
    missing = sorted(set(expected) - set(observed))
    imported = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "packet_fingerprint": packet["packet_fingerprint"],
        "candidate_tree_sha256": packet["sources"]["candidate"]["tree_sha256"],
        "baseline_tree_sha256": (
            packet["sources"]["baseline"]["tree_sha256"]
            if packet["sources"]["baseline"] is not None
            else None
        ),
        "coverage": {
            "expected": expected,
            "observed": observed,
            "missing": missing,
            "status": "partial" if missing else "complete",
        },
        "sessions": normalized_sessions,
        "provenance": {
            "declared_by": "user",
            "import_mode": "validation_only",
            "agent_calls": 0,
            "network_calls": 0,
        },
    }
    return validate_imported_observation(imported)
