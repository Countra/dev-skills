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


if __name__ == "__main__":
    unittest.main()
