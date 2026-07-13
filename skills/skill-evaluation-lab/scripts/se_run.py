#!/usr/bin/env python3
"""执行 trigger/behavior 实验并保存成对证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from skill_evaluation_lab.assertions import evaluate_assertions
from skill_evaluation_lab.budgets import RunBudget, build_experiment_plan
from skill_evaluation_lab.cli import run_cli
from skill_evaluation_lab.codex_runner import (
    MAX_PROCESS_STREAM_BYTES,
    CodexRunner,
    codex_path,
    run_capture,
    skill_name,
    skills_config,
)
from skill_evaluation_lab.contracts import SuiteDocument, load_suite, resolve_source
from skill_evaluation_lab.errors import AuthorizationError, ExecutionError, LabError
from skill_evaluation_lab.isolation import CaseWorkspace, RunLayout, create_case_workspace, create_run_layout
from skill_evaluation_lab.output import render_json
from skill_evaluation_lab.runners import FakeRunner, RunRequest, RunResult, validate_live_request
from skill_evaluation_lab.security import build_codex_child_env
from skill_evaluation_lab.snapshots import build_tree_manifest, create_snapshot, verify_tree
from skill_evaluation_lab.traces import load_structured_final, parse_jsonl_trace, require_supported_trace


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(value, pretty=True) + "\n", encoding="utf-8")


def _write_behavior_schema(path: Path) -> None:
    _write_json(
        path,
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"response": {"type": "string"}},
            "required": ["response"],
        },
    )


def _behavior_child_env() -> tuple[dict[str, str], str]:
    """仅透传桌面受管 workspace profile，不接受任意权限配置。"""
    environment, profile = build_codex_child_env()
    return environment, profile or "cli-workspace-write"


def _run_behavior_bounded(
    argv: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    environment: dict[str, str],
) -> int:
    """直接落盘子进程流，并在 timeout 或输出越界时失败关闭。"""
    try:
        with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_stream,
                stderr=stderr_stream,
            )
            deadline = time.monotonic() + timeout_seconds
            failure: str | None = None
            while process.poll() is None:
                output_bytes = stdout_path.stat().st_size + stderr_path.stat().st_size
                if output_bytes > MAX_PROCESS_STREAM_BYTES:
                    failure = "Codex CLI 输出超过大小上限"
                    process.kill()
                    break
                if time.monotonic() >= deadline:
                    failure = "Codex CLI 达到 timeout"
                    process.kill()
                    break
                time.sleep(0.05)
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                raise ExecutionError("Codex CLI 终止后仍未退出", outcome="unknown") from exc
            output_bytes = stdout_path.stat().st_size + stderr_path.stat().st_size
            if output_bytes > MAX_PROCESS_STREAM_BYTES and failure is None:
                failure = "Codex CLI 输出超过大小上限"
    except OSError as exc:
        raise ExecutionError(f"无法启动或记录 Codex CLI：{exc}", outcome="not_started") from exc
    if failure:
        raise ExecutionError(failure, outcome="unknown")
    return return_code


class BehaviorCodexRunner:
    """执行允许写工作区的行为 case，不读取 grader oracle。"""

    def run(self, request: RunRequest, budget: RunBudget) -> RunResult:
        validate_live_request(request)
        if request.skill_path is not None:
            try:
                request.skill_path.resolve().relative_to(request.workspace.resolve())
            except ValueError as exc:
                raise ExecutionError("behavior skill 必须位于隔离工作区内", outcome="not_started") from exc
        if request.artifact_dir.exists():
            raise ExecutionError(f"run artifact 目录已存在：{request.artifact_dir}", outcome="not_started")
        budget.reserve_agent()
        request.artifact_dir.mkdir(parents=True)
        schema_path = request.artifact_dir / "final.schema.json"
        final_path = request.artifact_dir / "final.json"
        trace_path = request.artifact_dir / "trace.jsonl"
        stderr_path = request.artifact_dir / "stderr.log"
        _write_behavior_schema(schema_path)

        executable = codex_path()
        cli_version = run_capture([executable, "--version"], cwd=request.workspace).strip().splitlines()[0]
        argv = [
            executable,
            "-a",
            "never",
            "-s",
            request.sandbox,
            "-m",
            request.model,
            "-C",
            str(request.workspace),
        ]
        if request.skill_path is not None:
            argv.extend(["-c", skills_config(request.skill_path)])
        argv.extend(
            [
                "-c",
                'web_search="disabled"',
                "-c",
                'shell_environment_policy.inherit="none"',
                "-c",
                "features.skill_mcp_dependency_install=false",
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--strict-config",
                "--json",
                "--color",
                "never",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(final_path),
                request.prompt,
            ]
        )
        child_env, permission_profile = _behavior_child_env()
        visible_manifest = build_tree_manifest(request.skill_path) if request.skill_path is not None else None
        try:
            started_at = time.monotonic()
            return_code = _run_behavior_bounded(
                argv,
                cwd=request.workspace,
                stdout_path=trace_path,
                stderr_path=stderr_path,
                timeout_seconds=min(request.timeout_seconds, max(1, int(budget.remaining_seconds()))),
                environment=child_env,
            )
            trace = parse_jsonl_trace(trace_path)
            require_supported_trace(trace, return_code=return_code)
            final = load_structured_final(final_path) if return_code == 0 or final_path.exists() else {}
            outcome = "passed" if return_code == 0 and not trace["failed_event_seen"] and final else "failed"
            return RunResult(
                outcome=outcome,
                return_code=return_code,
                final=final,
                trace_path=trace_path,
                stderr_path=stderr_path,
                duration_seconds=max(0.0, time.monotonic() - started_at),
                usage=dict(trace["usage"]),
                provenance={
                    "adapter": "codex-cli",
                    "cli_version": cli_version,
                    "model": request.model,
                    "sandbox": request.sandbox,
                    "permission_profile": permission_profile,
                    "network_access": False,
                    "fingerprint": request.fingerprint,
                    "lab_tree_sha256": request.lab_tree_sha256,
                    "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                    "case_id": request.case_id,
                    "attempt": request.attempt,
                    "variant": request.variant,
                    **(
                        {"skill_tree_sha256": visible_manifest["tree_sha256"]}
                        if visible_manifest is not None
                        else {}
                    ),
                    "trace": trace,
                },
            )
        finally:
            if request.skill_path is not None and visible_manifest is not None:
                verify_tree(request.skill_path, visible_manifest)


def _snapshot_sources(suite: SuiteDocument, snapshot_root: Path) -> tuple[dict[str, Path | None], dict[str, Any]]:
    candidate_source = resolve_source(suite.root, suite.data["skill_path"], "$.skill_path")
    sources: dict[str, Path | None] = {"candidate": candidate_source, "baseline": None}
    manifests: dict[str, Any] = {"candidate": build_tree_manifest(candidate_source), "baseline": "none"}
    candidate_snapshot = snapshot_root / "candidate"
    create_snapshot(candidate_source, candidate_snapshot)
    snapshots: dict[str, Path | None] = {"candidate": candidate_snapshot, "baseline": None}

    baseline = suite.data["baseline"]
    if baseline["mode"] == "snapshot":
        baseline_source = resolve_source(suite.root, baseline["path"], "$.baseline.path")
        baseline_snapshot = snapshot_root / "baseline"
        manifests["baseline"] = build_tree_manifest(baseline_source)
        create_snapshot(baseline_source, baseline_snapshot)
        sources["baseline"] = baseline_source
        snapshots["baseline"] = baseline_snapshot
    return snapshots, {"sources": sources, "manifests": manifests}


def _relative(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    return path.resolve().relative_to(root.resolve()).as_posix()


def _serialize_result(result: RunResult, root: Path) -> dict[str, Any]:
    return {
        "outcome": result.outcome,
        "return_code": result.return_code,
        "final": result.final,
        "trace_path": _relative(result.trace_path, root),
        "stderr_path": _relative(result.stderr_path, root),
        "duration_seconds": result.duration_seconds,
        "usage": result.usage,
        "provenance": result.provenance,
        "observation": result.observation,
    }


def _create_workspace(
    suite: SuiteDocument,
    layout: RunLayout,
    entry: dict[str, Any],
    case: dict[str, Any],
    snapshots: dict[str, Path | None],
) -> CaseWorkspace:
    visible_skill = None if case["mode"] == "trigger" else snapshots[entry["variant"]]
    visible_name = skill_name(visible_skill) if visible_skill is not None else None
    return create_case_workspace(
        layout,
        case_id=case["id"],
        variant=entry["variant"],
        repetition=entry["repetition"],
        suite_root=suite.root,
        inputs=case["inputs"],
        agent_skill=visible_skill,
        agent_skill_name=visible_name,
    )


def _case_record(
    *,
    suite: SuiteDocument,
    entry: dict[str, Any],
    case: dict[str, Any],
    workspace: CaseWorkspace,
    result: RunResult,
    assertions: dict[str, Any] | None,
    run_root: Path,
    effective_sandbox: str,
) -> dict[str, Any]:
    expected_trigger = case.get("should_trigger")
    observed_trigger = bool(result.observation.get("activation_receipt_exact"))
    trigger_match = observed_trigger == expected_trigger
    passed = (
        result.outcome == "passed" and trigger_match
        if case["mode"] == "trigger"
        else result.outcome == "passed" and assertions is not None and assertions["status"] == "PASS"
    )
    return {
        **entry,
        "status": "PASS" if passed else "FAIL",
        "workspace": _relative(workspace.root, run_root),
        "baseline_commit": workspace.baseline_commit,
        "pairing": {
            "pair_key": f"{case['id']}:{entry['repetition']}",
            "prompt_sha256": hashlib.sha256(case["prompt"].encode("utf-8")).hexdigest(),
            "inputs": list(case["inputs"]),
            "model": suite.data["runner"]["model"],
            "sandbox": effective_sandbox,
            "timeout_seconds": suite.data["runner"]["timeout_seconds"],
            "network_access": False,
            "skill_snapshot": entry["variant"] if workspace.agent_skill is not None else "none",
        },
        "expected_trigger": expected_trigger,
        "observed_trigger": observed_trigger if case["mode"] == "trigger" else None,
        "runner": _serialize_result(result, run_root),
        "assertions": assertions,
    }


def execute_suite(
    suite: SuiteDocument,
    *,
    work_root: Path,
    approved_fingerprint: str | None,
    authorize_live: bool,
    run_id: str | None = None,
) -> dict[str, Any]:
    """按 preview 矩阵串行执行，失败时也保留已完成记录。"""
    plan = build_experiment_plan(suite)
    adapter_name = suite.data["runner"]["adapter"]
    if adapter_name == "codex-cli" and not authorize_live:
        raise AuthorizationError("live suite 未获得显式授权", guidance="先运行 se_plan.py 并批准 fingerprint")
    if adapter_name == "codex-cli" and approved_fingerprint != plan["fingerprint"]:
        raise AuthorizationError("批准的 fingerprint 与当前 suite 不匹配", guidance="重新预览并批准当前 fingerprint")

    layout = create_run_layout(work_root, suite.suite_id, plan["fingerprint"], run_id=run_id)
    snapshots, source_state = _snapshot_sources(suite, layout.snapshots)
    budget_values = suite.data["budgets"]
    budget = RunBudget(
        max_agent_runs=budget_values["max_agent_runs"],
        max_judge_runs=budget_values["max_judge_runs"],
        max_wall_seconds=budget_values["max_wall_seconds"],
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "state": "running",
        "suite_id": suite.suite_id,
        "fingerprint": plan["fingerprint"],
        "run_id": layout.root.name,
        "execution_order": plan["execution_order"],
        "requested_concurrency": plan["requested_concurrency"],
        "effective_concurrency": plan["effective_concurrency"],
        "gates": dict(suite.data["gates"]),
        "lab_identity": {
            "tree_sha256": plan["lab_identity"]["tree_sha256"],
            "file_count": plan["lab_identity"]["file_count"],
        },
        "source_identity": {
            variant: (
                "none"
                if manifest_value == "none"
                else {
                    "tree_sha256": manifest_value["tree_sha256"],
                    "file_count": len(manifest_value["files"]),
                }
            )
            for variant, manifest_value in source_state["manifests"].items()
        },
        "records": [],
    }
    manifest_path = layout.root / "run.json"
    _write_json(manifest_path, manifest)
    cases = {item["id"]: item for item in suite.cases}
    fake_runner = FakeRunner()
    trigger_runner = CodexRunner()
    behavior_runner = BehaviorCodexRunner()
    try:
        for entry in plan["matrix"]:
            case = cases[entry["case_id"]]
            workspace = _create_workspace(suite, layout, entry, case, snapshots)
            artifact_dir = layout.artifacts / case["id"] / f"{entry['variant']}-{entry['repetition']}"
            effective_sandbox = "read-only" if case["mode"] == "trigger" else suite.data["runner"]["sandbox"]
            request = RunRequest(
                run_id=layout.root.name,
                case_id=case["id"],
                attempt=entry["repetition"],
                prompt=case["prompt"],
                workspace=workspace.root,
                artifact_dir=artifact_dir,
                model=suite.data["runner"]["model"],
                sandbox=effective_sandbox,
                timeout_seconds=suite.data["runner"]["timeout_seconds"],
                fingerprint=plan["fingerprint"],
                lab_tree_sha256=plan["lab_identity"]["tree_sha256"],
                approved_fingerprint=approved_fingerprint,
                live_authorized=authorize_live,
                skill_path=snapshots["candidate"] if case["mode"] == "trigger" else workspace.agent_skill,
                variant=entry["variant"],
            )
            if adapter_name == "fake":
                result = fake_runner.run(request, budget)
            elif case["mode"] == "trigger":
                result = trigger_runner.run(request, budget)
            else:
                result = behavior_runner.run(request, budget)
            assertion_result = None
            if case["mode"] == "behavior":
                assertion_result = evaluate_assertions(
                    case.get("assertions", []),
                    workspace=workspace.root,
                    trusted_verifier=case.get("trusted_verifier", False),
                )
            manifest["records"].append(
                _case_record(
                    suite=suite,
                    entry=entry,
                    case=case,
                    workspace=workspace,
                    result=result,
                    assertions=assertion_result,
                    run_root=layout.root,
                    effective_sandbox=effective_sandbox,
                )
            )
            manifest["budget"] = budget.snapshot()
            _write_json(manifest_path, manifest)
        for variant, source in source_state["sources"].items():
            if source is not None:
                verify_tree(source, source_state["manifests"][variant])
        manifest["state"] = "completed"
        manifest["status"] = "PASS" if all(item["status"] == "PASS" for item in manifest["records"]) else "FAIL"
        _write_json(manifest_path, manifest)
        return {**manifest, "run_root": str(layout.root), "manifest_path": str(manifest_path)}
    except LabError as exc:
        integrity_error: LabError | None = None
        try:
            for variant, source in source_state["sources"].items():
                if source is not None:
                    verify_tree(source, source_state["manifests"][variant])
        except LabError as integrity_exc:
            integrity_error = integrity_exc
        reported = integrity_error or exc
        manifest.update(
            {"state": "failed", "status": "ERROR", "error": reported.to_dict(), "budget": budget.snapshot()}
        )
        _write_json(manifest_path, manifest)
        raise reported


def main() -> int:
    parser = argparse.ArgumentParser(description="执行 Skill Evaluation Lab 实验矩阵")
    parser.add_argument("--suite", required=True, type=Path, help="suite JSON 路径")
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path(".harness") / "skill-evaluation-lab" / "runs",
        help="隔离运行目录根路径",
    )
    parser.add_argument("--fingerprint", help="经 se_plan.py 预览并批准的 fingerprint")
    parser.add_argument("--authorize-live", action="store_true", help="授权当前 fingerprint 的有限 live 调用")
    parser.add_argument("--run-id", help="可选的稳定运行标识；不得复用已有目录")
    parser.add_argument("--output", type=Path, help="可选 run manifest 副本路径")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    args = parser.parse_args()

    def handler() -> object:
        result = execute_suite(
            load_suite(args.suite),
            work_root=args.work_root,
            approved_fingerprint=args.fingerprint,
            authorize_live=args.authorize_live,
            run_id=args.run_id,
        )
        if args.output:
            manifest_copy = {
                key: value for key, value in result.items() if key not in {"run_root", "manifest_path"}
            }
            _write_json(args.output, manifest_copy)
        return result

    return run_cli("suite.run", handler, pretty=args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
