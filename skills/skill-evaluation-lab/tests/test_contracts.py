"""Suite 契约和预算预览测试。"""

from __future__ import annotations

import json
import unittest

from _helpers import SKILL_ROOT, temporary_workspace, valid_suite, write_json
from skill_evaluation_lab.budgets import build_experiment_plan
from skill_evaluation_lab.contracts import load_suite
from skill_evaluation_lab.errors import SuiteError


class ContractTests(unittest.TestCase):
    def test_valid_suite_and_plan(self) -> None:
        with temporary_workspace() as root:
            suite_path = root / "suite.json"
            write_json(suite_path, valid_suite(root))
            suite = load_suite(suite_path)
            plan = build_experiment_plan(suite)
            self.assertEqual(plan["agent_run_count"], 3)
            self.assertEqual(len(plan["fingerprint"]), 64)

    def test_rejects_unknown_root_field(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["version"] = 1
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "未知字段"):
                load_suite(suite_path)

    def test_rejects_duplicate_case(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][1]["id"] = value["cases"][0]["id"]
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "case id 重复"):
                load_suite(suite_path)

    def test_rejects_unsafe_input_path(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][0]["inputs"] = ["../secret.txt"]
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "不能包含"):
                load_suite(suite_path)

    def test_rejects_windows_escape_on_every_platform(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][0]["inputs"] = ["..\\secret.txt"]
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "不能包含"):
                load_suite(suite_path)

    def test_rejects_unbounded_matrix(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["runner"]["repetitions"] = 10
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "超过上限"):
                build_experiment_plan(load_suite(suite_path))

    def test_rejects_budget_above_implementation_cap(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["budgets"]["max_agent_runs"] = 257
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "实现上限 256"):
                load_suite(suite_path)

    def test_rejects_assertion_path_escape(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][1]["assertions"][0]["path"] = "../result.json"
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "相对路径"):
                load_suite(suite_path)

    def test_verifier_requires_explicit_trust(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][1]["assertions"] = [
                {"id": "custom", "type": "verifier_command", "argv": ["python", "verify.py"]}
            ]
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "trusted_verifier"):
                load_suite(suite_path)

    def test_rejects_fields_irrelevant_to_assertion_type(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][1]["assertions"][0]["value"] = "silently ignored"
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "file_exists assertion 不允许"):
                load_suite(suite_path)

    def test_rejects_fields_irrelevant_to_case_mode(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][0]["assertions"] = []
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "trigger case 不允许"):
                load_suite(suite_path)

    def test_rejects_invalid_json_field_contract(self) -> None:
        with temporary_workspace() as root:
            value = valid_suite(root)
            value["cases"][1]["assertions"] = [
                {
                    "id": "decision",
                    "type": "json_field_equals",
                    "path": "outputs/result.json",
                    "value": {"field": "/decision"},
                }
            ]
            suite_path = root / "suite.json"
            write_json(suite_path, value)
            with self.assertRaisesRegex(SuiteError, "field 与 equals"):
                load_suite(suite_path)

    def test_published_schema_closes_nested_variants(self) -> None:
        schema = json.loads((SKILL_ROOT / "schemas" / "eval-suite.schema.json").read_text(encoding="utf-8"))
        definitions = schema["$defs"]
        self.assertFalse(definitions["runner"]["additionalProperties"])
        self.assertFalse(definitions["triggerCase"]["additionalProperties"])
        self.assertFalse(definitions["behaviorCase"]["additionalProperties"])
        self.assertEqual(len(definitions["assertion"]["oneOf"]), 12)
        run_schema = json.loads(
            (SKILL_ROOT / "schemas" / "run-manifest.schema.json").read_text(encoding="utf-8")
        )
        final_schema = json.loads(
            (SKILL_ROOT / "schemas" / "final-response.schema.json").read_text(encoding="utf-8")
        )
        report_schema = json.loads(
            (SKILL_ROOT / "schemas" / "report.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(run_schema["additionalProperties"])
        self.assertEqual(len(final_schema["oneOf"]), 2)
        self.assertFalse(report_schema["additionalProperties"])
        self.assertFalse(report_schema["$defs"]["gateDecisions"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
