"""闭合断言与 trusted verifier 测试。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from _helpers import temporary_workspace
from skill_evaluation_lab.assertions import evaluate_assertion, evaluate_assertions
from skill_evaluation_lab.isolation import initialize_git_baseline


def assertion(assertion_id: str, assertion_type: str, **values: object) -> dict[str, object]:
    return {"id": assertion_id, "type": assertion_type, **values}


class BuiltinAssertionTests(unittest.TestCase):
    def test_file_and_content_assertions_return_concrete_evidence(self) -> None:
        with temporary_workspace() as workspace:
            result_file = workspace / "outputs" / "result.json"
            result_file.parent.mkdir()
            result_file.write_text('{"status":"ready","items":[1]}\n', encoding="utf-8")

            checks = [
                assertion("exists", "file_exists", path="outputs/result.json"),
                assertion("absent", "file_absent", path="outputs/missing.json"),
                assertion("contains", "text_contains", path="outputs/result.json", value="ready"),
                assertion("excludes", "text_excludes", path="outputs/result.json", value="secret"),
                assertion("regex", "regex_matches", path="outputs/result.json", pattern=r'"status":"rea.+"'),
                assertion("valid", "json_valid", path="outputs/result.json"),
                assertion(
                    "field",
                    "json_field_equals",
                    path="outputs/result.json",
                    value={"field": "/status", "equals": "ready"},
                ),
            ]
            results = evaluate_assertions(checks, workspace=workspace)

        self.assertEqual(results["status"], "PASS")
        self.assertEqual(results["counts"], {"PASS": 7, "FAIL": 0, "ERROR": 0})
        self.assertEqual(results["results"][0]["evidence"]["path"], "outputs/result.json")
        self.assertIn("sha256", results["results"][0]["evidence"])
        self.assertEqual(results["results"][-1]["evidence"]["actual"], "ready")

    def test_git_diff_assertions_use_local_baseline(self) -> None:
        with temporary_workspace() as workspace:
            outputs = workspace / "outputs"
            outputs.mkdir()
            source = workspace / "input.txt"
            source.write_text("initial\n", encoding="utf-8")
            initialize_git_baseline(workspace)
            source.write_text("changed\n", encoding="utf-8")
            (outputs / "result.txt").write_text("created\n", encoding="utf-8")

            checks = [
                assertion("changed", "path_changed", path="input.txt"),
                assertion("portable", "path_changed", path=r"outputs\result.txt"),
                assertion("unchanged", "path_unchanged", path="outputs"),
                assertion("allow", "diff_allows_only", allow=["input.txt", r"outputs\**"]),
                assertion("deny", "diff_excludes", deny=["secrets/**"]),
            ]
            results = evaluate_assertions(checks, workspace=workspace)

        self.assertEqual(
            [item["status"] for item in results["results"]],
            ["PASS", "PASS", "FAIL", "PASS", "PASS"],
        )
        self.assertEqual(results["results"][2]["evidence"]["changed"], True)

    def test_invalid_contract_shape_and_path_escape_are_errors(self) -> None:
        with temporary_workspace() as workspace:
            malformed = evaluate_assertion(
                assertion("field", "json_field_equals", path="missing.json", value="bad"),
                workspace=workspace,
            )
            escaped = evaluate_assertion(
                assertion("escape", "file_exists", path="../outside.txt"),
                workspace=workspace,
            )
            unknown = evaluate_assertion(assertion("unknown", "arbitrary-shell"), workspace=workspace)
            summary = evaluate_assertions(
                [assertion("unknown", "arbitrary-shell")],
                workspace=workspace,
            )

        self.assertEqual([malformed.status, escaped.status, unknown.status], ["ERROR", "ERROR", "ERROR"])
        self.assertEqual(summary["status"], "ERROR")

    def test_large_file_evidence_skips_unbounded_hashing(self) -> None:
        with temporary_workspace() as workspace:
            path = workspace / "large.bin"
            path.write_bytes(b"x" * 64)
            with mock.patch("skill_evaluation_lab.assertions.MAX_ASSERTION_FILE_BYTES", 32):
                result = evaluate_assertion(
                    assertion("large", "file_exists", path="large.bin"),
                    workspace=workspace,
                )

        self.assertEqual(result.status, "PASS")
        self.assertFalse(result.evidence["sha256_available"])
        self.assertNotIn("sha256", result.evidence)

    def test_rename_evidence_contains_old_and_new_paths(self) -> None:
        with temporary_workspace() as workspace:
            original = workspace / "before.txt"
            original.write_text("content\n", encoding="utf-8")
            initialize_git_baseline(workspace)
            original.rename(workspace / "after.txt")
            result = evaluate_assertion(
                assertion("renamed", "diff_allows_only", allow=["before.txt", "after.txt"]),
                workspace=workspace,
            )

        self.assertEqual(result.status, "PASS")

    def test_git_status_output_limit_becomes_assertion_error(self) -> None:
        with temporary_workspace() as workspace:
            (workspace / "tracked.txt").write_text("before\n", encoding="utf-8")
            initialize_git_baseline(workspace)
            (workspace / "tracked.txt").write_text("after\n", encoding="utf-8")
            with mock.patch("skill_evaluation_lab.assertions.MAX_GIT_STATUS_BYTES", 4):
                result = evaluate_assertion(
                    assertion("bounded", "path_changed", path="tracked.txt"),
                    workspace=workspace,
                )

        self.assertEqual(result.status, "ERROR")
        self.assertIn("大小上限", result.message)


class TrustedVerifierTests(unittest.TestCase):
    def test_verifier_requires_explicit_trust_and_strips_business_secrets(self) -> None:
        check = assertion(
            "verify",
            "verifier_command",
            argv=[
                sys.executable,
                "-c",
                "import os,sys;sys.exit(1 if 'SKILL_GITLAB_PAT' in os.environ else 0)",
            ],
            timeout_seconds=5,
        )
        with temporary_workspace() as workspace:
            with mock.patch.dict(os.environ, {"SKILL_GITLAB_PAT": "do-not-inherit"}):
                denied = evaluate_assertion(check, workspace=workspace)
                allowed = evaluate_assertion(check, workspace=workspace, trusted_verifier=True)

        self.assertEqual(denied.status, "ERROR")
        self.assertEqual(allowed.status, "PASS")
        self.assertEqual(allowed.evidence["return_code"], 0)

    def test_verifier_disables_git_configuration_and_prompts(self) -> None:
        script = (
            "import os,sys;"
            "ok=os.environ.get('GIT_CONFIG_NOSYSTEM')=='1' and "
            "os.environ.get('GIT_TERMINAL_PROMPT')=='0' and "
            "bool(os.environ.get('GIT_CONFIG_GLOBAL'));"
            "sys.exit(0 if ok else 1)"
        )
        with temporary_workspace() as workspace:
            result = evaluate_assertion(
                assertion("git-env", "verifier_command", argv=[sys.executable, "-c", script]),
                workspace=workspace,
                trusted_verifier=True,
            )

        self.assertEqual(result.status, "PASS")

    def test_verifier_reports_nonzero_timeout_and_output_limit(self) -> None:
        with temporary_workspace() as workspace:
            nonzero = evaluate_assertion(
                assertion(
                    "nonzero",
                    "verifier_command",
                    argv=[sys.executable, "-c", "import sys;print('bad');sys.exit(3)"],
                ),
                workspace=workspace,
                trusted_verifier=True,
            )
            timeout = evaluate_assertion(
                assertion(
                    "timeout",
                    "verifier_command",
                    argv=[sys.executable, "-c", "import time;time.sleep(2)"],
                    timeout_seconds=1,
                ),
                workspace=workspace,
                trusted_verifier=True,
            )
            with mock.patch("skill_evaluation_lab.assertions.MAX_VERIFIER_OUTPUT_BYTES", 32):
                overflow = evaluate_assertion(
                    assertion(
                        "overflow",
                        "verifier_command",
                        argv=[sys.executable, "-c", "print('x' * 4096)"],
                    ),
                    workspace=workspace,
                    trusted_verifier=True,
                )

        self.assertEqual(nonzero.status, "FAIL")
        self.assertEqual(nonzero.evidence["return_code"], 3)
        self.assertEqual(timeout.status, "ERROR")
        self.assertIn("超时", timeout.message)
        self.assertEqual(overflow.status, "ERROR")
        self.assertIn("大小上限", overflow.message)


if __name__ == "__main__":
    unittest.main()
