"""通过 verifier 公共入口执行 Termous 隔离只读契约。"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from public_contract_support import (
    ManagedVerifier,
    operation_response,
    operation_state,
    wait_operation,
    write_json,
)


SESSION = "termous"
APP_ID = "termous-smoke"
APP_VERSION = "isolated-test"
SCREEN_DIGEST = "termous-main-window"
PRE_STATE = "isolated-startup"


def prepare_run(managed: ManagedVerifier, goal: str) -> dict[str, Any]:
    return managed.cli(
        "ev_prepare.py",
        "--session",
        SESSION,
        "--app-id",
        APP_ID,
        "--app-version",
        APP_VERSION,
        "--screen-digest",
        SCREEN_DIGEST,
        "--pre-state",
        PRE_STATE,
        "--max-risk",
        "low",
        "--goal",
        goal,
    )


def execute_action(
    managed: ManagedVerifier,
    data_dir: Path,
    run_id: str,
    action: dict[str, Any],
    *,
    expected_states: tuple[str, ...] = ("succeeded",),
) -> dict[str, Any]:
    action_path = data_dir / f"{action['id']}.action.json"
    write_json(action_path, action)
    submitted = managed.cli(
        "ev_action.py",
        "--run-id",
        run_id,
        "--action",
        str(action_path),
        "--deadline-ms",
        "60000",
    )
    waited = wait_operation(managed, submitted, timeout_seconds=60)
    response = operation_response(waited["completed"], expected_states=expected_states)
    return {
        "operationId": waited["operationId"],
        "state": operation_state(waited["completed"]),
        "response": response,
    }


def execute_workflow(
    managed: ManagedVerifier,
    data_dir: Path,
    run_id: str,
    workflow: dict[str, Any],
    *,
    name: str,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    workflow_path = data_dir / f"{name}.workflow.json"
    write_json(workflow_path, workflow)
    submitted = managed.cli(
        "ev_workflow.py",
        "--run-id",
        run_id,
        "--workflow",
        str(workflow_path),
        "--no-finalize",
        "--deadline-ms",
        str(timeout_seconds * 1000),
    )
    waited = wait_operation(managed, submitted, timeout_seconds=timeout_seconds)
    return {
        "operationId": waited["operationId"],
        "state": operation_state(waited["completed"]),
        "response": operation_response(waited["completed"]),
    }


def strict_locator_smoke(managed: ManagedVerifier, data_dir: Path) -> dict[str, Any]:
    prepared = prepare_run(managed, "验证歧义 locator 不触发点击")
    run_id = str(prepared["runId"])
    before = execute_action(
        managed,
        data_dir,
        run_id,
        {"id": "strict-before", "type": "snapshot", "options": {"timeoutMs": 10000}},
    )
    ambiguous = execute_action(
        managed,
        data_dir,
        run_id,
        {
            "id": "ambiguous-connect",
            "type": "click",
            "locator": {"role": "button", "accessibleName": "连接", "exact": True},
            "options": {"timeoutMs": 10000},
            "postconditions": [
                {"type": "titleContains", "expected": "Termous", "timeoutMs": 10000}
            ],
        },
        expected_states=("failed",),
    )
    after = execute_action(
        managed,
        data_dir,
        run_id,
        {"id": "strict-after", "type": "snapshot", "options": {"timeoutMs": 10000}},
    )
    finalized = managed.cli("ev_finalize.py", "--run-id", run_id, expected_codes=(2,))
    error = ambiguous["response"].get("step", {}).get("error", {})
    details = error.get("details", {}) if isinstance(error, dict) else {}
    before_preview = str(before["response"].get("step", {}).get("result", {}).get("preview") or "")
    after_preview = str(after["response"].get("step", {}).get("result", {}).get("preview") or "")
    return {
        "runId": run_id,
        "operationIds": [before["operationId"], ambiguous["operationId"], after["operationId"]],
        "errorCode": error.get("code") if isinstance(error, dict) else None,
        "candidateCount": details.get("candidateCount") if isinstance(details, dict) else None,
        "stateUnchanged": bool(before_preview) and before_preview == after_preview,
        "reportStatus": finalized.get("result", {}).get("status"),
        "pending": finalized.get("pending"),
    }


def navigation_smoke(managed: ManagedVerifier, data_dir: Path) -> dict[str, Any]:
    prepared = prepare_run(managed, "验证 Termous 只读页面导航")
    run_id = str(prepared["runId"])
    views = (
        ("hosts", "主机", True),
        ("forwards", "端口转发", True),
        ("workstation", "工作站", False),
        ("settings", "设置", True),
    )
    steps: list[dict[str, Any]] = []
    for slug, accessible_name, capture in views:
        steps.extend(
            [
                {
                    "id": f"navigate-{slug}",
                    "type": "click",
                    "locator": {
                        "role": "button",
                        "accessibleName": accessible_name,
                        "exact": True,
                    },
                    "options": {"timeoutMs": 10000},
                    "postconditions": [
                        {"type": "titleContains", "expected": "Termous", "timeoutMs": 10000}
                    ],
                },
                {"id": f"snapshot-{slug}", "type": "snapshot", "options": {"timeoutMs": 10000}},
            ]
        )
        if capture:
            steps.append(
                {
                    "id": f"screenshot-{slug}",
                    "type": "screenshot",
                    "options": {"timeoutMs": 10000, "label": f"navigation-{slug}"},
                }
            )
    workflow = {
        "schemaVersion": 1,
        "appId": APP_ID,
        "goal": "验证 Termous 只读页面导航",
        "steps": steps,
    }
    executed = execute_workflow(managed, data_dir, run_id, workflow, name="navigation")
    finalized = managed.cli("ev_finalize.py", "--run-id", run_id)
    snapshot_steps = [
        step
        for step in executed["response"].get("steps", [])
        if step.get("action", {}).get("type") == "snapshot"
    ]
    previews = [str(step.get("result", {}).get("preview") or "") for step in snapshot_steps]
    view_evidence = [
        {
            "label": step.get("label"),
            "characters": len(preview),
            "sha256": hashlib.sha256(preview.encode("utf-8")).hexdigest(),
        }
        for step, preview in zip(snapshot_steps, previews, strict=True)
    ]
    artifacts = [
        item
        for item in finalized.get("result", {}).get("artifacts", [])
        if str(item.get("label") or "").startswith("navigation-")
    ]
    return {
        "runId": run_id,
        "operationId": executed["operationId"],
        "state": finalized.get("state"),
        "pending": finalized.get("pending"),
        "views": view_evidence,
        "viewsDiffer": len(previews) == len(views) and len(set(previews)) == len(previews),
        "screenshots": {
            "successCount": len(artifacts),
            "distinctDigests": len({item.get("sha256") for item in artifacts}) == len(artifacts),
            "qualityVerified": bool(artifacts)
            and all(item.get("quality", {}).get("pixelVariation", 0) > 1 for item in artifacts),
        },
    }


def public_service_smoke(
    managed: ManagedVerifier,
    endpoint: str,
    data_dir: Path,
) -> dict[str, Any]:
    health = managed.cli("ev_health.py")
    probe = managed.cli("ev_probe.py", "--cdp", endpoint)
    targets = probe.get("targets", [])
    candidates = [item for item in targets if not str(item.get("url", "")).startswith("devtools://")]
    if not candidates:
        raise RuntimeError("公共 ev_probe 未发现 Termous page target")
    selected = candidates[0]
    attach = managed.cli(
        "ev_attach.py",
        "--name",
        SESSION,
        "--cdp",
        endpoint,
        "--target-title-contains",
        "Termous",
    )
    prepared = prepare_run(managed, "验证当前窗口可稳定只读采集")
    run_id = str(prepared["runId"])
    workflow = {
        "schemaVersion": 1,
        "appId": APP_ID,
        "goal": "验证当前窗口可稳定只读采集",
        "steps": [
            {"id": "snapshot", "type": "snapshot", "options": {"timeoutMs": 10000}},
            *[
                {
                    "id": f"screenshot-{index + 1}",
                    "type": "screenshot",
                    "options": {"timeoutMs": 10000, "label": f"shot-{index + 1}"},
                }
                for index in range(10)
            ],
            {
                "id": "console",
                "type": "collectConsole",
                "options": {"maxEvents": 100},
                "continueOnFailure": True,
            },
            {
                "id": "exceptions",
                "type": "collectExceptions",
                "options": {"maxEvents": 100},
                "continueOnFailure": True,
            },
            {
                "id": "network",
                "type": "collectNetwork",
                "options": {"maxEvents": 100},
                "continueOnFailure": True,
            },
        ],
    }
    executed = execute_workflow(managed, data_dir, run_id, workflow, name="read-only-capture")
    steps = executed["response"].get("steps", [])
    if len(steps) != len(workflow["steps"]):
        raise RuntimeError("公共 workflow 未执行全部只读步骤")
    durations = [
        float(step["durationMs"])
        for step in steps
        if step.get("action", {}).get("type") == "screenshot"
    ]
    if len(durations) != 10:
        raise RuntimeError("公共 workflow 截图结果不完整")
    finalized = managed.cli("ev_finalize.py", "--run-id", run_id)
    finalized_again = managed.cli("ev_finalize.py", "--run-id", run_id)
    report = finalized["result"]
    screenshots = [item for item in report["artifacts"] if item.get("mediaType") == "image/png"]
    ordered = sorted(durations)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {
        "backend": health.get("backend"),
        "probe": {
            "browserVersion": probe.get("browserVersion"),
            "targetCount": len(targets),
            "selectedTarget": selected,
        },
        "attach": {
            "connected": attach.get("ok") is True,
            "sessionId": attach.get("session", {}).get("sessionId"),
        },
        "knowledge": prepared.get("knowledge"),
        "run": {
            "runId": run_id,
            "operationId": executed["operationId"],
            "state": finalized.get("state"),
            "report": finalized.get("report"),
            "reportIdempotent": finalized.get("report") == finalized_again.get("report"),
            "pending": finalized.get("pending"),
            "stepCount": report.get("summary", {}).get("stepCount"),
            "artifactCount": report.get("summary", {}).get("artifactCount"),
        },
        "screenshots": {
            "successCount": len(screenshots),
            "p95Ms": round(p95, 3),
            "maxMs": round(max(durations), 3),
            "minBytes": min(item["bytes"] for item in screenshots),
            "maxBytes": max(item["bytes"] for item in screenshots),
            "qualityVerified": all(
                item.get("quality", {}).get("pixelVariation", 0) > 1 for item in screenshots
            ),
        },
        "diagnostics": {
            "independentArtifacts": sum(
                item.get("label") in {"console", "exception", "network"}
                for item in report["artifacts"]
            )
        },
        "strictLocator": strict_locator_smoke(managed, data_dir),
        "navigation": navigation_smoke(managed, data_dir),
    }


def stale_session_smoke(managed: ManagedVerifier) -> dict[str, Any]:
    status = managed.cli("ev_sessions.py", "--session", SESSION, expected_codes=(0, 2))
    first = managed.cli("ev_detach.py", "--session", SESSION)
    second = managed.cli("ev_detach.py", "--session", SESSION)
    session_existed = isinstance(status.get("session"), dict)
    return {
        "sessionExisted": session_existed,
        "staleAfterAppExit": status.get("connected") is False if session_existed else None,
        "status": status.get("session", {}).get("status"),
        "firstDetach": first.get("alreadyDetached"),
        "secondDetach": second.get("alreadyDetached"),
    }
