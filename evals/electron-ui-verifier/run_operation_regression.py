#!/usr/bin/env python3
"""验证 durable operation 的幂等、取消、deadline 与重启恢复。"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "electron-ui-verifier" / "scripts"
SKILL_ROOT = ROOT / "skills" / "electron-ui-verifier"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.operations import FINAL_STATES, OperationService, OperationStore  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def action_payload(request_id: str, label: str, deadline_ms: int = 5_000) -> dict[str, Any]:
    return {
        "requestId": request_id,
        "deadlineMs": deadline_ms,
        "runId": str(uuid.uuid4()),
        "action": {"type": "waitText", "value": label},
    }


def process_manager_contract() -> dict[str, Any]:
    paths = (
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "server.md",
        SKILL_ROOT / "references" / "troubleshooting.md",
        SKILL_ROOT / "tests" / "public_contract_support.py",
        SKILL_ROOT / "tests" / "run_process_manager_smoke.py",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    required = (
        "pm_manager.py ensure",
        "pm_session.py open",
        "pm_session.py close",
        "--session-id",
        "--stop-manager-if-idle",
        "renew_session",
        "sessionClose",
    )
    forbidden = (
        "manager_offline",
        "pm_health.py",
        "pm_shutdown.py",
        "manager_started",
        '"pm_manager.py", "start"',
    )
    missing = [marker for marker in required if marker not in text]
    present = [marker for marker in forbidden if marker in text]
    return {
        "ok": not missing and not present,
        "files": [str(path.relative_to(ROOT).as_posix()) for path in paths],
        "missing": missing,
        "forbidden": present,
    }


async def wait_final(service: OperationService, operation_id: str) -> dict[str, Any]:
    for _ in range(1_000):
        operation = service.get(operation_id)["operation"]
        if operation["state"] in FINAL_STATES:
            return operation
        await asyncio.sleep(0.002)
    raise RuntimeError("operation regression 未在期限内收敛")


async def run(work_dir: Path, *, include_process_manager: bool = False) -> dict[str, Any]:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    idempotency_root = work_dir / "idempotency"
    calls = 0

    async def immediate(kind, payload, context):
        nonlocal calls
        calls += 1
        return {"ok": True, "runId": payload["runId"]}

    idempotency = OperationService(idempotency_root, b"regression-secret", immediate)
    request_id = str(uuid.uuid4())
    idempotent_payload = action_payload(request_id, "same")
    first = idempotency.submit("action", idempotent_payload)
    duplicate = idempotency.submit("action", idempotent_payload)
    first_final = await wait_final(idempotency, first["operation"]["operationId"])
    conflict_code = None
    try:
        idempotency.submit("action", action_payload(request_id, "different"))
    except VerifierError as exc:
        conflict_code = exc.code
    await idempotency.shutdown()

    cancel_root = work_dir / "cancel"
    started = asyncio.Event()
    mutation_count = 0

    async def cancellable(kind, payload, context):
        nonlocal mutation_count
        for _ in range(4):
            context.checkpoint()
            context.begin_mutation()
            mutation_count += 1
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                context.mark_outcome_unknown()
                raise
            finally:
                context.end_mutation()
        return {"ok": True}

    cancellable_service = OperationService(cancel_root, b"regression-secret", cancellable)
    submitted = cancellable_service.submit("action", action_payload(str(uuid.uuid4()), "cancel"))
    await asyncio.wait_for(started.wait(), timeout=1)
    cancelled = await cancellable_service.cancel(submitted["operation"]["operationId"])
    count_at_cancel = mutation_count
    await asyncio.sleep(0.03)
    count_after_cancel = mutation_count
    await cancellable_service.shutdown()

    queued_deadline_root = work_dir / "queued-deadline"
    queued_release = asyncio.Event()
    queued_calls: list[str] = []

    async def queued_executor(kind, payload, context):
        queued_calls.append(payload["action"]["value"])
        await queued_release.wait()
        return {"ok": True}

    queued_service = OperationService(queued_deadline_root, b"regression-secret", queued_executor)
    queued_first = queued_service.submit("action", action_payload(str(uuid.uuid4()), "first"))
    queued_expiring = queued_service.submit(
        "action",
        action_payload(str(uuid.uuid4()), "queued-expiring", deadline_ms=100),
    )
    queued_final = await wait_final(queued_service, queued_expiring["operation"]["operationId"])
    queued_release.set()
    await wait_final(queued_service, queued_first["operation"]["operationId"])
    await queued_service.shutdown()

    deadline_root = work_dir / "deadline"
    deadline_mutations = 0

    async def deadline_executor(kind, payload, context):
        nonlocal deadline_mutations
        context.begin_mutation()
        deadline_mutations += 1
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            context.mark_outcome_unknown()
            raise
        finally:
            context.end_mutation()

    deadline_service = OperationService(deadline_root, b"regression-secret", deadline_executor)
    deadline_submit = deadline_service.submit(
        "action",
        action_payload(str(uuid.uuid4()), "deadline", deadline_ms=500),
    )
    deadline_final = await wait_final(deadline_service, deadline_submit["operation"]["operationId"])
    await deadline_service.shutdown()

    recovery_root = work_dir / "recovery"
    store = OperationStore(recovery_root, b"regression-secret")
    queued, _ = store.create("action", action_payload(str(uuid.uuid4()), "queued"), 5_000)
    running, _ = store.create("action", action_payload(str(uuid.uuid4()), "running"), 5_000)
    store.transition(running["operationId"], "running")
    replay_count = 0

    async def forbidden_replay(kind, payload, context):
        nonlocal replay_count
        replay_count += 1
        return {"ok": True}

    recovered_service = OperationService(recovery_root, b"regression-secret", forbidden_replay)
    recovered = recovered_service.recover()
    queued_state = recovered_service.get(queued["operationId"])["operation"]["state"]
    running_state = recovered_service.get(running["operationId"])["operation"]["state"]
    await recovered_service.shutdown()

    checks = {
        "sameRequestReturnsSameOperation": first["operation"]["operationId"] == duplicate["operation"]["operationId"],
        "duplicateExecutedOnce": calls == 1,
        "conflictRejected": conflict_code == "operation_request_conflict",
        "successfulTerminalState": first_final["state"] == "succeeded",
        "runningCancelUnknown": cancelled["operation"]["state"] == "unknown",
        "noMutationAfterCancel": count_at_cancel == count_after_cancel == 1,
        "deadlineUnknown": deadline_final["state"] == "unknown" and deadline_mutations == 1,
        "queuedDeadlineKnown": queued_final["state"] == "deadline_exceeded",
        "queuedDeadlineNeverExecuted": queued_calls == ["first"],
        "queuedRestartCancelled": queued_state == "cancelled",
        "runningRestartUnknown": running_state == "unknown",
        "restartNeverReplays": replay_count == 0,
        "recoveryCount": len(recovered["recovered"]) == 2,
    }
    manager_contract = process_manager_contract() if include_process_manager else None
    if manager_contract is not None:
        checks["processManagerConsumerContract"] = manager_contract["ok"]
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "processManager": manager_contract,
        "metrics": {
            "mutationCountAtCancel": count_at_cancel,
            "mutationCountAfterCancel": count_after_cancel,
            "deadlineMutationCount": deadline_mutations,
            "queuedDeadlineExecutorCalls": len(queued_calls),
            "restartReplayCount": replay_count,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--include-process-manager", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        run(
            Path(args.work_dir).resolve(),
            include_process_manager=args.include_process_manager,
        )
    )
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
