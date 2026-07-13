"""公共 suite runner 的离线成对编排测试。"""

from __future__ import annotations

import json
import stat
from copy import deepcopy
import unittest
from unittest import mock

from _helpers import temporary_workspace, valid_suite, write_json
from se_run import BehaviorCodexRunner, _behavior_child_env, execute_suite
from skill_evaluation_lab.budgets import RunBudget
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.errors import ExecutionError, SuiteError
from skill_evaluation_lab.run_contracts import validate_run_manifest
from skill_evaluation_lab.runners import RunRequest


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

    def test_behavior_runner_detects_visible_skill_mutation(self) -> None:
        with temporary_workspace() as root:
            workspace = root / "workspace"
            skill = workspace / ".agents" / "skills" / "probe"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(
                "---\nname: probe\ndescription: Probe.\n---\n\n# Probe\n",
                encoding="utf-8",
            )
            request = RunRequest(
                run_id="run",
                case_id="behavior",
                attempt=1,
                prompt="Create an output.",
                workspace=workspace,
                artifact_dir=root / "artifacts",
                model="test-model",
                sandbox="workspace-write",
                timeout_seconds=30,
                fingerprint="f" * 64,
                lab_tree_sha256="a" * 64,
                approved_fingerprint="f" * 64,
                live_authorized=True,
                skill_path=skill,
            )

            def mutate_skill(*_args: object, **_kwargs: object) -> int:
                (request.artifact_dir / "trace.jsonl").write_text(
                    "".join(
                        json.dumps(event) + "\n"
                        for event in (
                            {"type": "thread.started", "thread_id": "thread"},
                            {"type": "turn.completed", "usage": {}},
                        )
                    ),
                    encoding="utf-8",
                )
                (request.artifact_dir / "final.json").write_text(
                    '{"response":"ok"}\n',
                    encoding="utf-8",
                )
                skill_file.chmod(skill_file.stat().st_mode | stat.S_IWUSR)
                skill_file.write_text("mutated\n", encoding="utf-8")
                return 0

            budget = RunBudget(max_agent_runs=1, max_judge_runs=0, max_wall_seconds=60)
            with mock.patch("se_run.codex_path", return_value="codex"), mock.patch(
                "se_run.run_capture",
                return_value="codex 1.0\n",
            ), mock.patch("se_run._run_behavior_bounded", side_effect=mutate_skill):
                with self.assertRaisesRegex(ExecutionError, "完整性"):
                    BehaviorCodexRunner().run(request, budget)


if __name__ == "__main__":
    unittest.main()
