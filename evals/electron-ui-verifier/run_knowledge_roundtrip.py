#!/usr/bin/env python3
"""验证 production run 到批准、检索、组合和服务端复用的完整闭环。"""

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
from electron_verifier.asset_execution import AssetExecutionService  # noqa: E402
from electron_verifier.canonical_store import CanonicalStore  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import PendingArtifact  # noqa: E402
from electron_verifier.knowledge_reset import KnowledgeReset  # noqa: E402
from electron_verifier.retrieval import HybridRetriever  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402


APP_ID = "roundtrip-app"
APP_VERSION = "1.0.0"
SCREEN_DIGEST = "screen-main"
INITIAL_STATE = "home"


class FakeSessions:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(live=lambda session_id: SimpleNamespace(page=object()))

    async def status(self, value: str) -> dict[str, Any]:
        return {
            "ok": True,
            "connected": True,
            "session": {
                "sessionId": "roundtrip-session",
                "name": "roundtrip",
                "status": "connected",
                "targetTitle": "Roundtrip Fixture",
            },
        }

    def intent(self, value: str):
        return SimpleNamespace(
            session_id="roundtrip-session",
            target_id="roundtrip-target",
            app_id=APP_ID,
        )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def guarded_path(value: str, label: str) -> Path:
    path = Path(value).resolve()
    if ROOT not in path.parents or ".harness" not in path.parts:
        raise SystemExit(f"{label} 必须位于当前仓库的 .harness 内")
    return path


def config(root: Path):
    return SimpleNamespace(state_root=root, runs_dir=root / "runs", pending_dir=root / "pending")


def context(*, pre_state: str = INITIAL_STATE, max_risk: str = "high", **overrides: Any) -> dict[str, Any]:
    value = {
        "session": "roundtrip",
        "appId": APP_ID,
        "appVersion": APP_VERSION,
        "screenDigest": SCREEN_DIGEST,
        "preState": pre_state,
        "maxRisk": max_risk,
        "goal": "复用批准 workflow",
    }
    value.update(overrides)
    return value


async def fake_execute(live: Any, action: Any) -> ActionExecution:
    risks = []
    if action.action_type == "click" and action.locator is None:
        risks.append({"code": "coordinate_action", "learnable": False})
    artifact = PendingArtifact(
        "application/json",
        json.dumps({"action": action.action_type, "verified": True}).encode("utf-8"),
        f"{action.action_type}-evidence",
        "json",
    )
    return ActionExecution(
        result={"action": action.action_type, "postconditions": [{"passed": True}]},
        artifacts=[artifact],
        risks=risks,
    )


def prepare(runs: RunService, **overrides: Any) -> str:
    return str(asyncio.run(runs.prepare(context(**overrides)))["runId"])


