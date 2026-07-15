#!/usr/bin/env python3
"""验证批准链在各持久化阶段中断后的可见性、恢复与幂等。"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.actions import ActionExecution  # noqa: E402
from electron_verifier.approval import ApprovalService  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import PendingArtifact  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402


PHASES = ("after_objects", "after_decision", "after_index")


class InjectedInterruption(RuntimeError):
    """表示测试主动注入的批准中断。"""


class FakeSessions:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(live=lambda session_id: SimpleNamespace(page=object()))

    async def status(self, value: str) -> dict[str, Any]:
        return {
            "ok": True,
            "connected": True,
            "session": {
                "sessionId": "session-1",
                "name": "approval-recovery",
                "status": "connected",
                "targetTitle": "Approval Recovery",
            },
        }

    def intent(self, value: str) -> SimpleNamespace:
        return SimpleNamespace(session_id="session-1")


def config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(state_root=root, runs_dir=root / "runs", pending_dir=root / "pending")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_pending(root: Path) -> tuple[RunService, str]:
    runs = RunService(config(root), FakeSessions())
    prepared = asyncio.run(
        runs.prepare(
            {
                "session": "approval-recovery",
                "appId": "approval-recovery",
                "appVersion": "1.0.0",
                "screenDigest": "approval-recovery-main",
                "preState": "form-ready",
                "goal": "填写名称并保存",
                "parameterSchema": {"name": {"type": "string", "required": True}},
            }
        )
    )

    async def fake_execute(live: Any, action: Any) -> ActionExecution:
        return ActionExecution(
            result={"action": "fill", "postconditions": [{"passed": True}]},
            artifacts=[PendingArtifact("application/json", b'{"verified":true}', "evidence", "json")],
        )

    action = {
        "type": "fill",
        "locator": {"label": "名称"},
        "value": "${name}",
        "postconditions": [
            {"type": "value", "locator": {"label": "名称"}, "expected": "${name}"}
        ],
    }
    with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
        result = asyncio.run(runs.append_action(prepared["runId"], action, {"name": "示例"}))
    if not result.get("ok"):
        raise AssertionError("测试 pending action 未通过")
    asyncio.run(runs.finalize(prepared["runId"]))
    return runs, str(prepared["runId"])


def run_phase(work_dir: Path, phase: str) -> dict[str, Any]:
    state_root = work_dir / phase / "state"
    KnowledgeReset(state_root).ensure()
    runs, run_id = prepare_pending(state_root)
    initial_store = CanonicalStore(state_root)
    preview = ApprovalService(initial_store, runs).validate(run_id)
    fingerprint = str(preview["bundleFingerprint"])
    expected_asset_count = int(preview["proposalCount"])

    def interrupt(current: str) -> None:
        if current == phase:
            raise InjectedInterruption(current)

    interrupted = False
    try:
        ApprovalService(initial_store, runs, interrupt).approve(run_id, fingerprint, "批准恢复测试")
    except InjectedInterruption as exc:
        interrupted = str(exc) == phase
    pre_recovery_store = CanonicalStore(state_root)
    decision_before = pre_recovery_store.get_decision(fingerprint)
    active_before = len(pre_recovery_store.list_assets())
    pre_recovery_error = None
    try:
        pre_recovery_store.verify(repair_index=False)
    except VerifierError as exc:
        pre_recovery_error = exc.code

    restarted = CanonicalStore(state_root)
    recovered = restarted.verify()
    retry = ApprovalService(restarted, runs).approve(run_id, fingerprint, "批准恢复测试")
    final = CanonicalStore(state_root).verify(repair_index=False)
    decision_after = retry["decision"]
    object_count = len(list(restarted.paths["objects"].glob("*.json")))
    expected_pre_active = 0 if phase == "after_objects" else expected_asset_count
    expected_pre_error = "knowledge_index_activation_mismatch" if phase == "after_decision" else None
    checks = {
        "interruptionObserved": interrupted,
        "preDecisionVisible": decision_before is not None,
        "preActiveCount": active_before,
        "preRecoveryError": pre_recovery_error,
        "recoveredActiveCount": recovered["activeAssetCount"],
        "finalActiveCount": final["activeAssetCount"],
        "decisionCount": final["decisionCount"],
        "objectCount": object_count,
        "retryAlreadyApproved": retry["alreadyApproved"],
        "sameDecision": decision_before is None
        or decision_before["decisionDigest"] == decision_after["decisionDigest"],
        "expectedPreActive": expected_pre_active,
        "expectedPreError": expected_pre_error,
    }
    checks["passed"] = all(
        (
            checks["interruptionObserved"],
            checks["preDecisionVisible"] is (phase != "after_objects"),
            checks["preActiveCount"] == expected_pre_active,
            checks["preRecoveryError"] == expected_pre_error,
            checks["recoveredActiveCount"] == expected_pre_active,
            checks["finalActiveCount"] == expected_asset_count,
            checks["decisionCount"] == 1,
            checks["objectCount"] == expected_asset_count,
            checks["retryAlreadyApproved"] is (phase != "after_objects"),
            checks["sameDecision"],
        )
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    work_dir = Path(args.work_dir).resolve()
    output = Path(args.output).resolve()
    if ROOT not in work_dir.parents or ".harness" not in work_dir.parts:
        raise SystemExit("--work-dir 必须位于仓库 .harness 隔离目录内")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    phases: dict[str, Any] = {}
    failures: list[str] = []
    try:
        for phase in PHASES:
            phases[phase] = run_phase(work_dir, phase)
            if not phases[phase]["passed"]:
                failures.append(phase)
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    result = {"ok": not failures, "phases": phases, "failures": failures}
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
