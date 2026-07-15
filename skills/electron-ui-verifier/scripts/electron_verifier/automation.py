"""单 automation owner 与有界跨线程命令队列。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from .approval import ApprovalService
from .asset_execution import AssetExecutionService
from .canonical_store import CanonicalStore
from .config import ServiceConfig
from .driver import PlaywrightCdpDriver
from .errors import VerifierError
from .limits import DEFAULT_LIMITS, RuntimeLimits
from .operations import OperationContext, OperationService
from .runs import RunService
from .knowledge_reset import KnowledgeReset
from .retrieval import DEFAULT_MIN_MARGIN, DEFAULT_MIN_SCORE, HybridRetriever
from .sessions import SessionManager


def _integer_option(value: Any, default: int, label: str) -> int:
    try:
        return int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise VerifierError("invalid_operation_option", f"{label} 必须是整数") from exc


def _float_option(value: Any, default: float, label: str) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise VerifierError("invalid_operation_option", f"{label} 必须是数字") from exc


@dataclass
class _Command:
    operation: str
    payload: dict[str, Any]
    future: concurrent.futures.Future[dict[str, Any]]


class AutomationRuntime:
    """只在 owner event loop 内持有 Playwright 和 session 对象。"""

    def __init__(self, config: ServiceConfig, driver_factory: Callable[..., PlaywrightCdpDriver] = PlaywrightCdpDriver) -> None:
        self.config = config
        self.driver = driver_factory(config.artifacts_dir)
        self.sessions = SessionManager(config.sessions_file, self.driver)
        self.runs = RunService(config, self.sessions)
        self.operations = OperationService(
            config.operations_dir,
            config.token().encode("utf-8"),
            self._execute_operation,
        )
        self.knowledge: CanonicalStore | None = None
        self.retriever: HybridRetriever | None = None
        self.approvals: ApprovalService | None = None
        self.asset_executor: AssetExecutionService | None = None

    async def start(self) -> None:
        KnowledgeReset(self.config.state_root).ensure()
        self.knowledge = CanonicalStore(self.config.state_root)
        self.knowledge.verify()
        self.retriever = HybridRetriever(self.knowledge)
        self.approvals = ApprovalService(self.knowledge, self.runs)
        self.asset_executor = AssetExecutionService(self.knowledge, self.runs, self._record_outcome)
        await self.driver.start()
        await self.sessions.load()
        await self.runs.recover()
        self.operations.recover()

    async def stop(self) -> None:
        try:
            try:
                await self.operations.shutdown()
            finally:
                try:
                    await self.runs.abort_open()
                finally:
                    await self.sessions.shutdown()
        finally:
            try:
                await self.driver.stop()
            finally:
                if self.retriever is not None:
                    self.retriever.close()

    def _record_outcome(self, asset_id: str, succeeded: bool, verified_at: str) -> dict[str, Any]:
        if self.retriever is None:
            raise VerifierError("knowledge_index_unavailable", "derived index 暂不可用", status=503)
        return self.retriever.record_outcome(asset_id, succeeded, verified_at)

    async def dispatch(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "probe":
            return await self.driver.probe(str(payload.get("cdp") or ""), payload)
        if operation == "attach":
            if payload.get("allowRemoteCdp"):
                raise VerifierError("remote_cdp_not_approved", "本任务未批准 remote CDP")
            return await self.sessions.attach(payload)
        if operation == "sessions":
            return await self.sessions.list()
        if operation == "session_status":
            return await self.sessions.status(str(payload.get("session") or payload.get("name") or ""))
        if operation == "detach":
            return await self.sessions.detach(str(payload.get("session") or payload.get("name") or ""))
        if operation == "run_prepare":
            knowledge = None
            if payload.get("appId") and payload.get("goal"):
                assert self.retriever is not None
                knowledge = self.retriever.search(
                    str(payload["goal"]),
                    payload,
                    kind=str(payload["kind"]) if payload.get("kind") else None,
                    limit=3,
                )
            prepared = await self.runs.prepare(payload)
            if knowledge is not None:
                prepared["knowledge"] = knowledge
            return prepared
        if operation == "run_action":
            return self.operations.submit("action", payload)
        if operation == "run_workflow":
            return self.operations.submit("workflow", payload)
        if operation == "operation_get":
            return self.operations.get(str(payload.get("operationId") or ""))
        if operation == "operation_cancel":
            return await self.operations.cancel(str(payload.get("operationId") or ""))
        if operation == "risk_preview":
            asset_id = str(payload.get("assetId") or "")
            if asset_id:
                if payload.get("action") is not None:
                    raise VerifierError("risk_preview_invalid", "risk preview 的 action/assetId 只能提供一个")
                assert self.asset_executor is not None
                return self.asset_executor.preview_risk(
                    str(payload.get("runId") or ""),
                    asset_id,
                )
            return self.runs.preview_risk(
                str(payload.get("runId") or ""),
                payload.get("action"),
            )
        if operation == "risk_approve":
            return self.runs.approve_risk(
                str(payload.get("previewId") or ""),
                str(payload.get("fingerprint") or ""),
                str(payload.get("note") or ""),
            )
        if operation == "run_finalize":
            return await self.runs.finalize(str(payload.get("runId") or ""))
        if operation == "run_status":
            return {"ok": True, "run": self.runs.load(str(payload.get("runId") or ""))}
        if operation == "report_latest":
            return self.runs.latest_report(str(payload.get("session") or ""))
        if operation == "report_get":
            return self.runs.get_report(str(payload.get("path") or ""))
        if operation == "artifact_get":
            return self.runs.get_artifact(str(payload.get("path") or ""))
        if operation == "pending_preview":
            assert self.approvals is not None
            return {"ok": True, **self.approvals.validate(str(payload.get("runId") or ""))}
        if operation == "pending_approve":
            assert self.approvals is not None
            assert self.knowledge is not None
            if self.retriever is not None:
                self.retriever.close()
                self.retriever = None
            try:
                return self.approvals.approve(
                    str(payload.get("runId") or ""),
                    str(payload.get("fingerprint") or ""),
                    str(payload.get("note") or ""),
                )
            finally:
                self.knowledge.verify()
                self.retriever = HybridRetriever(self.knowledge)
        if operation == "pending_reject":
            assert self.approvals is not None
            return self.approvals.reject(
                str(payload.get("runId") or ""),
                str(payload.get("fingerprint") or ""),
                str(payload.get("reason") or ""),
            )
        if operation == "knowledge_verify":
            assert self.knowledge is not None
            return {"ok": True, **self.knowledge.verify()}
        if operation == "knowledge_rebuild":
            assert self.knowledge is not None
            if self.retriever is not None:
                self.retriever.close()
                self.retriever = None
            try:
                rebuilt = self.knowledge.rebuild_index()
            finally:
                self.retriever = HybridRetriever(self.knowledge)
            return {"ok": True, **rebuilt}
        if operation == "knowledge_search":
            assert self.retriever is not None
            return self.retriever.search(
                str(payload.get("query") or payload.get("goal") or ""),
                payload,
                kind=str(payload["kind"]) if payload.get("kind") else None,
                limit=_integer_option(payload.get("limit"), 3, "limit"),
                min_score=_float_option(payload.get("minScore"), DEFAULT_MIN_SCORE, "minScore"),
                min_margin=_float_option(payload.get("minMargin"), DEFAULT_MIN_MARGIN, "minMargin"),
                explain=payload.get("explain") is True,
            )
        if operation == "knowledge_compose":
            assert self.retriever is not None
            return self.retriever.compose(payload)
        if operation == "knowledge_asset_get":
            assert self.retriever is not None
            return self.retriever.get_asset(str(payload.get("assetId") or ""))
        if operation == "knowledge_assets":
            assert self.retriever is not None
            return self.retriever.list_assets(
                str(payload["appId"]) if payload.get("appId") else None,
                str(payload["kind"]) if payload.get("kind") else None,
                _integer_option(payload.get("limit"), 50, "limit"),
            )
        if operation == "knowledge_stats":
            assert self.retriever is not None
            return self.retriever.stats()
        raise VerifierError("operation_not_found", f"未知 automation operation：{operation}", status=404)

    async def _execute_operation(
        self,
        kind: str,
        payload: dict[str, Any],
        context: OperationContext,
    ) -> dict[str, Any]:
        if kind == "action":
            if payload.get("assetId"):
                assert self.asset_executor is not None
                return await self.asset_executor.execute_action(
                    str(payload.get("runId") or ""),
                    str(payload["assetId"]),
                    payload.get("bindings"),
                    str(payload["riskReceipt"]) if payload.get("riskReceipt") else None,
                    context,
                )
            return await self.runs.append_action(
                str(payload.get("runId") or ""),
                payload.get("action"),
                payload.get("bindings"),
                payload.get("parameterSchema"),
                str(payload["riskReceipt"]) if payload.get("riskReceipt") else None,
                operation_context=context,
            )
        if kind == "workflow":
            if payload.get("assetId"):
                assert self.asset_executor is not None
                return await self.asset_executor.execute_workflow(
                    str(payload.get("runId") or ""),
                    str(payload["assetId"]),
                    payload.get("bindings"),
                    payload.get("riskReceipts"),
                    payload.get("autoFinalize", True) is not False,
                    context,
                )
            return await self.runs.execute_workflow(
                str(payload.get("runId") or ""),
                payload.get("workflow"),
                auto_finalize=payload.get("autoFinalize", True) is not False,
                bindings=payload.get("bindings"),
                risk_receipts=payload.get("riskReceipts"),
                operation_context=context,
            )
        raise VerifierError("operation_kind_invalid", f"不支持的 operation kind：{kind}")


class AutomationWorker:
    """HTTP 线程通过此边界提交命令，Playwright handle 永不越过线程。"""

    def __init__(
        self,
        config: ServiceConfig,
        *,
        limits: RuntimeLimits = DEFAULT_LIMITS,
        runtime_factory: Callable[[ServiceConfig], AutomationRuntime] = AutomationRuntime,
    ) -> None:
        self.config = config
        self.limits = limits
        self.runtime_factory = runtime_factory
        self._thread = threading.Thread(target=self._thread_main, name="electron-verifier-automation", daemon=False)
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[_Command] | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._startup_error: BaseException | None = None
        self._shutdown_error: BaseException | None = None
        self._closing = False

    def start(self, timeout: float | None = None) -> None:
        wait_timeout = self.limits.automation_start_timeout_seconds if timeout is None else timeout
        self._thread.start()
        if not self._ready.wait(wait_timeout):
            self._closing = True
            if self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(self._cancel_startup)
                except RuntimeError:
                    # 超时边界上 worker 可能已自行关闭 event loop。
                    pass
            self._thread.join(timeout=self.limits.shutdown_grace_seconds)
            raise VerifierError(
                "automation_start_timeout",
                "automation worker 启动超时",
                status=503,
                details={
                    "timeoutSeconds": wait_timeout,
                    "cleanupCompleted": not self._thread.is_alive(),
                },
            )
        if self._startup_error is not None:
            cleanup = f"；cleanup 失败：{self._shutdown_error}" if self._shutdown_error is not None else ""
            raise VerifierError("automation_start_failed", f"automation worker 启动失败：{self._startup_error}{cleanup}", status=503)

    def _cancel_startup(self) -> None:
        if self._startup_task is not None and not self._startup_task.done():
            self._startup_task.cancel()
            return
        if self._queue is not None:
            future: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()
            self._enqueue(_Command("__shutdown__", {}, future))

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._queue = asyncio.Queue(maxsize=self.limits.command_queue_size)
        runtime = self.runtime_factory(self.config)
        self._startup_task = loop.create_task(runtime.start())
        try:
            loop.run_until_complete(self._startup_task)
        except BaseException as exc:
            self._startup_error = exc
            try:
                loop.run_until_complete(runtime.stop())
            except BaseException as cleanup_exc:
                self._shutdown_error = cleanup_exc
            self._ready.set()
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            return
        finally:
            self._startup_task = None
        self._ready.set()
        try:
            if not self._closing:
                loop.run_until_complete(self._consume(runtime))
        except BaseException as exc:
            self._shutdown_error = exc
        finally:
            try:
                loop.run_until_complete(runtime.stop())
            except BaseException as exc:
                self._shutdown_error = self._shutdown_error or exc
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

    async def _consume(self, runtime: AutomationRuntime) -> None:
        assert self._queue is not None
        while True:
            command = await self._queue.get()
            try:
                if command.operation == "__shutdown__":
                    if not command.future.cancelled():
                        command.future.set_result({"ok": True})
                    return
                if command.future.cancelled():
                    continue
                result = await runtime.dispatch(command.operation, command.payload)
                if not command.future.cancelled():
                    command.future.set_result(result)
            except BaseException as exc:
                if not command.future.cancelled():
                    command.future.set_exception(exc)
            finally:
                self._queue.task_done()

    def _enqueue(self, command: _Command) -> None:
        if self._queue is None or self._closing and command.operation != "__shutdown__":
            command.future.set_exception(VerifierError("automation_stopping", "automation worker 正在停止", status=503))
            return
        if self._queue.full():
            command.future.set_exception(VerifierError("automation_queue_full", "automation command queue 已满", status=503))
            return
        self._queue.put_nowait(command)

    def submit(self, operation: str, payload: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:
        if self._loop is None or not self._thread.is_alive():
            raise VerifierError("automation_unavailable", "automation worker 不可用", status=503)
        future: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._enqueue, _Command(operation, payload, future))
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise VerifierError(
                "operation_timeout",
                f"automation operation 超时：{operation}",
                status=504,
                details={"outcome": "unknown"},
            ) from exc

    def shutdown(self, timeout: float | None = None) -> None:
        if not self._thread.is_alive() or self._loop is None:
            if self._shutdown_error is not None:
                raise VerifierError(
                    "automation_shutdown_failed",
                    f"automation worker cleanup 失败：{self._shutdown_error}",
                    status=500,
                )
            return
        self._closing = True
        future: concurrent.futures.Future[dict[str, Any]] = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._enqueue, _Command("__shutdown__", {}, future))
        grace = timeout if timeout is not None else self.limits.shutdown_grace_seconds
        try:
            future.result(timeout=grace)
        except (concurrent.futures.TimeoutError, BaseException):
            pass
        self._thread.join(timeout=grace)
        if self._thread.is_alive():
            raise VerifierError("automation_shutdown_timeout", "automation worker 未在 grace 内停止", status=500)
        if self._shutdown_error is not None:
            raise VerifierError(
                "automation_shutdown_failed",
                f"automation worker cleanup 失败：{self._shutdown_error}",
                status=500,
            )

    def stats(self) -> dict[str, Any]:
        size = self._queue.qsize() if self._queue is not None else 0
        return {"ownerAlive": self._thread.is_alive(), "queueSize": size, "queueLimit": self.limits.command_queue_size}
