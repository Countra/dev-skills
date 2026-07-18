"""公共契约 fixture 的 process-manager 参数边界测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import public_contract_support as support
from public_contract_support import HARNESS_ROOT, ManagedVerifier


class ManagedVerifierCommandTests(unittest.TestCase):
    def test_service_validation_uses_fixture_manager_config(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        service_file = (
            managed.workspace
            / ".harness"
            / "process-manager"
            / "services"
            / "sample.json"
        )

        with mock.patch.object(managed, "_pm", return_value={"ok": True}) as invoke:
            result = managed._validate_service(service_file)

        self.assertEqual({"ok": True}, result)
        invoke.assert_called_once_with(
            "pm_validate.py",
            "--config",
            str(managed.manager_config),
            "--service",
            str(service_file),
            "--pretty",
        )

    def test_readiness_timeout_comes_from_service_contract(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        service_file = mock.Mock()
        service_file.read_text.return_value = '{"readiness":{"timeoutSeconds":75}}'

        timeout = managed._service_readiness_timeout(service_file)

        self.assertEqual(75.0, timeout)
        service_file.read_text.assert_called_once_with(encoding="utf-8")

    def test_log_tail_is_bounded_and_workspace_scoped(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        log_file = managed.workspace / "logs" / "stderr.log"

        with mock.patch("pathlib.Path.read_text", return_value="abcdef"):
            tail = managed._log_tail(str(log_file), limit=4)

        self.assertEqual("cdef", tail)
        self.assertEqual(
            "[workspace 外日志已忽略]",
            managed._log_tail(str(HARNESS_ROOT / "outside.log")),
        )

    def test_extra_service_requires_and_inherits_validation_session(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        service_file = managed.workspace / "service.json"
        with self.assertRaises(RuntimeError):
            managed.start_managed_service(service_file)

        managed.session_id = "1" * 32
        responses = (
            {"data": {"processKey": "demo.run-1"}},
            {"data": {"ready": True}},
        )
        with (
            mock.patch.object(managed, "_validate_service"),
            mock.patch.object(managed, "_service_readiness_timeout", return_value=30),
            mock.patch.object(managed, "_pm", side_effect=responses) as invoke,
        ):
            result = managed.start_managed_service(service_file)

        self.assertEqual(result["processKey"], "demo.run-1")
        start_call = invoke.call_args_list[0]
        self.assertIn("--session-id", start_call.args)
        index = start_call.args.index("--session-id")
        self.assertEqual(start_call.args[index + 1], managed.session_id)

    def test_session_renew_is_explicit_and_context_bound(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        managed.session_id = "2" * 32
        with mock.patch.object(
            managed,
            "_pm",
            return_value={"data": {"sessionId": managed.session_id, "state": "open"}},
        ) as invoke:
            renewed = managed.renew_session(ttl_seconds=900)

        self.assertEqual(renewed["sessionId"], managed.session_id)
        invoke.assert_called_once_with(
            "pm_session.py",
            "renew",
            "--config",
            str(managed.manager_config),
            "--session-id",
            managed.session_id,
            "--ttl-seconds",
            "900",
            "--pretty",
        )

    def test_stop_falls_back_to_confirmed_manager_cleanup_when_session_close_fails(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        managed.manager_ensured = True
        managed.session_id = "3" * 32
        manager_stop = {
            "data": {
                "cleanup": {
                    "managerStopped": True,
                    "bootstrapCleaned": True,
                    "ownersEmpty": True,
                }
            }
        }
        with mock.patch.object(
            managed,
            "_pm",
            side_effect=(RuntimeError("close failed"), manager_stop),
        ) as invoke:
            checks, failures = managed.stop()

        self.assertIn("validation session close 失败", failures[0])
        self.assertEqual(checks["managerStopFallback"], manager_stop["data"])
        self.assertIsNone(managed.session_id)
        self.assertIn("--confirm-stop-owned-runs", invoke.call_args_list[1].args)

    def test_start_marks_manager_for_cleanup_before_ensure_returns(self) -> None:
        managed = ManagedVerifier(HARNESS_ROOT / "public-contract-support-unit")
        manager_stop = {
            "data": {
                "cleanup": {
                    "managerStopped": True,
                    "bootstrapCleaned": True,
                    "ownersEmpty": True,
                }
            }
        }
        with (
            mock.patch.object(managed, "reset"),
            mock.patch.object(support, "select_service_python", return_value=Path(sys.executable)),
            mock.patch.object(support, "install_digest", return_value="fixture-digest"),
            mock.patch.object(support, "run_json", return_value={}),
            mock.patch.object(managed, "_validate_service"),
            mock.patch.object(
                managed,
                "_pm",
                side_effect=({"ok": True}, RuntimeError("ensure failed"), manager_stop),
            ) as invoke,
        ):
            with self.assertRaisesRegex(RuntimeError, "ensure failed"):
                managed.start()
            self.assertIs(managed.manager_ensured, True)
            checks, failures = managed.stop()

        self.assertEqual(failures, [])
        self.assertEqual(checks["managerStopFallback"], manager_stop["data"])
        self.assertEqual(invoke.call_count, 3)


if __name__ == "__main__":
    unittest.main()
