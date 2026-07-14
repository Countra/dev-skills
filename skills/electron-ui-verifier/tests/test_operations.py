"""Durable operation 幂等、取消、deadline 与恢复测试。"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.operations import FINAL_STATES, OperationService, OperationStore  # noqa: E402
from ev_common import wait_for_operation  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


async def wait_final(service: OperationService, operation_id: str) -> dict:
    for _ in range(500):
        operation = service.get(operation_id)["operation"]
        if operation["state"] in FINAL_STATES:
            return operation
        await asyncio.sleep(0.002)
    raise AssertionError("operation 未在测试期限内收敛")


def payload(request_id: str, value: str = "value", deadline_ms: int = 5_000) -> dict:
    return {
        "requestId": request_id,
        "deadlineMs": deadline_ms,
        "runId": str(uuid.uuid4()),
        "action": {"type": "waitText", "value": value},
        "bindings": {"secret": value},
    }


class OperationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    async def test_request_id_is_idempotent_and_secret_is_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)

            async def executor(kind, submitted, context):
                return {"ok": True, "runId": submitted["runId"]}

            service = OperationService(root, b"test-secret", executor)
            request_id = str(uuid.uuid4())
            sentinel = "SENTINEL-operation-binding-22"
            submitted_payload = payload(request_id, sentinel)
            first = service.submit("action", submitted_payload)
            second = service.submit("action", submitted_payload)
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(first["operation"]["operationId"], second["operation"]["operationId"])
            await wait_final(service, first["operation"]["operationId"])
            persisted = b"".join(path.read_bytes() for path in root.rglob("*") if path.is_file())
            self.assertNotIn(sentinel.encode(), persisted)

            with self.assertRaises(VerifierError) as caught:
                service.submit("action", payload(request_id, "changed"))
            self.assertEqual("operation_request_conflict", caught.exception.code)
            await service.shutdown()

    async def test_asset_submission_is_id_only_and_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            seen = []

            async def executor(kind, submitted, context):
                seen.append(dict(submitted))
                return {"ok": True}

            service = OperationService(Path(folder), b"test-secret", executor)
            base = {
                "requestId": str(uuid.uuid4()),
                "runId": str(uuid.uuid4()),
                "assetId": "action-" + "a" * 40,
            }
            submitted = service.submit("action", base)
            terminal = await wait_final(service, submitted["operation"]["operationId"])
            self.assertEqual("succeeded", terminal["state"])
            self.assertEqual(base["assetId"], terminal["assetId"])
            self.assertNotIn("action", seen[0])
            with self.assertRaises(VerifierError) as both:
                service.submit(
                    "action",
                    {**base, "requestId": str(uuid.uuid4()), "action": {"type": "snapshot"}},
                )
            self.assertEqual("operation_request_invalid", both.exception.code)
            with self.assertRaises(VerifierError) as client_schema:
                service.submit(
                    "action",
                    {**base, "requestId": str(uuid.uuid4()), "parameterSchema": {"value": {}}},
                )
            self.assertEqual("operation_request_invalid", client_schema.exception.code)
            await service.shutdown()

    async def test_queued_cancel_never_calls_executor(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            release = asyncio.Event()
            calls: list[str] = []

            async def executor(kind, submitted, context):
                calls.append(submitted["action"]["value"])
                await release.wait()
                return {"ok": True}

            service = OperationService(Path(folder), b"test-secret", executor)
            first = service.submit("action", payload(str(uuid.uuid4()), "first"))
            second = service.submit("action", payload(str(uuid.uuid4()), "second"))
            await asyncio.sleep(0.02)
            cancelled = await service.cancel(second["operation"]["operationId"])
            self.assertEqual("cancelled", cancelled["operation"]["state"])
            self.assertEqual(["first"], calls)
            release.set()
            await wait_final(service, first["operation"]["operationId"])
            self.assertEqual(["first"], calls)
            await service.shutdown()

    async def test_running_cancel_marks_unknown_and_stops_later_mutations(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            started = asyncio.Event()
            mutation_count = 0

            async def executor(kind, submitted, context):
                nonlocal mutation_count
                for _ in range(3):
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

            service = OperationService(Path(folder), b"test-secret", executor)
            submitted = service.submit("action", payload(str(uuid.uuid4()), "running"))
            await asyncio.wait_for(started.wait(), timeout=1)
            cancelled = await service.cancel(submitted["operation"]["operationId"])
            self.assertEqual("unknown", cancelled["operation"]["state"])
            self.assertEqual("unknown", cancelled["operation"]["error"]["outcome"])
            await asyncio.sleep(0.02)
            self.assertEqual(1, mutation_count)
            await service.shutdown()

    async def test_deadline_distinguishes_known_and_unknown_outcomes(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            mutation_started = asyncio.Event()

            async def executor(kind, submitted, context):
                context.begin_mutation()
                mutation_started.set()
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    context.mark_outcome_unknown()
                    raise
                finally:
                    context.end_mutation()

            service = OperationService(Path(folder), b"test-secret", executor)
            submitted = service.submit("action", payload(str(uuid.uuid4()), deadline_ms=500))
            await asyncio.wait_for(mutation_started.wait(), timeout=1)
            operation = await wait_final(service, submitted["operation"]["operationId"])
            self.assertEqual("unknown", operation["state"])
            self.assertEqual("operation_deadline_exceeded", operation["error"]["code"])
            await service.shutdown()

    async def test_queued_deadline_expires_without_executor_call(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            release = asyncio.Event()
            calls: list[str] = []

            async def executor(kind, submitted, context):
                calls.append(submitted["action"]["value"])
                await release.wait()
                return {"ok": True}

            service = OperationService(Path(folder), b"test-secret", executor)
            first = service.submit("action", payload(str(uuid.uuid4()), "first"))
            second = service.submit(
                "action",
                payload(str(uuid.uuid4()), "deadline-queued", deadline_ms=100),
            )
            expired = await wait_final(service, second["operation"]["operationId"])
            self.assertEqual("deadline_exceeded", expired["state"])
            self.assertEqual(["first"], calls)
            release.set()
            await wait_final(service, first["operation"]["operationId"])
            await service.shutdown()

    async def test_client_wait_timeout_does_not_request_cancel(self) -> None:
        running = {
            "ok": True,
            "operation": {
                "operationId": str(uuid.uuid4()),
                "state": "running",
                "cancelRequested": False,
            },
        }
        with mock.patch("ev_common.request_json", return_value=running) as request:
            result = await asyncio.to_thread(
                wait_for_operation,
                object(),
                running["operation"]["operationId"],
                0.01,
                0.002,
            )
        self.assertEqual("operation_wait_timeout", result["code"])
        self.assertFalse(result["operation"]["cancelRequested"])
        self.assertGreaterEqual(request.call_count, 1)

    async def test_recovery_never_replays_open_operations(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            store = OperationStore(root, b"test-secret")
            queued, _ = store.create("action", payload(str(uuid.uuid4())), 5_000)
            running, _ = store.create("action", payload(str(uuid.uuid4())), 5_000)
            store.transition(running["operationId"], "running")
            calls = 0

            async def executor(kind, submitted, context):
                nonlocal calls
                calls += 1
                return {"ok": True}

            service = OperationService(root, b"test-secret", executor)
            recovered = service.recover()
            self.assertCountEqual(
                [queued["operationId"], running["operationId"]],
                recovered["recovered"],
            )
            self.assertEqual("cancelled", service.get(queued["operationId"])["operation"]["state"])
            self.assertEqual("unknown", service.get(running["operationId"])["operation"]["state"])
            self.assertEqual(0, calls)
            await service.shutdown()


if __name__ == "__main__":
    unittest.main()
