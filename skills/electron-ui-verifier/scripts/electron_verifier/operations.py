"""持久化 mutation operation、幂等提交与协作式取消。"""

from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Awaitable, Callable

from .atomic_io import atomic_write_json, canonical_json_bytes, exclusive_write_json
from .errors import VerifierError
from .limits import DEFAULT_LIMITS, RuntimeLimits
from .sensitivity import BindingContext, transient_input_values


OPEN_STATES = {"queued", "running"}
FINAL_STATES = {"succeeded", "failed", "cancelled", "deadline_exceeded", "unknown"}
_TRANSITIONS = {
    "queued": {"running", "failed", "cancelled", "deadline_exceeded"},
    "running": {"succeeded", "failed", "cancelled", "deadline_exceeded", "unknown"},
}
_SUBMISSION_FIELDS = {
    "action": {"requestId", "deadlineMs", "runId", "action", "bindings", "parameterSchema", "riskReceipt"},
    "workflow": {"requestId", "deadlineMs", "runId", "workflow", "autoFinalize", "bindings", "riskReceipts"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _deadline_at(deadline_ms: int) -> str:
    value = datetime.now(timezone.utc) + timedelta(milliseconds=deadline_ms)
    return value.isoformat().replace("+00:00", "Z")


def _remaining_deadline_ms(value: str) -> int:
    try:
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise VerifierError("operation_store_invalid", "operation deadlineAt 无效", status=500) from exc
    remaining = int((deadline - datetime.now(timezone.utc)).total_seconds() * 1000)
    return max(1, remaining)


def _uuid(value: Any, label: str) -> str:
    try:
        parsed = uuid.UUID(str(value or ""))
    except (ValueError, TypeError, AttributeError) as exc:
        raise VerifierError("invalid_operation_id", f"{label} 必须是非零 UUID") from exc
    if parsed.int == 0:
        raise VerifierError("invalid_operation_id", f"{label} 必须是非零 UUID")
    return str(parsed)


def _request_fingerprint(secret: bytes, kind: str, payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "requestId"}
    return hmac.new(secret, canonical_json_bytes({"kind": kind, "payload": stable}), sha256).hexdigest()


def _projection_context(kind: str, payload: dict[str, Any]) -> BindingContext:
    bindings = payload.get("bindings") if isinstance(payload.get("bindings"), dict) else {}
    scalar_bindings = [
        value for value in bindings.values() if isinstance(value, (str, int, float, bool))
    ]
    workflow = payload.get("workflow")
    actions = (
        [payload.get("action")]
        if kind == "action"
        else workflow.get("steps", []) if isinstance(workflow, dict) else []
    )
    transient = list(scalar_bindings)
    for action in actions if isinstance(actions, list) else []:
        transient.extend(transient_input_values(action))
    return BindingContext.create({}, {}).with_transient_values(transient)


class OperationContext:
    """仅存于 owner loop 的 deadline/cancel 上下文。"""

    def __init__(self, operation_id: str, deadline_ms: int) -> None:
        self.operation_id = operation_id
        self._deadline = asyncio.get_running_loop().time() + deadline_ms / 1000
        self._cancel_requested = False
        self._mutation_inflight = False
        self._outcome_unknown = False

    @property
    def mutation_inflight(self) -> bool:
        return self._mutation_inflight

    @property
    def outcome_unknown(self) -> bool:
        return self._outcome_unknown

    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline - asyncio.get_running_loop().time())

    def checkpoint(self) -> None:
        if self._cancel_requested:
            raise VerifierError("operation_cancelled", "operation 已请求取消", status=409)
        if self.remaining_seconds() <= 0:
            raise VerifierError("operation_deadline_exceeded", "operation 已超过服务端 deadline", status=504)

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def begin_mutation(self) -> None:
        self.checkpoint()
        self._mutation_inflight = True

    def end_mutation(self) -> None:
        self._mutation_inflight = False

    def mark_outcome_unknown(self) -> None:
        self._outcome_unknown = True

    def constrain_action(self, value: Any) -> Any:
        """把 action 和 postcondition timeout 限制到剩余预算内。"""

        self.checkpoint()
        if not isinstance(value, dict):
            return value
        remaining_ms = max(1, int(self.remaining_seconds() * 1000))
        constrained = deepcopy(value)
        options = constrained.setdefault("options", {})
        if isinstance(options, dict):
            try:
                requested = int(options.get("timeoutMs", 30_000))
            except (TypeError, ValueError) as exc:
                raise VerifierError("invalid_timeout", "action timeoutMs 必须是整数") from exc
            options["timeoutMs"] = min(requested, remaining_ms)
        postconditions = constrained.get("postconditions")
        if isinstance(postconditions, list):
            for assertion in postconditions:
                if isinstance(assertion, dict):
                    try:
                        requested = int(assertion.get("timeoutMs", 10_000))
                    except (TypeError, ValueError) as exc:
                        raise VerifierError("invalid_assertion", "postcondition timeoutMs 必须是整数") from exc
                    assertion["timeoutMs"] = min(requested, remaining_ms)
        return constrained


class OperationStore:
    """以 operation 文件和 request 索引提供原子、可重放状态。"""

    def __init__(self, root: Path, secret: bytes, limits: RuntimeLimits = DEFAULT_LIMITS) -> None:
        self.root = root
        self.requests_dir = root / "requests"
        self.secret = secret
        self.limits = limits

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.requests_dir.mkdir(parents=True, exist_ok=True)

    def _operation_path(self, operation_id: str) -> Path:
        return self.root / f"{_uuid(operation_id, 'operationId')}.json"

    def _request_path(self, request_id: str) -> Path:
        digest = sha256(request_id.encode("utf-8")).hexdigest()
        return self.requests_dir / f"{digest}.json"

    @staticmethod
    def _read(path: Path, code: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise VerifierError(code, "operation 不存在", status=404) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("operation_store_invalid", f"operation 状态不可读：{type(exc).__name__}", status=500) from exc
        if not isinstance(value, dict):
            raise VerifierError("operation_store_invalid", "operation 状态根节点必须是 object", status=500)
        return value

    def load(self, operation_id: str) -> dict[str, Any]:
        operation = self._read(self._operation_path(operation_id), "operation_not_found")
        if operation.get("operationId") != _uuid(operation_id, "operationId"):
            raise VerifierError("operation_store_invalid", "operation identity 不匹配", status=500)
        return operation

    def _save(self, operation: dict[str, Any]) -> None:
        operation["updatedAt"] = _now()
        operation["revision"] = int(operation.get("revision", 0)) + 1
        atomic_write_json(
            self._operation_path(str(operation["operationId"])),
            operation,
            max_bytes=self.limits.operation_record_bytes,
        )

    def create(self, kind: str, payload: dict[str, Any], deadline_ms: int) -> tuple[dict[str, Any], bool]:
        self.ensure()
        request_id = _uuid(payload.get("requestId"), "requestId")
        fingerprint = _request_fingerprint(self.secret, kind, payload)
        request_path = self._request_path(request_id)
        if request_path.exists():
            existing = self._read(request_path, "operation_request_not_found")
            if not hmac.compare_digest(str(existing.get("requestFingerprint") or ""), fingerprint):
                raise VerifierError(
                    "operation_request_conflict",
                    "相同 requestId 已用于不同请求",
                    status=409,
                )
            return self.load(str(existing.get("operationId") or "")), False
        if len(list(self.root.glob("*.json"))) >= self.limits.operation_history_limit:
            raise VerifierError("operation_history_full", "operation 历史达到上限，请先执行显式保留清理", status=503)
        operation_id = str(uuid.uuid4())
        now = _now()
        operation = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "requestId": request_id,
            "requestFingerprint": fingerprint,
            "kind": kind,
            "runId": str(payload.get("runId") or ""),
            "state": "queued",
            "done": False,
            "cancelRequested": False,
            "deadlineAt": _deadline_at(deadline_ms),
            "createdAt": now,
            "updatedAt": now,
            "revision": 1,
        }
        atomic_write_json(self._operation_path(operation_id), operation, max_bytes=self.limits.operation_record_bytes)
        index = {
            "schemaVersion": 1,
            "requestId": request_id,
            "requestFingerprint": fingerprint,
            "operationId": operation_id,
        }
        if not exclusive_write_json(request_path, index):
            existing = self._read(request_path, "operation_request_not_found")
            if not hmac.compare_digest(str(existing.get("requestFingerprint") or ""), fingerprint):
                raise VerifierError("operation_request_conflict", "相同 requestId 已用于不同请求", status=409)
            return self.load(str(existing.get("operationId") or "")), False
        return operation, True

    def transition(self, operation_id: str, state: str, **fields: Any) -> dict[str, Any]:
        operation = self.load(operation_id)
        current = str(operation.get("state") or "")
        if current in FINAL_STATES:
            return operation
        if state not in _TRANSITIONS.get(current, set()):
            raise VerifierError("operation_transition_invalid", f"非法 operation 状态迁移：{current} -> {state}", status=500)
        operation.update(fields)
        operation["state"] = state
        operation["done"] = state in FINAL_STATES
        if state == "running":
            operation["startedAt"] = _now()
        if state in FINAL_STATES:
            operation["finishedAt"] = _now()
        self._save(operation)
        return operation

    def request_cancel(self, operation_id: str) -> dict[str, Any]:
        operation = self.load(operation_id)
        if operation.get("state") not in FINAL_STATES and not operation.get("cancelRequested"):
            operation["cancelRequested"] = True
            self._save(operation)
        return operation

    def recover(self) -> list[str]:
        self.ensure()
        recovered: list[str] = []
        for path in sorted(self.root.glob("*.json")):
            operation = self._read(path, "operation_not_found")
            state = operation.get("state")
            if state == "queued":
                self.transition(
                    str(operation["operationId"]),
                    "cancelled",
                    error={"code": "service_restarted_before_execution"},
                )
                recovered.append(str(operation["operationId"]))
            elif state == "running":
                self.transition(
                    str(operation["operationId"]),
                    "unknown",
                    error={"code": "service_interrupted", "outcome": "unknown"},
                )
                recovered.append(str(operation["operationId"]))
        return recovered


OperationExecutor = Callable[[str, dict[str, Any], OperationContext], Awaitable[dict[str, Any]]]


class OperationService:
    """在 owner loop 内运行真实 task；HTTP future 不代表 mutation 生命周期。"""

    def __init__(
        self,
        root: Path,
        secret: bytes,
        executor: OperationExecutor,
        limits: RuntimeLimits = DEFAULT_LIMITS,
    ) -> None:
        self.store = OperationStore(root, secret, limits)
        self.executor = executor
        self.limits = limits
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._contexts: dict[str, OperationContext] = {}

    def recover(self) -> dict[str, Any]:
        return {"recovered": self.store.recover()}

    def submit(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind not in _SUBMISSION_FIELDS:
            raise VerifierError("operation_kind_invalid", f"不支持的 operation kind：{kind}")
        unknown = sorted(set(payload) - _SUBMISSION_FIELDS[kind])
        if unknown:
            raise VerifierError("operation_request_invalid", f"operation 请求包含未知字段：{unknown}")
        if not payload.get("runId") or payload.get(kind) is None:
            raise VerifierError("operation_request_invalid", f"{kind} operation 缺少 runId 或 {kind}")
        default_deadline = self.limits.workflow_timeout_ms if kind == "workflow" else self.limits.action_timeout_ms
        if isinstance(payload.get("deadlineMs"), bool):
            raise VerifierError("operation_deadline_invalid", "deadlineMs 必须是整数")
        try:
            deadline_ms = int(payload.get("deadlineMs", default_deadline))
        except (TypeError, ValueError) as exc:
            raise VerifierError("operation_deadline_invalid", "deadlineMs 必须是整数") from exc
        if deadline_ms < 1 or deadline_ms > self.limits.operation_deadline_max_ms:
            raise VerifierError(
                "operation_deadline_invalid",
                f"deadlineMs 必须在 1..{self.limits.operation_deadline_max_ms}",
            )
        payload = dict(payload)
        payload["requestId"] = _uuid(payload.get("requestId"), "requestId")
        payload["runId"] = _uuid(payload.get("runId"), "runId")
        operation, created = self.store.create(kind, payload, deadline_ms)
        if created:
            operation_id = str(operation["operationId"])
            context = OperationContext(
                operation_id,
                _remaining_deadline_ms(str(operation["deadlineAt"])),
            )
            self._contexts[operation_id] = context
            self._tasks[operation_id] = asyncio.create_task(
                self._run(operation_id, kind, payload, context),
                name=f"electron-verifier-operation-{operation_id}",
            )
        return {"ok": True, "created": created, "operation": operation}

    def get(self, operation_id: str) -> dict[str, Any]:
        return {"ok": True, "operation": self.store.load(operation_id)}

    async def cancel(self, operation_id: str) -> dict[str, Any]:
        operation = self.store.request_cancel(operation_id)
        if operation.get("state") in FINAL_STATES:
            return {"ok": True, "operation": operation}
        context = self._contexts.get(operation_id)
        task = self._tasks.get(operation_id)
        if context is not None:
            context.request_cancel()
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=self.limits.operation_cancel_grace_seconds)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        current = self.store.load(operation_id)
        if current.get("state") in OPEN_STATES:
            unknown = bool(context and (context.mutation_inflight or context.outcome_unknown))
            current = self.store.transition(
                operation_id,
                "unknown" if unknown else "cancelled",
                error={"code": "operation_cancelled", **({"outcome": "unknown"} if unknown else {})},
            )
        return {"ok": True, "operation": current}

    async def _run(
        self,
        operation_id: str,
        kind: str,
        payload: dict[str, Any],
        context: OperationContext,
    ) -> None:
        acquired = False
        projection = _projection_context(kind, payload)
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=context.remaining_seconds())
            acquired = True
            context.checkpoint()
            self.store.transition(operation_id, "running")
            response = await asyncio.wait_for(
                self.executor(kind, payload, context),
                timeout=context.remaining_seconds(),
            )
            response = projection.project(response)
            if context.outcome_unknown:
                self.store.transition(
                    operation_id,
                    "unknown",
                    response=response,
                    error={"code": "operation_outcome_unknown", "outcome": "unknown"},
                )
            elif response.get("ok") is False:
                self.store.transition(
                    operation_id,
                    "failed",
                    response=response,
                    error={"code": "operation_result_failed"},
                )
            else:
                self.store.transition(operation_id, "succeeded", response=response)
        except asyncio.TimeoutError:
            unknown = context.mutation_inflight or context.outcome_unknown
            self.store.transition(
                operation_id,
                "unknown" if unknown else "deadline_exceeded",
                error={"code": "operation_deadline_exceeded", **({"outcome": "unknown"} if unknown else {})},
            )
        except asyncio.CancelledError:
            unknown = context.mutation_inflight or context.outcome_unknown
            self.store.transition(
                operation_id,
                "unknown" if unknown else "cancelled",
                error={"code": "operation_cancelled", **({"outcome": "unknown"} if unknown else {})},
            )
        except VerifierError as exc:
            unknown = context.mutation_inflight or context.outcome_unknown
            error = projection.project(exc.envelope())
            if unknown:
                error["outcome"] = "unknown"
            self.store.transition(operation_id, "unknown" if unknown else "failed", error=error)
        except Exception as exc:
            unknown = context.mutation_inflight or context.outcome_unknown
            self.store.transition(
                operation_id,
                "unknown" if unknown else "failed",
                error={
                    "ok": False,
                    "code": "operation_internal_error",
                    "error": type(exc).__name__,
                    **({"outcome": "unknown"} if unknown else {}),
                },
            )
        finally:
            if acquired:
                self._lock.release()
            self._tasks.pop(operation_id, None)
            self._contexts.pop(operation_id, None)

    async def shutdown(self) -> None:
        for operation_id, context in list(self._contexts.items()):
            context.request_cancel()
            self.store.request_cancel(operation_id)
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
        self.store.recover()
