"""单 owner automation worker 的并发边界测试。"""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.automation import AutomationRuntime, AutomationWorker, _float_option, _integer_option  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.limits import RuntimeLimits  # noqa: E402


class FakeRuntime:
    owner_threads: list[int] = []

    def __init__(self, config) -> None:
        self.config = config

    async def start(self) -> None:
        self.owner_threads.append(threading.get_ident())

    async def stop(self) -> None:
        self.owner_threads.append(threading.get_ident())

    async def dispatch(self, operation: str, payload: dict) -> dict:
        self.owner_threads.append(threading.get_ident())
        if operation == "slow":
            await asyncio.sleep(0.05)
        return {"ok": True, "operation": operation, "value": payload.get("value")}


class AutomationWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeRuntime.owner_threads = []
        self.worker = AutomationWorker(
            object(),
            limits=RuntimeLimits(command_queue_size=2, shutdown_grace_seconds=1.0),
            runtime_factory=FakeRuntime,
        )
        self.worker.start()

    def tearDown(self) -> None:
        self.worker.shutdown()

    def test_all_runtime_calls_stay_on_one_owner_thread(self) -> None:
        first = self.worker.submit("echo", {"value": 1})
        second = self.worker.submit("echo", {"value": 2})
        self.assertEqual(1, first["value"])
        self.assertEqual(2, second["value"])
        self.assertEqual(1, len(set(FakeRuntime.owner_threads)))
        self.assertNotEqual(threading.get_ident(), FakeRuntime.owner_threads[0])

    def test_timeout_is_reported_as_unknown_outcome(self) -> None:
        with self.assertRaises(VerifierError) as caught:
            self.worker.submit("slow", {}, timeout=0.005)
        self.assertEqual("operation_timeout", caught.exception.code)
        self.assertEqual("unknown", caught.exception.details["outcome"])

    def test_invalid_numeric_options_return_stable_error(self) -> None:
        with self.assertRaises(VerifierError) as integer_error:
            _integer_option("many", 3, "limit")
        with self.assertRaises(VerifierError) as float_error:
            _float_option({}, 0.5, "minScore")
        self.assertEqual("invalid_operation_option", integer_error.exception.code)
        self.assertEqual("invalid_operation_option", float_error.exception.code)

    def test_prepare_validates_knowledge_before_creating_run(self) -> None:
        class RejectingRetriever:
            def search(self, *args, **kwargs):
                raise VerifierError("invalid_retrieval_context", "invalid")

        class FakeRuns:
            calls = 0

            async def prepare(self, payload):
                self.calls += 1
                return {"ok": True}

        runtime = object.__new__(AutomationRuntime)
        runtime.retriever = RejectingRetriever()
        runtime.runs = FakeRuns()
        with self.assertRaises(VerifierError):
            asyncio.run(runtime.dispatch("run_prepare", {"appId": "demo", "goal": "test"}))
        self.assertEqual(0, runtime.runs.calls)

    def test_startup_failure_still_runs_runtime_cleanup(self) -> None:
        class StartupFailureRuntime:
            stopped = False

            def __init__(self, config) -> None:
                pass

            async def start(self) -> None:
                raise RuntimeError("start failed")

            async def stop(self) -> None:
                self.__class__.stopped = True

        worker = AutomationWorker(object(), runtime_factory=StartupFailureRuntime)
        with self.assertRaises(VerifierError) as caught:
            worker.start()
        self.assertEqual("automation_start_failed", caught.exception.code)
        self.assertTrue(StartupFailureRuntime.stopped)

    def test_startup_timeout_cancels_worker_and_runs_cleanup(self) -> None:
        class BlockingStartupRuntime:
            stopped = threading.Event()

            def __init__(self, config) -> None:
                pass

            async def start(self) -> None:
                await asyncio.Event().wait()

            async def stop(self) -> None:
                self.__class__.stopped.set()

        limits = RuntimeLimits(
            automation_start_timeout_seconds=0.02,
            readiness_timeout_margin_seconds=0.03,
            shutdown_grace_seconds=1.0,
        )
        worker = AutomationWorker(object(), limits=limits, runtime_factory=BlockingStartupRuntime)

        with self.assertRaises(VerifierError) as caught:
            worker.start()

        self.assertEqual("automation_start_timeout", caught.exception.code)
        self.assertEqual(0.02, caught.exception.details["timeoutSeconds"])
        self.assertTrue(caught.exception.details["cleanupCompleted"])
        self.assertTrue(BlockingStartupRuntime.stopped.is_set())
        self.assertFalse(worker._thread.is_alive())
        self.assertAlmostEqual(0.05, limits.service_readiness_timeout_seconds)

    def test_default_start_timeout_comes_from_runtime_limits(self) -> None:
        limits = RuntimeLimits(automation_start_timeout_seconds=12.5, shutdown_grace_seconds=1.0)
        worker = AutomationWorker(object(), limits=limits, runtime_factory=FakeRuntime)

        with mock.patch.object(worker._ready, "wait", wraps=worker._ready.wait) as wait:
            worker.start()
        worker.shutdown()

        wait.assert_called_once_with(12.5)

    def test_timeout_boundary_stops_worker_that_just_became_ready(self) -> None:
        limits = RuntimeLimits(automation_start_timeout_seconds=1.0, shutdown_grace_seconds=1.0)
        worker = AutomationWorker(object(), limits=limits, runtime_factory=FakeRuntime)
        real_wait = worker._ready.wait

        def lose_timeout_race(timeout: float) -> bool:
            self.assertTrue(real_wait(timeout))
            return False

        with (
            mock.patch.object(worker._ready, "wait", side_effect=lose_timeout_race),
            self.assertRaises(VerifierError) as caught,
        ):
            worker.start()

        self.assertEqual("automation_start_timeout", caught.exception.code)
        self.assertTrue(caught.exception.details["cleanupCompleted"])
        self.assertFalse(worker._thread.is_alive())

    def test_shutdown_cleanup_failure_is_reported(self) -> None:
        class ShutdownFailureRuntime(FakeRuntime):
            async def stop(self) -> None:
                raise RuntimeError("stop failed")

        worker = AutomationWorker(object(), runtime_factory=ShutdownFailureRuntime)
        worker.start()
        with self.assertRaises(VerifierError) as caught:
            worker.shutdown()
        self.assertEqual("automation_shutdown_failed", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
