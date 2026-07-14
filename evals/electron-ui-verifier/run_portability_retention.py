#!/usr/bin/env python3
"""验证真实复制安装、workspace 隔离与显式 retention 公共契约。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = (ROOT / ".harness").resolve()
SOURCE_SKILL = ROOT / "skills" / "electron-ui-verifier"
SCRIPTS = SOURCE_SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from knowledge_fixtures import action_asset  # noqa: E402


NOW = datetime.now(timezone.utc)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_json(arguments: list[str], *, cwd: Path, timeout: float = 90.0) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"命令未返回 JSON：rc={completed.returncode} stdout={completed.stdout[:500]} stderr={completed.stderr[:500]}"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeError("命令 JSON 根节点不是 object")
    return completed.returncode, value


def has_playwright(python_path: Path) -> bool:
    completed = subprocess.run(
        [str(python_path), "-X", "utf8", "-B", "-c", "import playwright.async_api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return completed.returncode == 0


def service_python(work_dir: Path) -> Path:
    executable = "python.exe" if os.name == "nt" else "python"
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    candidates = []
    if os.environ.get("EV_SERVICE_PYTHON"):
        candidates.append(Path(str(os.environ["EV_SERVICE_PYTHON"])))
    candidates.extend(
        (
            Path(sys.executable),
            work_dir.parent / "fresh-env" / bin_dir / executable,
            ROOT / ".harness" / "electron-ui-verifier" / "baseline-venv" / bin_dir / executable,
        )
    )
    for candidate in candidates:
        if candidate.is_absolute() and candidate.exists() and has_playwright(candidate):
            return candidate.resolve()
    raise RuntimeError("未找到安装 Playwright 的 verifier Python")


def install_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def old_timestamp(seconds: int = 3600) -> str:
    return (NOW - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def create_run(state_root: Path, *, state: str = "passed", run_id: str | None = None) -> str:
    run_id = run_id or str(uuid.uuid4())
    run_dir = state_root / "runs" / run_id
    write_json(
        run_dir / "journal.json",
        {
            "schemaVersion": 1,
            "runId": run_id,
            "state": state,
            "createdAt": old_timestamp(7200),
            "updatedAt": old_timestamp(),
            "steps": [],
        },
    )
    (run_dir / "artifacts").mkdir()
    (run_dir / "artifacts" / "evidence.txt").write_text("portable-retention", encoding="utf-8")
    return run_id


def create_operation(state_root: Path, run_id: str) -> str:
    operation_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    write_json(
        state_root / "operations" / f"{operation_id}.json",
        {
            "schemaVersion": 1,
            "operationId": operation_id,
            "requestId": request_id,
            "requestFingerprint": "a" * 64,
            "kind": "action",
            "runId": run_id,
            "state": "succeeded",
            "done": True,
            "cancelRequested": False,
            "deadlineAt": old_timestamp(3500),
            "createdAt": old_timestamp(7200),
            "updatedAt": old_timestamp(),
            "finishedAt": old_timestamp(),
            "revision": 2,
        },
    )
    request_name = hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"
    write_json(
        state_root / "operations" / "requests" / request_name,
        {
            "schemaVersion": 1,
            "requestId": request_id,
            "requestFingerprint": "a" * 64,
            "operationId": operation_id,
        },
    )
    return operation_id


def command(python_path: Path, script: Path, workspace: Path, *arguments: str) -> list[str]:
    return [
        str(python_path),
        "-u",
        "-X",
        "utf8",
        "-B",
        str(script),
        *arguments,
        "--workspace",
        str(workspace),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
    output = Path(args.output).resolve()
    if work_dir == HARNESS_ROOT or HARNESS_ROOT not in work_dir.parents:
        raise SystemExit("--work-dir 必须是当前仓库 .harness 内的隔离子目录")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    install_root = work_dir / "install" / "electron-ui-verifier"
    workspace = work_dir / "workspace"
    workspace.mkdir(parents=True)
    shutil.copytree(
        SOURCE_SKILL,
        install_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    failures: list[str] = []
    checks: dict[str, Any] = {}
    try:
        python_path = service_python(work_dir)
        before_digest = install_digest(install_root)
        init_command = command(
            python_path,
            install_root / "scripts" / "ev_init.py",
            workspace,
            "--python",
            str(python_path),
        )
        init_code, initialized = run_json(init_command, cwd=workspace)
        state_root = workspace / ".harness" / "electron-ui-verifier"
        service_path = workspace / ".harness" / "process-manager" / "services" / "electron-ui-verifier.json"
        service = json.loads(service_path.read_text(encoding="utf-8"))
        after_digest = install_digest(install_root)
        checks["copyInstall"] = {
            "initCode": init_code,
            "initOk": initialized.get("ok"),
            "reportedRoots": initialized.get("roots"),
            "installCheck": initialized.get("installCheck"),
            "launcherScript": service.get("launcher", {}).get("script"),
            "workspace": str(workspace),
            "installRoot": str(install_root),
            "installUnchanged": before_digest == after_digest,
            "stateUnderWorkspace": state_root.is_dir() and workspace in state_root.parents,
            "installHasNoState": not (install_root / ".harness").exists(),
        }

        old_run = create_run(state_root)
        linked_run = create_run(state_root)
        operation_id = create_operation(state_root, linked_run)
        open_run = create_run(state_root, state="running")
        approved_run = create_run(state_root)
        approved_asset = action_asset("portable-app", "已批准动作", [], evidence_digest="e" * 64)
        CanonicalStore(state_root).activate([approved_asset], run_id=approved_run)
        pending_run = create_run(state_root)
        write_json(
            state_root / "pending" / pending_run / "pending.json",
            {
                "runId": pending_run,
                "bundleFingerprint": "f" * 64,
                "proposals": [{"assetId": "action-" + "1" * 40}],
            },
        )
        orphan = action_asset("portable-app", "孤儿动作", [], evidence_digest="d" * 64)
        CanonicalStore(state_root).stage_objects([orphan])
        retired = state_root / "retired" / "sentinel"
        retired.mkdir(parents=True)
        (retired / "keep.txt").write_text("keep-retired", encoding="utf-8")

        prune_script = install_root / "scripts" / "ev_prune.py"
        policy_args = (
            "--terminal-age-days",
            "0",
            "--operation-expiration-days",
            "0",
            "--orphan-grace-days",
            "0",
            "--max-runs",
            "100",
        )
        preview_code, preview = run_json(
            command(python_path, prune_script, workspace, "preview", *policy_args),
            cwd=workspace,
        )
        preview_preserved = (state_root / "runs" / old_run).exists()
        replacement = "0" if preview["fingerprint"][-1] != "0" else "1"
        wrong = preview["fingerprint"][:-1] + replacement
        confirm_code, confirmation = run_json(
            command(
                python_path,
                prune_script,
                workspace,
                "apply",
                *policy_args,
                "--fingerprint",
                preview["fingerprint"],
            ),
            cwd=workspace,
        )
        stale_code, stale = run_json(
            command(
                python_path,
                prune_script,
                workspace,
                "apply",
                *policy_args,
                "--fingerprint",
                wrong,
                "--confirm",
            ),
            cwd=workspace,
        )
        apply_code, applied = run_json(
            command(
                python_path,
                prune_script,
                workspace,
                "apply",
                *policy_args,
                "--fingerprint",
                preview["fingerprint"],
                "--confirm",
            ),
            cwd=workspace,
        )
        repeat_code, repeated = run_json(
            command(
                python_path,
                prune_script,
                workspace,
                "apply",
                *policy_args,
                "--fingerprint",
                preview["fingerprint"],
                "--confirm",
            ),
            cwd=workspace,
        )
        include_code, include_preview = run_json(
            command(python_path, prune_script, workspace, "preview", *policy_args, "--include-orphans"),
            cwd=workspace,
        )
        protected = {f"{item['kind']}:{item['id']}": item["reasons"] for item in preview["protected"]}
        checks["retention"] = {
            "previewCode": preview_code,
            "candidateKeys": [item["key"] for item in preview["candidates"]],
            "previewPreservedData": preview_preserved,
            "confirmationCode": confirm_code,
            "confirmationError": confirmation.get("code"),
            "staleCode": stale_code,
            "staleError": stale.get("code"),
            "applyCode": apply_code,
            "applyError": applied.get("code"),
            "applyMessage": applied.get("error"),
            "applyDetails": applied.get("details"),
            "deletedCount": applied.get("deletedCount"),
            "repeatCode": repeat_code,
            "repeatError": repeated.get("code"),
            "alreadyApplied": repeated.get("alreadyApplied"),
            "linkedRunPreserved": (state_root / "runs" / linked_run).exists(),
            "openRunPreserved": (state_root / "runs" / open_run).exists(),
            "approvedRunPreserved": (state_root / "runs" / approved_run).exists(),
            "pendingRunPreserved": (state_root / "runs" / pending_run).exists(),
            "retiredPreserved": (retired / "keep.txt").read_text(encoding="utf-8") == "keep-retired",
            "protected": protected,
            "includePreviewCode": include_code,
            "explicitOrphanCandidate": orphan.asset_id in {item["id"] for item in include_preview["candidates"]},
            "defaultOrphanProtected": f"orphanObject:{orphan.asset_id}" in protected,
            "operationRemoved": not (state_root / "operations" / f"{operation_id}.json").exists(),
            "oldRunRemoved": not (state_root / "runs" / old_run).exists(),
        }
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    copy_check = checks.get("copyInstall", {})
    retention = checks.get("retention", {})
    required = {
        "copyInit": copy_check.get("initCode") == 0 and copy_check.get("initOk") is True,
        "rootSeparation": copy_check.get("reportedRoots") == {"skill": str(install_root), "workspace": str(workspace)},
        "launcherFromInstall": copy_check.get("launcherScript") == str(install_root / "scripts" / "ev_server.py"),
        "workspaceOnlyWrites": (
            copy_check.get("installUnchanged") is True and copy_check.get("installHasNoState") is True
        ),
        "previewOnly": retention.get("previewCode") == 0 and retention.get("previewPreservedData") is True,
        "confirmationGate": retention.get("confirmationError") == "retention_confirmation_required",
        "staleGate": retention.get("staleError") == "retention_fingerprint_stale",
        "boundedApply": retention.get("applyCode") == 0 and retention.get("deletedCount") == 2,
        "idempotent": retention.get("repeatCode") == 0 and retention.get("alreadyApplied") is True,
        "referencesProtected": all(
            retention.get(name) is True
            for name in ("linkedRunPreserved", "openRunPreserved", "approvedRunPreserved", "pendingRunPreserved")
        ),
        "retiredUntouched": retention.get("retiredPreserved") is True,
        "orphanExplicit": (
            retention.get("defaultOrphanProtected") is True
            and retention.get("explicitOrphanCandidate") is True
        ),
    }
    failures.extend(name for name, passed in required.items() if not passed)
    result = {"ok": not failures, "checks": checks, "required": required, "failures": failures}
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
