"""只基于已激活 canonical asset 的服务端复用执行。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .canonical_store import CanonicalStore
from .compatibility import RuntimeContext, require_asset_compatibility
from .errors import VerifierError
from .knowledge_models import CanonicalAsset
from .operations import OperationContext
from .run_context import current_run_state
from .runs import RunService
from .sensitivity import bind_parameters, normalize_parameter_schema


OutcomeRecorder = Callable[[str, bool, str], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AssetExecutionService:
    """在 owner loop 内完成资产解析、现场门禁与可靠性反馈。"""

    def __init__(self, store: CanonicalStore, runs: RunService, outcome_recorder: OutcomeRecorder) -> None:
        self.store = store
        self.runs = runs
        self.outcome_recorder = outcome_recorder

    @staticmethod
    def _context(journal: dict[str, Any], pre_state: str | None = None) -> RuntimeContext:
        return RuntimeContext.decode(
            {
                "appId": journal.get("appId"),
                "appVersion": journal.get("appVersion"),
                "screenDigest": journal.get("screenDigest"),
                "preState": pre_state if pre_state is not None else current_run_state(journal),
                "maxRisk": journal.get("maxRisk"),
            }
        )

    def _load(self, asset_id: str, kind: str) -> CanonicalAsset:
        asset = self.store.get_asset(asset_id)
        if asset.kind != kind:
            raise VerifierError(
                "asset_kind_mismatch",
                f"asset kind 必须是 {kind}：{asset_id}",
                status=409,
            )
        return asset

    def _validate_action(
        self,
        asset: CanonicalAsset,
        journal: dict[str, Any],
        bindings: Any,
        *,
        pre_state: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
        compatibility = asset.payload["compatibility"]
        require_asset_compatibility(asset.app_id, compatibility, self._context(journal, pre_state))
        action = asset.payload["action"]
        schema = normalize_parameter_schema(asset.payload["parameterSchema"])
        bind_parameters(action, bindings, schema)
        return action, schema, compatibility

    def _record(self, asset_id: str, succeeded: bool, response: dict[str, Any]) -> None:
        try:
            response.setdefault("knowledgeOutcomes", []).append(
                self.outcome_recorder(asset_id, succeeded, _now())
            )
        except VerifierError:
            # UI 结果已经确定时，派生排序统计失败不能篡改验证结论。
            response.setdefault("warnings", []).append(
                {"code": "knowledge_outcome_deferred", "assetId": asset_id}
            )

    def preview_risk(self, run_id: str, asset_id: str) -> dict[str, Any]:
        journal = self.runs.load(run_id)
        asset = self._load(asset_id, "action")
        require_asset_compatibility(
            asset.app_id,
            asset.payload["compatibility"],
            self._context(journal),
        )
        action = asset.payload["action"]
        result = self.runs.preview_risk(run_id, action)
        result["assetId"] = asset.asset_id
        return result

    async def execute_action(
        self,
        run_id: str,
        asset_id: str,
        bindings: Any,
        risk_receipt: str | None,
        operation_context: OperationContext | None,
    ) -> dict[str, Any]:
        journal = self.runs.load(run_id)
        asset = self._load(asset_id, "action")
        action, schema, compatibility = self._validate_action(asset, journal, bindings)
        result = await self.runs.append_action(
            run_id,
            action,
            bindings,
            schema,
            risk_receipt,
            operation_context,
            {
                "assetId": asset.asset_id,
                "preState": compatibility["preState"],
                "postState": compatibility["postState"],
                "risk": compatibility["risk"],
            },
        )
        self._record(asset.asset_id, result.get("ok") is True, result)
        return result

    def _workflow_actions(
        self,
        workflow: CanonicalAsset,
        journal: dict[str, Any],
        bindings: Any,
    ) -> list[tuple[CanonicalAsset, dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]]:
        payload = workflow.payload
        context = self._context(journal)
        require_asset_compatibility(workflow.app_id, payload["compatibility"], context)
        workflow_schema = normalize_parameter_schema(payload["parameterSchema"])
        required = [f"${{{name}}}" for name in payload["requiredParameters"]]
        bind_parameters(required, bindings, workflow_schema)
        actions = []
        merged_schema: dict[str, dict[str, Any]] = {}
        for asset_id, transition in zip(payload["actionIds"], payload["transitions"], strict=True):
            asset = self._load(asset_id, "action")
            action_schema = normalize_parameter_schema(asset.payload["parameterSchema"])
            action_bindings = (
                {name: bindings[name] for name in action_schema if name in bindings}
                if isinstance(bindings, dict)
                else bindings
            )
            action, schema, compatibility = self._validate_action(
                asset,
                journal,
                action_bindings,
                pre_state=transition["preState"],
            )
            if (
                compatibility["preState"] != transition["preState"]
                or compatibility["postState"] != transition["postState"]
            ):
                raise VerifierError(
                    "workflow_transition_mismatch",
                    f"workflow transition 与 action asset 不一致：{asset_id}",
                    status=409,
                )
            for name, definition in schema.items():
                if name in merged_schema and merged_schema[name] != definition:
                    raise VerifierError(
                        "parameter_schema_conflict",
                        f"workflow action 参数 schema 冲突：{name}",
                        status=409,
                    )
                merged_schema[name] = definition
            actions.append((asset, action, schema, compatibility))
        if merged_schema != workflow_schema:
            raise VerifierError(
                "workflow_schema_mismatch",
                "workflow parameterSchema 与引用 action assets 不一致",
                status=409,
            )
        return actions

    @staticmethod
    def _receipt(receipts: dict[str, Any], index: int, asset: CanonicalAsset, action: dict[str, Any]) -> str | None:
        label = str(action.get("id") or "")
        keys = (f"{index}:{asset.asset_id}", str(index), label, asset.asset_id)
        value = next((receipts[key] for key in keys if key and key in receipts), None)
        if value is not None and not isinstance(value, str):
            raise VerifierError("invalid_risk_receipts", f"riskReceipts[{index}] 必须是 receiptId 字符串")
        return value

    async def execute_workflow(
        self,
        run_id: str,
        asset_id: str,
        bindings: Any,
        risk_receipts: Any,
        auto_finalize: bool,
        operation_context: OperationContext | None,
    ) -> dict[str, Any]:
        journal = self.runs.load(run_id)
        workflow = self._load(asset_id, "workflow")
        actions = self._workflow_actions(workflow, journal, bindings)
        if risk_receipts in (None, {}):
            receipts: dict[str, Any] = {}
        elif isinstance(risk_receipts, dict):
            receipts = risk_receipts
        else:
            raise VerifierError("invalid_risk_receipts", "riskReceipts 必须是 object")
        self.runs.begin_asset_workflow(
            run_id,
            workflow.asset_id,
            workflow.goal,
            len(actions),
            workflow.payload["parameterSchema"],
        )
        steps = []
        warnings = []
        outcomes = []
        for index, (action_asset, action, schema, compatibility) in enumerate(actions):
            if operation_context is not None:
                operation_context.checkpoint()
            result = await self.runs.append_action(
                run_id,
                action,
                bindings,
                None,
                self._receipt(receipts, index, action_asset, action),
                operation_context,
                {
                    "assetId": action_asset.asset_id,
                    "preState": compatibility["preState"],
                    "postState": compatibility["postState"],
                    "risk": compatibility["risk"],
                },
            )
            self._record(action_asset.asset_id, result.get("ok") is True, result)
            steps.append(result["step"])
            warnings.extend(result.get("warnings", []))
            outcomes.extend(result.get("knowledgeOutcomes", []))
            if result.get("ok") is not True:
                break
        succeeded = len(steps) == len(actions) and all(step.get("status") == "passed" for step in steps)
        response: dict[str, Any] = {
            "ok": succeeded,
            "runId": run_id,
            "workflowAssetId": workflow.asset_id,
            "steps": steps,
        }
        if warnings:
            response["warnings"] = warnings
        if outcomes:
            response["knowledgeOutcomes"] = outcomes
        self._record(workflow.asset_id, succeeded, response)
        if auto_finalize:
            finalized = await self.runs.finalize(run_id)
            finalized["workflowAssetId"] = workflow.asset_id
            if response.get("warnings"):
                finalized["warnings"] = response["warnings"]
            finalized["knowledgeOutcomes"] = response.get("knowledgeOutcomes", [])
            return finalized
        return response
