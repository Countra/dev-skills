"""公共契约 fixture 的 process-manager 参数边界测试。"""

from __future__ import annotations

import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