def capture_rejection(
    executor: AssetExecutionService,
    runs: RunService,
    asset_id: str,
    *,
    bindings: dict[str, Any],
    expected_code: str,
    **prepare_overrides: Any,
) -> dict[str, Any]:
    run_id = prepare(runs, **prepare_overrides)
    code = None
    details: dict[str, Any] = {}
    try:
        asyncio.run(executor.execute_action(run_id, asset_id, bindings, None, None))
    except VerifierError as exc:
        code = exc.code
        details = exc.details
    return {
        "code": code,
        "expected": expected_code,
        "zeroSteps": runs.load(run_id)["steps"] == [],
        "reasons": details.get("reasons", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    work_dir = guarded_path(args.work_dir, "--work-dir")
    output = guarded_path(args.output, "--output")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    state = work_dir / "state"
    KnowledgeReset(state).ensure()
    runs = RunService(config(state), FakeSessions())
    production_run = prepare(
        runs,
        goal="确认并填写名称",
        aliases=["保存名称流程"],
        parameterSchema={"name": {"type": "string", "required": True}},
    )
    high_risk_action = {
        "id": "confirm-open",
        "type": "click",
        "options": {"coordinates": {"x": 10, "y": 10}},
        "postconditions": [{"type": "visible", "locator": {"text": "名称表单"}}],
    }
    parameterized_action = {
        "id": "fill-name",
        "type": "fill",
        "locator": {"label": "名称"},
        "value": "${name}",
        "postconditions": [
            {"type": "value", "locator": {"label": "名称"}, "expected": "${name}"}
        ],
    }
    risk_preview = runs.preview_risk(production_run, high_risk_action)
    risk_receipt = runs.approve_risk(
        risk_preview["previewId"],
        risk_preview["fingerprint"],
        "批准隔离 roundtrip 坐标动作",
    )
    with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
        first_step = asyncio.run(
            runs.append_action(production_run, high_risk_action, risk_receipt=risk_receipt["receiptId"])
        )
        second_step = asyncio.run(
            runs.append_action(production_run, parameterized_action, {"name": "production-secret"})
        )
    finalized = asyncio.run(runs.finalize(production_run))
    store = CanonicalStore(state)
    approvals = ApprovalService(store, runs)
    approval_preview = approvals.validate(production_run)
    approved = approvals.approve(
        production_run,
        approval_preview["bundleFingerprint"],
        "批准 production roundtrip 资产",
    )
    action_assets = {
        asset["payload"]["action"]["id"]: asset
        for asset in approved["actionAssets"]
    }
    high_asset = action_assets["confirm-open"]
    parameter_asset = action_assets["fill-name"]
    workflow_asset = approved["workflowAsset"]
    retriever = HybridRetriever(store)
    try:
        search_context = {
            "appId": APP_ID,
            "appVersion": APP_VERSION,
            "screenDigest": SCREEN_DIGEST,
            "preState": INITIAL_STATE,
            "maxRisk": "high",
        }
        search = retriever.search("confirm-open", search_context, kind="action", explain=True)
        composition = retriever.compose(
            {
                **search_context,
                "subgoals": ["confirm-open", "fill-name"],
                "bindings": {"name": "compose-secret"},
            }
        )
        metadata = retriever.get_asset(workflow_asset["assetId"])
        executor = AssetExecutionService(store, runs, retriever.record_outcome)
        rejections = {
            "app": capture_rejection(
                executor,
                runs,
                high_asset["assetId"],
                bindings={},
                expected_code="asset_app_mismatch",
                appId="other-app",
            ),
            "version": capture_rejection(
                executor,
                runs,
                high_asset["assetId"],
                bindings={},
                expected_code="asset_context_mismatch",
                appVersion="2.0.0",
            ),
            "screen": capture_rejection(
                executor,
                runs,
                high_asset["assetId"],
                bindings={},
                expected_code="asset_context_mismatch",
                screenDigest="other-screen",
            ),
            "state": capture_rejection(
                executor,
                runs,
                high_asset["assetId"],
                bindings={},
                expected_code="asset_context_mismatch",
                pre_state="other-state",
            ),
            "risk": capture_rejection(
                executor,
                runs,
                high_asset["assetId"],
                bindings={},
                expected_code="asset_context_mismatch",
                max_risk="low",
            ),
            "receipt": capture_rejection(
                executor,
                runs,
                high_asset["assetId"],
                bindings={},
                expected_code="risk_authorization_required",
            ),
            "parameter": capture_rejection(
                executor,
                runs,
                parameter_asset["assetId"],
                bindings={},
                expected_code="parameter_binding_required",
                pre_state=parameter_asset["payload"]["compatibility"]["preState"],
            ),
        }
        reuse_run = prepare(
            runs,
            parameterSchema={"name": {"type": "string", "required": True}},
        )
        reuse_preview = executor.preview_risk(reuse_run, high_asset["assetId"])
        reuse_receipt = runs.approve_risk(
            reuse_preview["previewId"],
            reuse_preview["fingerprint"],
            "批准隔离 workflow 复用",
        )
        with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
            reused = asyncio.run(
                executor.execute_workflow(
                    reuse_run,
                    workflow_asset["assetId"],
                    {"name": "reuse-secret"},
                    {high_asset["assetId"]: reuse_receipt["receiptId"]},
                    False,
                    None,
                )
            )
        reuse_journal = runs.load(reuse_run)
        asyncio.run(runs.finalize(reuse_run))
        listing = retriever.list_assets(APP_ID, None, 20)
    finally:
        retriever.close()
    reliability = {item["assetId"]: item for item in listing["assets"]}
    workflow_payload = workflow_asset["payload"]
    rejection_gate = all(
        item["code"] == item["expected"] and item["zeroSteps"] is True
        for item in rejections.values()
    )
    gates = {
        "productionRunPassed": first_step["ok"] is True and second_step["ok"] is True and finalized["ok"] is True,
        "productionPending": bool(finalized.get("pending")),
        "approvalGraph": len(approved["actionAssets"]) == 2 and len(approved["decision"]["assetIds"]) == 3,
        "workflowReferencesOnly": "steps" not in workflow_payload and len(workflow_payload["actionIds"]) == 2,
        "searchReuse": search["decision"] == "reuse" and search["candidates"][0]["assetId"] == high_asset["assetId"],
        "composeIdsOnly": composition["assetIds"] == workflow_payload["actionIds"] and "workflow" not in composition,
        "metadataOnly": "payload" not in metadata["asset"] and "action" not in metadata["asset"],
        "serverRejections": rejection_gate,
        "workflowReuse": reused["ok"] is True and [step["assetId"] for step in reuse_journal["steps"]] == workflow_payload["actionIds"],
        "bindingMinimized": "production-secret" not in str(runs.load(production_run)) and "reuse-secret" not in str(reuse_journal),
        "reliabilityUpdated": all(reliability[asset_id]["successCount"] >= 2 for asset_id in approved["decision"]["assetIds"]),
        "storeVerified": CanonicalStore(state).verify()["activeAssetCount"] == 3,
    }
    failures = [name for name, passed in gates.items() if not passed]
    result = {
        "ok": not failures,
        "gates": gates,
        "production": {
            "runId": production_run,
            "actionAssetIds": workflow_payload["actionIds"],
            "workflowAssetId": workflow_asset["assetId"],
            "proposalCount": len(approved["assets"]),
        },
        "retrieval": {
            "decision": search["decision"],
            "composeAssetIds": composition["assetIds"],
        },
        "rejections": rejections,
        "reuse": {
            "runId": reuse_run,
            "stepAssetIds": [step["assetId"] for step in reuse_journal["steps"]],
        },
        "failures": failures,
    }
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
