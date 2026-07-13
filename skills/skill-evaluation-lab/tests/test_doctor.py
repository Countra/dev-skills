"""Doctor 环境与无模型 capability probe 测试。"""

from __future__ import annotations

import unittest
from unittest import mock

from _helpers import temporary_workspace
from se_doctor import collect_diagnostics
from skill_evaluation_lab.errors import DependencyError


def available_version(command: str) -> dict[str, object]:
    return {"available": True, "path": command, "version": f"{command} 1.0"}


class DoctorTests(unittest.TestCase):
    def test_optional_probe_is_exposed_without_model_call(self) -> None:
        with temporary_workspace() as root:
            probe = {"supported": True, "live_model_called": False}
            with mock.patch("se_doctor._version", side_effect=available_version), mock.patch(
                "se_doctor.probe_codex",
                return_value=probe,
            ) as runner:
                result = collect_diagnostics(
                    require_live=False,
                    probe_skill=root / "skill",
                    workspace=root,
                )

        self.assertEqual(result["capability_probe"], probe)
        self.assertFalse(result["live_model_called"])
        runner.assert_called_once()

    def test_live_requirement_fails_when_codex_is_missing(self) -> None:
        def version(command: str) -> dict[str, object]:
            if command == "codex":
                return {"available": False, "path": None, "version": None}
            return available_version(command)

        with temporary_workspace() as root, mock.patch("se_doctor._version", side_effect=version):
            with self.assertRaisesRegex(DependencyError, "Codex CLI"):
                collect_diagnostics(require_live=True, probe_skill=None, workspace=root)


if __name__ == "__main__":
    unittest.main()
