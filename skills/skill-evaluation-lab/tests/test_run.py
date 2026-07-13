"""公共 suite runner 的离线成对编排测试。"""

from __future__ import annotations

import json
from copy import deepcopy
import unittest
from unittest import mock

from _helpers import temporary_workspace, valid_suite, write_json
from se_run import _behavior_child_env, execute_suite
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.errors import SuiteError
from skill_evaluation_lab.run_contracts import validate_run_manifest


class SuiteRunTests(unittest.TestCase):
    def test_managed_workspace_profile_is_narrowly_forwarded(self) -> None:
        with mock.patch.dict("os.environ", {"CODEX_PERMISSION_PROFILE": ":workspace"}, clear=True):
            environment, profile = _behavior_child_env()
        self.assertEqual(profile, ":workspace")
        self.assertEqual(environment["CODEX_PERMISSION_PROFILE"], ":workspace")

        with mock.patch.dict("os.environ", {"CODEX_PERMISSION_PROFILE": "danger-full-access"}, clear=True):
            environment, profile = _behavior_child_env()
        self.assertEqual(profile, "cli-workspace-write")
        self.assertNotIn("CODEX_PERMISSION_PROFILE", environment)

    def test_fake_run_preserves_pairing_and_writes_manifest(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][0]["should_trigger"] = False
            value["cases"][1]["assertions"] = [
                {"id": "result-absent", "type": "file_absent", "path": "outputs/result.json"}
            ]
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            result = execute_suite(
                load_suite(suite_path),
                work_root=root / "runs",
                approved_fingerprint=None,
                authorize_live=False,
                run_id="offline-pair",
            )

            manifest_path = root / "runs" / "test-suite" / "offline-pair" / "run.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIs(validate_run_manifest(manifest), manifest)
            invalid = deepcopy(manifest)
            invalid["unexpected"] = True
            with self.assertRaisesRegex(SuiteError, "未知字段"):
                validate_run_manifest(invalid)
            invalid = deepcopy(manifest)
            invalid["records"][0]["repetition"] = 21
            with self.assertRaisesRegex(SuiteError, "repetition"):
                validate_run_manifest(invalid)
            invalid = deepcopy(manifest)
            invalid["records"][1]["pairing"]["model"] = "different-model"
            invalid["records"][1]["runner"]["provenance"]["model"] = "different-model"
            with self.assertRaisesRegex(SuiteError, "执行条件不一致"):
                validate_run_manifest(invalid)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["records"]), 3)
            self.assertEqual(result["source_identity"]["candidate"]["file_count"], 1)
            self.assertEqual(result["source_identity"]["baseline"], "none")
            self.assertEqual(result["gates"], value["gates"])
            self.assertEqual(len(result["lab_identity"]["tree_sha256"]), 64)
            self.assertEqual(result["execution_order"], "serial-paired-alternating")
            self.assertEqual(result["effective_concurrency"], 1)
            self.assertTrue(all(item["runner"]["duration_seconds"] is not None for item in result["records"]))
            trigger = next(item for item in result["records"] if item["mode"] == "trigger")
            self.assertFalse(trigger["observed_trigger"])
            paired = [item for item in result["records"] if item["mode"] == "behavior"]
            self.assertEqual([item["variant"] for item in paired], ["candidate", "baseline"])
            self.assertEqual(
                {key: value for key, value in paired[0]["pairing"].items() if key != "skill_snapshot"},
                {key: value for key, value in paired[1]["pairing"].items() if key != "skill_snapshot"},
            )
            self.assertEqual(paired[0]["pairing"]["skill_snapshot"], "candidate")
            self.assertEqual(paired[1]["pairing"]["skill_snapshot"], "none")


if __name__ == "__main__":
    unittest.main()
