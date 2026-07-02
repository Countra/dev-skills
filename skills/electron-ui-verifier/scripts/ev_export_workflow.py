#!/usr/bin/env python3
"""导出可复用 verifier workflow JSON。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from ev_common import EVError, add_common_args, fail, load_config, print_json, read_json, resolve_config_path, write_json
from ev_asset_extract import extract_assets
from ev_knowledge_extract import safe_report_path
from ev_knowledge_store import knowledge_paths_from_config, open_store_from_paths


SUPPORTED_ACTIONS = {
    "snapshot",
    "screenshot",
    "clickText",
    "clickXY",
    "fillText",
    "pressKey",
    "extractText",
    "extractTable",
    "waitText",
    "waitUrlContains",
    "evaluate",
    "collectConsole",
    "collectExceptions",
    "collectNetwork",
    "domSnapshot",
    "accessibilitySnapshot",
}
CONTROL_KEYS = {"id", "continueOnFailure", "notes"}


def output_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise EVError("--output must be an absolute path")
    return path


def path_hash(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def action_keys(step: dict[str, Any]) -> list[str]:
    return [key for key in step if key not in CONTROL_KEYS]


def validate_step(step: Any, index: int) -> None:
    if not isinstance(step, dict):
        raise EVError(f"workflow step must be an object: index={index}")
    keys = action_keys(step)
    if len(keys) != 1:
        raise EVError(f"workflow step must contain exactly one action: index={index}, actions={keys}")
    action = keys[0]
    if action not in SUPPORTED_ACTIONS:
        raise EVError(f"unsupported workflow action: index={index}, action={action}")


def validate_workflow(workflow: dict[str, Any]) -> None:
    readiness = workflow.get("readiness", [])
    steps = workflow.get("steps")
    if not isinstance(readiness, list):
        raise EVError("workflow.readiness must be a list")
    if not isinstance(steps, list) or not steps:
        raise EVError("workflow.steps must be a non-empty list")
    for index, step in enumerate(readiness):
        validate_step(step, index)
    for index, step in enumerate(steps):
        validate_step(step, index)


def local_path_like(value: str) -> bool:
    return ":\\" in value or ":/" in value or value.startswith("\\\\")


def scan_local_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(scan_local_paths(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(scan_local_paths(item, f"{path}[{index}]"))
    elif isinstance(value, str) and local_path_like(value):
        found.append(path)
    return found


def required_params(asset: dict[str, Any]) -> dict[str, Any]:
    params = asset.get("params")
    if not isinstance(params, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, dict):
            safe[key] = {name: item for name, item in value.items() if name not in {"sample", "value", "default"}}
        else:
            safe[key] = {"required": True}
    return safe


def metadata_for_asset(asset: dict[str, Any], include_local_paths: bool) -> dict[str, Any]:
    metadata = {
        "source": "knowledge.workflow_asset",
        "workflowAssetId": asset.get("workflow_asset_id") or asset.get("workflowAssetId"),
        "appId": asset.get("app_id") or asset.get("appId"),
        "goal": asset.get("goal"),
        "status": asset.get("status"),
        "confidence": asset.get("confidence"),
        "riskFlags": asset.get("risk_flags", []),
        "evidenceRefs": asset.get("evidence_refs", []),
        "requiredParams": required_params(asset),
    }
    if include_local_paths:
        metadata["sourceReport"] = asset.get("source_report")
    return metadata


def metadata_for_report(asset: dict[str, Any], include_local_paths: bool) -> dict[str, Any]:
    metadata = {
        "source": "verifier.report",
        "workflowAssetId": asset.get("workflowAssetId"),
        "appId": asset.get("appId"),
        "goal": asset.get("goal"),
        "status": asset.get("status"),
        "confidence": asset.get("confidence"),
        "riskFlags": asset.get("riskFlags", []),
        "requiredParams": required_params(asset),
    }
    if include_local_paths:
        metadata["sourceReport"] = asset.get("sourceReport")
        metadata["artifactRefs"] = asset.get("artifactRefs", [])
    return metadata


def workflow_from_asset(asset: dict[str, Any], include_metadata: bool, include_local_paths: bool) -> dict[str, Any]:
    workflow = {
        "readiness": asset.get("readiness", []),
        "steps": asset.get("steps", []),
    }
    metadata = metadata_for_asset(asset, include_local_paths)
    if include_metadata or metadata["requiredParams"]:
        workflow["metadata"] = metadata
    return workflow


def workflow_from_report(report: Path, app_id: str | None, goal: str | None, include_metadata: bool, include_local_paths: bool) -> dict[str, Any]:
    assets = extract_assets(report, app_id_override=app_id, notes=goal)
    workflows = assets.get("workflowAssets") if isinstance(assets.get("workflowAssets"), list) else []
    if not workflows:
        raise EVError("report did not produce a workflow asset candidate")
    asset = dict(workflows[0])
    workflow = {
        "readiness": asset.get("readiness", []),
        "steps": asset.get("steps", []),
    }
    metadata = metadata_for_report(asset, include_local_paths)
    if include_metadata or metadata["requiredParams"]:
        workflow["metadata"] = metadata
    return workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从知识库或 report 导出 verifier workflow JSON。")
    add_common_args(parser)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--workflow-id", help="workflow asset ID")
    source.add_argument("--report", help="report.json 绝对路径")
    parser.add_argument("--app-id", help="从 report 导出时覆盖 appId")
    parser.add_argument("--goal", help="从 report 导出时指定 workflow goal")
    parser.add_argument("--output", required=True, help="输出 workflow JSON 的绝对路径")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出文件")
    parser.add_argument("--include-metadata", action="store_true", help="写入脱敏 metadata")
    parser.add_argument("--include-local-evidence-paths", action="store_true", help="metadata 中写入本机 report/artifact 绝对路径")
    parser.add_argument("--dry-run", action="store_true", help="只输出将导出的 workflow，不写文件")
    return parser


def load_workflow(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if args.workflow_id:
        config = load_config(resolve_config_path(args))
        with open_store_from_paths(knowledge_paths_from_config(config)) as store:
            asset = store.get_workflow_asset(args.workflow_id)
        return workflow_from_asset(asset, args.include_metadata, args.include_local_evidence_paths), asset
    report = safe_report_path(args.report)
    return workflow_from_report(report, args.app_id, args.goal, args.include_metadata, args.include_local_evidence_paths), None


def write_export_record(args: argparse.Namespace, workflow_asset_id: str | None, output: Path) -> dict[str, Any] | None:
    if not workflow_asset_id:
        return None
    config = load_config(resolve_config_path(args))
    with open_store_from_paths(knowledge_paths_from_config(config)) as store:
        return store.add_workflow_export(
            {
                "workflowAssetId": workflow_asset_id,
                "outputPathHash": path_hash(output),
                "formatVersion": "workflow-json-v1",
                "metadata": {"includeMetadata": bool(args.include_metadata), "includeLocalEvidencePaths": bool(args.include_local_evidence_paths)},
            }
        )


def export_workflow(args: argparse.Namespace) -> dict[str, Any]:
    output = output_path(args.output)
    if output.exists() and not args.overwrite and not args.dry_run:
        raise EVError(f"output already exists; use --overwrite to replace: {output}")
    workflow, asset = load_workflow(args)
    validate_workflow(workflow)
    local_paths = scan_local_paths(workflow)
    if local_paths and not args.include_local_evidence_paths:
        raise EVError(f"workflow contains local paths at {local_paths}; use --include-local-evidence-paths only when intended")
    if args.dry_run:
        return {"dryRun": True, "output": str(output), "workflow": workflow, "localPathRefs": local_paths}
    write_json(output, workflow)
    written = read_json(output)
    if not isinstance(written, dict):
        raise EVError("written workflow is not a JSON object")
    validate_workflow(written)
    workflow_asset_id = None
    if asset:
        workflow_asset_id = str(asset.get("workflow_asset_id") or asset.get("workflowAssetId") or "")
    export_record = write_export_record(args, workflow_asset_id, output)
    return {"dryRun": False, "output": str(output), "bytes": output.stat().st_size, "workflow": written, "export": export_record, "localPathRefs": local_paths}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = export_workflow(args)
        print_json({"ok": True, "result": result})
        return 0
    except EVError as exc:
        return fail(str(exc), "export_workflow_failed")


if __name__ == "__main__":
    raise SystemExit(main())
