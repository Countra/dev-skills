"""Run UUID、journal、finalize 幂等和 crash recovery 测试。"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _helpers import TestTemporaryDirectory  # noqa: E402
from electron_verifier.actions import ActionExecution  # noqa: E402
from electron_verifier.errors import VerifierError  # noqa: E402
from electron_verifier.evidence import PendingArtifact  # noqa: E402
from electron_verifier.runs import RunService  # noqa: E402
from electron_verifier.operations import OperationContext  # noqa: E402


TEST_ROOT = Path(os.environ.get("EV_TEST_ROOT", Path.cwd() / ".harness" / "electron-ui-verifier-test-tmp"))


class FakeSessions:
    def __init__(self) -> None:
        self.driver = SimpleNamespace(live=lambda session_id: SimpleNamespace(page=object()))

    async def status(self, value: str) -> dict:
        return {
            "ok": True,
            "connected": True,
            "session": {"sessionId": "session-1", "name": "demo", "status": "connected", "targetTitle": "Demo"},
        }

    def intent(self, value: str):
        return SimpleNamespace(session_id="session-1")


def service_config(root: Path):
    return SimpleNamespace(
        state_root=root,
        runs_dir=root / "runs",
        pending_dir=root / "pending",
    )


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_twenty_actions_are_unique_and_finalize_is_idempotent(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(
                service.prepare(
                    {
                        "session": "demo",
                        "appId": "demo",
                        "appVersion": "1.0.0",
                        "screenDigest": "screen-main",
                        "preState": "home",
                        "goal": "保存设置",
                    }
                )
            )
            counter = 0

            async def fake_execute(live, action):
                nonlocal counter
                counter += 1
                return ActionExecution(
                    result={"action": "click", "postconditions": [{"passed": True}]},
                    artifacts=[PendingArtifact("application/json", f'{{"index":{counter}}}'.encode(), "event", "json")],
                )

            raw_action = {
                "id": "same-label",
                "type": "click",
                "locator": {"role": "button", "accessibleName": "保存"},
                "postconditions": [{"type": "visible", "locator": {"text": "已保存"}}],
            }
            with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
                for _ in range(20):
                    result = asyncio.run(service.append_action(prepared["runId"], raw_action))
                    self.assertTrue(result["ok"])
            first = asyncio.run(service.finalize(prepared["runId"]))
            second = asyncio.run(service.finalize(prepared["runId"]))
            journal = service.load(prepared["runId"])
            manifest = json.loads(
                (root / "runs" / prepared["runId"] / "evidence-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(20, len({step["stepId"] for step in journal["steps"]}))
            self.assertEqual(20, len({item["artifactId"] for item in manifest["artifacts"]}))
            self.assertEqual(first["report"], second["report"])
            self.assertEqual(first["pending"], second["pending"])
            self.assertEqual(1, len(list((root / "pending" / prepared["runId"]).glob("pending.json"))))

    def test_recovery_marks_inflight_step_unknown_and_aborts(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(service.prepare({"session": "demo"}))
            journal = service.load(prepared["runId"])
            journal["state"] = "running"
            journal["steps"].append({"stepId": "inflight", "status": "running", "action": {"type": "click"}})
            service._save(journal)
            result = asyncio.run(service.recover())
            recovered = service.load(prepared["runId"])
            self.assertEqual([prepared["runId"]], result["recovered"])
            self.assertEqual("aborted", recovered["state"])
            self.assertEqual("unknown", recovered["steps"][0]["status"])

    def test_independent_diagnostic_failure_does_not_skip_next_diagnostic(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(service.prepare({"session": "demo"}))

            async def fake_execute(live, action):
                if action.action_type == "collectConsole":
                    raise VerifierError("diagnostic_unavailable", "console unavailable")
                return ActionExecution(result={"action": action.action_type, "eventCount": 0})

            workflow = {
                "goal": "diagnostics",
                "steps": [
                    {"type": "collectConsole", "options": {}, "continueOnFailure": True},
                    {"type": "collectNetwork", "options": {}, "continueOnFailure": True},
                ],
            }
            with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
                result = asyncio.run(service.execute_workflow(prepared["runId"], workflow, auto_finalize=False))
            self.assertFalse(result["ok"])
            self.assertEqual(["failed", "passed"], [step["status"] for step in result["steps"]])

    def test_workflow_parameter_schema_is_adopted_without_persisting_binding_value(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(service.prepare({"session": "demo", "appId": "demo"}))
            workflow = {
                "appId": "demo",
                "goal": "填写名称",
                "parameterSchema": {"name": {"type": "string", "required": True}},
                "steps": [
                    {
                        "type": "fill",
                        "locator": {"label": "名称"},
                        "value": "${name}",
                        "postconditions": [{"type": "value", "locator": {"label": "名称"}, "expected": "${name}"}],
                    }
                ],
            }

            async def fake_execute(live, action):
                self.assertEqual("private-value", action.value)
                return ActionExecution(result={"action": "fill", "postconditions": [{"passed": True}]})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
                result = asyncio.run(
                    service.execute_workflow(prepared["runId"], workflow, auto_finalize=False, bindings={"name": "private-value"})
                )
            journal = service.load(prepared["runId"])
            self.assertTrue(result["ok"])
            self.assertEqual(["name"], journal["steps"][0]["boundParameters"])
            self.assertIn("${name}", json.dumps(journal, ensure_ascii=False))
            self.assertNotIn("private-value", json.dumps(journal, ensure_ascii=False))

    def test_action_asset_parameter_schema_is_adopted_before_binding(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(service.prepare({"session": "demo", "appId": "demo"}))
            action = {
                "type": "fill",
                "locator": {"label": "名称"},
                "value": "${name}",
                "postconditions": [{"type": "value", "locator": {"label": "名称"}, "expected": "${name}"}],
            }

            async def fake_execute(live, decoded):
                self.assertEqual("private-value", decoded.value)
                return ActionExecution(result={"action": "fill", "postconditions": [{"passed": True}]})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
                result = asyncio.run(
                    service.append_action(
                        prepared["runId"],
                        action,
                        {"name": "private-value"},
                        {"name": {"type": "string", "required": True}},
                    )
                )
            journal = service.load(prepared["runId"])
            self.assertTrue(result["ok"])
            self.assertIn("name", journal["parameterSchema"])
            self.assertNotIn("private-value", json.dumps(journal, ensure_ascii=False))

    def test_sensitive_value_is_removed_from_results_errors_and_text_artifacts(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(
                service.prepare(
                    {
                        "session": "demo",
                        "appId": "demo",
                        "parameterSchema": {"secret": {"type": "string"}},
                    }
                )
            )
            sentinel = "SENTINEL-run-secret-551"
            action = {
                "type": "fill",
                "locator": {"label": "密码"},
                "value": "${secret}",
                "postconditions": [
                    {"type": "value", "locator": {"label": "密码"}, "expected": "${secret}"}
                ],
            }

            async def successful_execute(live, decoded):
                self.assertEqual(sentinel, decoded.value)
                return ActionExecution(
                    result={"action": "fill", "echo": sentinel, "postconditions": [{"passed": True}]},
                    artifacts=[
                        PendingArtifact(
                            "application/json",
                            json.dumps({"echo": sentinel}).encode(),
                            f"event-{sentinel}",
                            "json",
                        )
                    ],
                )

            with mock.patch("electron_verifier.runs.execute_action", side_effect=successful_execute):
                response = asyncio.run(
                    service.append_action(prepared["runId"], action, bindings={"secret": sentinel})
                )
            self.assertNotIn(sentinel, json.dumps(response, ensure_ascii=False))

            async def failing_execute(live, decoded):
                raise VerifierError("action_failed", f"输入失败：{sentinel}", details={"echo": sentinel})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=failing_execute):
                failed = asyncio.run(
                    service.append_action(prepared["runId"], action, bindings={"secret": sentinel})
                )
            self.assertNotIn(sentinel, json.dumps(failed, ensure_ascii=False))

            direct_action = {
                "type": "waitUrlContains",
                "value": sentinel,
                "postconditions": [{"type": "titleContains", "expected": sentinel}],
            }

            async def direct_execute(live, decoded):
                return ActionExecution(result={"action": "waitUrlContains", "echo": sentinel})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=direct_execute):
                direct = asyncio.run(service.append_action(prepared["runId"], direct_action))
            self.assertNotIn(sentinel, json.dumps(direct, ensure_ascii=False))
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(sentinel.encode(), path.read_bytes(), msg=str(path))

    def test_risky_mutation_requires_and_consumes_one_receipt(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(service.prepare({"session": "demo", "appId": "demo"}))
            action = {
                "type": "click",
                "locator": {"role": "button", "accessibleName": "删除", "nth": 0},
                "postconditions": [{"type": "hidden", "locator": {"text": "待删除"}}],
            }
            mutation_count = 0

            async def fake_execute(live, decoded):
                nonlocal mutation_count
                mutation_count += 1
                return ActionExecution(result={"action": "click", "postconditions": [{"passed": True}]})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=fake_execute):
                with self.assertRaises(VerifierError) as missing:
                    asyncio.run(service.append_action(prepared["runId"], action))
                self.assertEqual("risk_authorization_required", missing.exception.code)
                self.assertEqual(0, mutation_count)

                preview = service.preview_risk(prepared["runId"], action)
                receipt = service.approve_risk(preview["previewId"], preview["fingerprint"], "确认测试删除动作")
                passed = asyncio.run(
                    service.append_action(prepared["runId"], action, risk_receipt=receipt["receiptId"])
                )
                self.assertTrue(passed["ok"])
                self.assertEqual(1, mutation_count)

                with self.assertRaises(VerifierError) as replayed:
                    asyncio.run(
                        service.append_action(prepared["runId"], action, risk_receipt=receipt["receiptId"])
                    )
                self.assertEqual("risk_authorization_consumed", replayed.exception.code)
                self.assertEqual(1, mutation_count)

    def test_restart_rebuilds_sensitive_mask_from_stable_locator(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            first_service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(
                first_service.prepare(
                    {
                        "session": "demo",
                        "appId": "demo",
                        "parameterSchema": {"secret": {"type": "string"}},
                    }
                )
            )
            fill = {
                "type": "fill",
                "locator": {"label": "密码"},
                "value": "${secret}",
                "postconditions": [
                    {"type": "value", "locator": {"label": "密码"}, "expected": "${secret}"}
                ],
            }

            async def fill_execute(live, decoded):
                return ActionExecution(result={"action": "fill", "postconditions": [{"passed": True}]})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=fill_execute):
                asyncio.run(
                    first_service.append_action(
                        prepared["runId"],
                        fill,
                        bindings={"secret": "restart-secret"},
                    )
                )

            restarted_service = RunService(service_config(root), FakeSessions())

            async def screenshot_execute(live, decoded, *, sensitive_masks):
                self.assertEqual(1, len(sensitive_masks))
                self.assertEqual("label", sensitive_masks[0].strategy)
                return ActionExecution(result={"action": "screenshot", "maskedLocatorCount": 1})

            with mock.patch("electron_verifier.runs.execute_action", side_effect=screenshot_execute):
                result = asyncio.run(
                    restarted_service.append_action(prepared["runId"], {"type": "screenshot"})
                )
            self.assertTrue(result["ok"])

    def test_operation_cancel_aborts_run_and_stops_later_mutations(self) -> None:
        with TestTemporaryDirectory(dir=TEST_ROOT) as folder:
            root = Path(folder)
            service = RunService(service_config(root), FakeSessions())
            prepared = asyncio.run(service.prepare({"session": "demo", "appId": "demo"}))
            mutation_count = 0

            async def scenario() -> None:
                nonlocal mutation_count
                started = asyncio.Event()

                async def blocking_execute(live, action):
                    nonlocal mutation_count
                    mutation_count += 1
                    started.set()
                    await asyncio.sleep(30)

                workflow = {
                    "steps": [
                        {
                            "type": "click",
                            "locator": {"text": f"保存-{index}"},
                            "postconditions": [{"type": "visible", "locator": {"text": "完成"}}],
                        }
                        for index in range(3)
                    ]
                }
                context = OperationContext(str(uuid.uuid4()), 5_000)
                with mock.patch("electron_verifier.runs.execute_action", side_effect=blocking_execute):
                    task = asyncio.create_task(
                        service.execute_workflow(
                            prepared["runId"],
                            workflow,
                            auto_finalize=False,
                            operation_context=context,
                        )
                    )
                    await asyncio.wait_for(started.wait(), timeout=1)
                    context.request_cancel()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

            asyncio.run(scenario())
            journal = service.load(prepared["runId"])
            self.assertEqual(1, mutation_count)
            self.assertEqual("aborted", journal["state"])
            self.assertEqual("unknown", journal["steps"][0]["status"])
            self.assertEqual(1, len(journal["steps"]))


if __name__ == "__main__":
    unittest.main()
