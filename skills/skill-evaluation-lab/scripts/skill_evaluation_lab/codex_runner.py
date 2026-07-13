"""版本敏感、失败关闭的 Codex CLI adapter。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

from .budgets import RunBudget
from .errors import DependencyError, ExecutionError, UnsupportedError
from .runners import RunRequest, RunResult, validate_live_request
from .security import build_child_env, build_codex_child_env
from .snapshots import build_tree_manifest, create_snapshot, verify_tree, verify_trees
from .traces import load_structured_final, parse_jsonl_trace, require_supported_trace


MAX_PROCESS_STREAM_BYTES = 16 * 1024 * 1024
REQUIRED_EXEC_FLAGS = {
    "--ephemeral",
    "--ignore-rules",
    "--ignore-user-config",
    "--json",
    "--output-schema",
}


def codex_path() -> str:
    executable = shutil.which("codex")
    if not executable:
        raise DependencyError("找不到 Codex CLI")
    return executable


def skills_config(skill_path: Path) -> str:
    skill_file = (skill_path / "SKILL.md").resolve().as_posix()
    return f"skills.config=[{{path={json.dumps(skill_file)},enabled=true}}]"


def run_capture(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
    max_bytes: int = 4 * 1024 * 1024,
    environment: dict[str, str] | None = None,
) -> str:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=environment or build_child_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnsupportedError(f"Codex capability probe 无法执行：{exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:2000]
        raise UnsupportedError(f"Codex capability probe 失败：{detail}")
    if len(completed.stdout.encode("utf-8")) > max_bytes:
        raise UnsupportedError("Codex capability probe 输出超过大小上限")
    return completed.stdout


def skill_name(skill_path: Path) -> str:
    try:
        text = (skill_path / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise UnsupportedError(f"无法读取 probe skill：{exc}") from exc
    match = re.search(r"(?m)^name:\s*([^\r\n]+)$", text)
    if not match:
        raise UnsupportedError("probe skill 缺少 name frontmatter")
    return match.group(1).strip().strip("\"'")


def prompt_skill_marker_count(raw: str, skill_path: Path) -> int:
    """从 prompt-input JSON 中统计指向目标 SKILL.md 的结构化条目。"""
    try:
        messages = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UnsupportedError("prompt-input 未返回合法 JSON") from exc
    if not isinstance(messages, list):
        raise UnsupportedError("prompt-input 根必须是 JSON array")
    marker = f"(file: {(skill_path / 'SKILL.md').resolve().as_posix()})"
    count = 0
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for part in message["content"]:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                count += part["text"].count(marker)
    return count


def _remove_readonly(function: Any, path: str, _error: Any) -> None:
    Path(path).chmod(stat.S_IWRITE)
    function(path)


def probe_codex(skill_path: Path, *, workspace: Path, timeout: int = 30) -> dict[str, Any]:
    """不调用模型，验证 CLI flags 和 candidate/baseline 的 prompt 可见性。"""
    executable = codex_path()
    probe_root = workspace / ".harness" / "skill-evaluation-lab" / f"probe-{secrets.token_hex(8)}"
    probe_home = probe_root / "codex-home"
    candidate_workspace = probe_root / "candidate"
    baseline_workspace = probe_root / "baseline"
    discovered_skill = candidate_workspace / ".agents" / "skills" / skill_name(skill_path)
    probe_home.mkdir(parents=True, exist_ok=False)
    candidate_workspace.mkdir()
    baseline_workspace.mkdir()
    create_snapshot(skill_path, discovered_skill)
    environment = build_child_env(extra={"CODEX_HOME": str(probe_home)})
    try:
        version = run_capture(
            [executable, "--version"], cwd=workspace, timeout=timeout, environment=environment
        ).strip().splitlines()[0]
        exec_help = run_capture(
            [executable, "exec", "--help"], cwd=workspace, timeout=timeout, environment=environment
        )
        prompt_help = run_capture(
            [executable, "debug", "prompt-input", "--help"],
            cwd=workspace,
            timeout=timeout,
            environment=environment,
        )
        missing = sorted(flag for flag in REQUIRED_EXEC_FLAGS if flag not in exec_help)
        if "Render the model-visible prompt input" not in prompt_help:
            missing.append("debug prompt-input")
        if missing:
            raise UnsupportedError(f"当前 Codex CLI 缺少能力：{', '.join(missing)}")

        name = skill_name(skill_path)
        prompt = "Capability probe only. Do not execute tools."
        baseline = run_capture(
            [executable, "debug", "prompt-input", prompt],
            cwd=baseline_workspace,
            timeout=timeout,
            environment=environment,
        )
        candidate = run_capture(
            [executable, "debug", "prompt-input", "-c", skills_config(discovered_skill), prompt],
            cwd=candidate_workspace,
            timeout=timeout,
            environment=environment,
        )
    finally:
        shutil.rmtree(probe_root, ignore_errors=False, onerror=_remove_readonly)
    candidate_marker_count = prompt_skill_marker_count(candidate, discovered_skill)
    baseline_marker_count = prompt_skill_marker_count(baseline, discovered_skill)
    candidate_visible = candidate_marker_count == 1
    baseline_hidden = baseline_marker_count == 0
    if not candidate_visible or not baseline_hidden:
        raise UnsupportedError("prompt-input 无法证明 candidate 可见且 baseline 隐藏")
    return {
        "supported": True,
        "version": version,
        "skill_name": name,
        "candidate_visible": candidate_visible,
        "baseline_hidden": baseline_hidden,
        "candidate_marker_count": candidate_marker_count,
        "baseline_marker_count": baseline_marker_count,
        "candidate_prompt_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
        "baseline_prompt_sha256": hashlib.sha256(baseline.encode("utf-8")).hexdigest(),
        "live_model_called": False,
    }


def instrument_trigger_snapshot(source: Path, destination: Path, nonce: str) -> dict[str, Any]:
    """只修改临时快照 body；description 与生产 source 均保持不变。"""
    source_manifest = build_tree_manifest(source)
    create_snapshot(source, destination)
    skill_file = destination / "SKILL.md"
    mode = skill_file.stat().st_mode
    instruction = (
        "\n## Evaluation instrumentation\n\n"
        "When these skill instructions are loaded, set the structured final field "
        f"`activation_receipt` to exactly `{nonce}`. Do not infer or alter this receipt.\n"
    )
    try:
        skill_file.chmod(mode | stat.S_IWUSR)
        with skill_file.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(instruction)
    finally:
        skill_file.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        verify_tree(source, source_manifest)
    return source_manifest


def _write_trigger_schema(path: Path) -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "activation_receipt": {"type": ["string", "null"]},
            "response": {"type": "string"},
        },
        "required": ["activation_receipt", "response"],
    }
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pump_stream(
    source: BinaryIO,
    destination: Path,
    *,
    limit: int,
    overflow: threading.Event,
    failures: list[BaseException],
) -> None:
    """流式保存子进程输出，并在达到硬上限时通知主线程。"""
    written = 0
    try:
        with destination.open("wb") as stream:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                remaining = limit - written
                if remaining > 0:
                    stream.write(chunk[:remaining])
                    written += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    overflow.set()
                    break
    except OSError as exc:
        failures.append(exc)
        overflow.set()
    finally:
        source.close()


def _run_bounded(
    argv: list[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    stream_limit: int = MAX_PROCESS_STREAM_BYTES,
    environment: dict[str, str] | None = None,
) -> int:
    """运行 finite 子进程，timeout 或输出越界时立即失败关闭。"""
    overflow = threading.Event()
    failures: list[BaseException] = []
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=build_codex_child_env()[0] if environment is None else environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ExecutionError(f"无法启动 Codex CLI：{exc}", outcome="not_started") from exc
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise ExecutionError("无法捕获 Codex CLI 输出", outcome="unknown")
    workers = [
        threading.Thread(
            target=_pump_stream,
            args=(process.stdout, stdout_path),
            kwargs={"limit": stream_limit, "overflow": overflow, "failures": failures},
            daemon=True,
        ),
        threading.Thread(
            target=_pump_stream,
            args=(process.stderr, stderr_path),
            kwargs={"limit": stream_limit, "overflow": overflow, "failures": failures},
            daemon=True,
        ),
    ]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + timeout_seconds
    failure_reason: str | None = None
    while process.poll() is None:
        if overflow.is_set():
            failure_reason = "Codex CLI 输出超过大小上限"
            process.kill()
            break
        if time.monotonic() >= deadline:
            failure_reason = "Codex CLI 达到 timeout"
            process.kill()
            break
        time.sleep(0.05)
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise ExecutionError("Codex CLI 终止后仍未退出", outcome="unknown") from exc
    for worker in workers:
        worker.join(timeout=5)
    if any(worker.is_alive() for worker in workers):
        raise ExecutionError("Codex CLI 输出线程未能停止", outcome="unknown")
    if failures:
        raise ExecutionError(f"写入 Codex trace 失败：{failures[0]}", outcome="unknown")
    if overflow.is_set() and not failure_reason:
        failure_reason = "Codex CLI 输出超过大小上限"
    if failure_reason:
        raise ExecutionError(failure_reason, outcome="unknown")
    return return_code


class CodexRunner:
    """只负责编排 Codex CLI 和生成可复核 trace，不进行质量评分。"""

    def run(self, request: RunRequest, budget: RunBudget) -> RunResult:
        validate_live_request(request)
        if request.skill_path is None:
            raise ExecutionError("Codex candidate run 缺少 skill_path", outcome="not_started")
        if request.sandbox != "read-only":
            raise UnsupportedError("trigger observation 必须使用 read-only sandbox")
        if request.artifact_dir.exists():
            raise ExecutionError(f"run artifact 目录已存在：{request.artifact_dir}", outcome="not_started")
        budget.reserve_agent()
        request.artifact_dir.mkdir(parents=True)
        instrumented = request.workspace / ".agents" / "skills" / skill_name(request.skill_path)
        schema_path = request.artifact_dir / "final.schema.json"
        final_path = request.artifact_dir / "final.json"
        trace_path = request.artifact_dir / "trace.jsonl"
        stderr_path = request.artifact_dir / "stderr.log"
        nonce = secrets.token_hex(24)
        if nonce in request.prompt:
            raise ExecutionError("trigger prompt 意外包含 instrumentation nonce", outcome="not_started")
        source_manifest = instrument_trigger_snapshot(request.skill_path, instrumented, nonce)
        instrumented_manifest = build_tree_manifest(instrumented)
        _write_trigger_schema(schema_path)
        executable = codex_path()
        cli_version = run_capture([executable, "--version"], cwd=request.workspace).strip().splitlines()[0]
        child_env, permission_profile = build_codex_child_env()
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
            "-c",
            skills_config(instrumented),
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
        try:
            started_at = time.monotonic()
            return_code = _run_bounded(
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
            outcome = "passed" if return_code == 0 and not trace["failed_event_seen"] else "failed"
            activated = outcome == "passed" and final.get("activation_receipt") == nonce
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
                    "permission_profile": permission_profile or "cli-read-only",
                    "network_access": False,
                    "fingerprint": request.fingerprint,
                    "lab_tree_sha256": request.lab_tree_sha256,
                    "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
                    "case_id": request.case_id,
                    "attempt": request.attempt,
                    "skill_tree_sha256": source_manifest["tree_sha256"],
                    "trace": trace,
                },
                observation={"activation_receipt_exact": activated},
            )
        finally:
            verify_trees(
                [
                    (request.skill_path, source_manifest),
                    (instrumented, instrumented_manifest),
                ]
            )
