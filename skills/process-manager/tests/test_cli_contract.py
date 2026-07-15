from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from helpers import workspace_directory  # noqa: E402
import pm_ready  # noqa: E402


PUBLIC_SCRIPTS = sorted(SCRIPTS_DIR.glob("pm_*.py"))
FORBIDDEN_OPTIONS = ("--platform", "--backend", "--guarantee")


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-B", str(script), *arguments],
        cwd=SCRIPTS_DIR.parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )


class CliContractTests(unittest.TestCase):
    def assert_platform_neutral(self, output: str) -> None:
        for option in FORBIDDEN_OPTIONS:
            self.assertNotIn(option, output)

    def test_all_public_scripts_have_platform_neutral_help(self) -> None:
        self.assertGreater(len(PUBLIC_SCRIPTS), 5)
        for script in PUBLIC_SCRIPTS:
            arguments = ("start", "--help") if script.name == "pm_manager.py" else ("--help",)
            with self.subTest(script=script.name):
                result = run_script(script, *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())
                self.assert_platform_neutral(result.stdout)
                if script.name == "pm_init.py":
                    self.assertNotIn("--port", result.stdout)

    def test_manager_subcommands_share_one_public_contract(self) -> None:
        script = SCRIPTS_DIR / "pm_manager.py"
        for command in ("start", "status", "stop"):
            with self.subTest(command=command):
                result = run_script(script, command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--config", result.stdout)
                self.assertIn("--pretty", result.stdout)
                self.assert_platform_neutral(result.stdout)

    def test_missing_config_returns_stable_json_error(self) -> None:
        with workspace_directory() as directory:
            result = run_script(SCRIPTS_DIR / "pm_health.py", "--config", str(Path(directory) / "missing.json"))
        self.assertEqual(result.returncode, 2, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["ok"], False)
        self.assertEqual(value["operation"], "health")
        self.assertEqual(value["error"]["code"], "configuration_error")
        self.assertEqual(set(value), {"ok", "operation", "error", "meta"})

    def test_ready_client_covers_service_timeout_when_override_is_omitted(self) -> None:
        client = mock.Mock()
        client.request.return_value = (200, {"ok": True})
        with (
            mock.patch.object(pm_ready, "make_client", return_value=client) as make_client,
            mock.patch.object(pm_ready, "output_remote", return_value=0),
        ):
            result = pm_ready.main(["--config", "manager.json", "--service", "demo"])

        self.assertEqual(0, result)
        make_client.assert_called_once_with("manager.json", timeout=605)
        client.request.assert_called_once_with(
            "POST",
            "/processes/ready",
            {"service": "demo", "processKey": None, "timeoutSeconds": None},
        )

    def test_ready_client_uses_explicit_timeout_with_transport_margin(self) -> None:
        client = mock.Mock()
        client.request.return_value = (200, {"ok": True})
        with (
            mock.patch.object(pm_ready, "make_client", return_value=client) as make_client,
            mock.patch.object(pm_ready, "output_remote", return_value=0),
        ):
            result = pm_ready.main(
                ["--config", "manager.json", "--process-key", "demo.run-1", "--timeout", "75"]
            )

        self.assertEqual(0, result)
        make_client.assert_called_once_with("manager.json", timeout=80.0)


if __name__ == "__main__":
    unittest.main()
