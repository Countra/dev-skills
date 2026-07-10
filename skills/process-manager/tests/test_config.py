from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import create_config, service_value, workspace_directory, write_json  # noqa: E402
from process_manager.config import (  # noqa: E402
    load_manager_config,
    load_service_config,
    resolve_service_environment,
)
from process_manager.errors import ValidationError  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_manager_config_is_closed_and_uses_os_assigned_port(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            self.assertEqual(config.port, 0)
            value = json.loads(config.config_path.read_text(encoding="utf-8"))
            value["control"]["port"] = 43210
            write_json(config.config_path, value)
            with self.assertRaises(ValidationError):
                load_manager_config(config.config_path)
            value["control"]["port"] = 0
            value["portRetry"] = {"enabled": True}
            write_json(config.config_path, value)
            with self.assertRaises(ValidationError):
                load_manager_config(config.config_path)

    def test_service_schema_accepts_only_direct_or_script(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            path = workspace / "service.json"
            value = service_value(workspace)
            write_json(path, value)
            service = load_service_config(path, config)
            self.assertEqual(service.launcher["type"], "script")
            for mutation in (
                {"minimumGuarantee": "kernel-tree"},
                {"platform": "windows"},
                {"backend": "job-object"},
                {"env": {"A": "B"}},
            ):
                with self.subTest(mutation=mutation):
                    changed = dict(value)
                    changed.update(mutation)
                    write_json(path, changed)
                    with self.assertRaises(ValidationError):
                        load_service_config(path, config)
            changed = service_value(workspace)
            changed["launcher"] = {"type": "direct", "argv": [sys.executable]}
            write_json(path, changed)
            with self.assertRaises(ValidationError):
                load_service_config(path, config)

    def test_secret_environment_uses_from_env_and_stays_out_of_summary(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            path = workspace / "service.json"
            value = service_value(workspace, from_env=["APP_TOKEN"])
            write_json(path, value)
            service = load_service_config(path, config)
            with mock.patch.dict(os.environ, {"APP_TOKEN": "secret-value"}, clear=False):
                environment, secrets = resolve_service_environment(service)
            self.assertEqual(environment["APP_TOKEN"], "secret-value")
            self.assertEqual(secrets, ["secret-value"])
            self.assertNotIn("secret-value", json.dumps(service.public_summary()))
            value["environment"]["set"]["APP_TOKEN"] = "bad"
            value["environment"]["fromEnv"] = []
            write_json(path, value)
            with self.assertRaises(ValidationError):
                load_service_config(path, config)

    def test_readiness_rejects_fields_from_another_probe_type(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            path = workspace / "service.json"
            value = service_value(workspace)
            value["readiness"]["url"] = "http://127.0.0.1:8000"
            write_json(path, value)
            with self.assertRaises(ValidationError):
                load_service_config(path, config)

    def test_log_readiness_rejects_unbounded_backtracking_pattern(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            path = workspace / "service.json"
            value = service_value(workspace)
            value["readiness"] = {
                "type": "log",
                "pattern": "(a+)+$",
                "extract": {},
                "scanBytes": 4096,
                "timeoutSeconds": 1,
            }
            write_json(path, value)
            with self.assertRaisesRegex(ValidationError, "可回溯重复"):
                load_service_config(path, config)


if __name__ == "__main__":
    unittest.main()
