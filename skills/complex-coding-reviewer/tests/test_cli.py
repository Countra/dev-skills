from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import create_file_target, receipt_for_target, writable_tempdir, write_json


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


class CliTests(unittest.TestCase):
    def run_script(self, name: str, *arguments: str) -> tuple[int, dict[str, object]]:
        result = subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-B", str(SCRIPT_DIR / name), *arguments],
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI 未返回 JSON：stdout={result.stdout!r}; stderr={result.stderr!r}; error={exc}")
        return result.returncode, payload

    def test_target_cli_writes_only_under_review_root(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            target = create_file_target(root)
            original = (root / "src" / "example.py").read_bytes()
            review_root = root / "reviews"
            output = review_root / "target.json"
            code, payload = self.run_script(
                "review_target.py",
                "files",
                "--workspace",
                str(root),
                "--file",
                "src/example.py",
                "--label",
                "unit-test",
                "--review-root",
                str(review_root),
                "--output",
                str(output),
            )
            self.assertEqual(0, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(target["digest"], payload["result"]["target"]["digest"])
            self.assertEqual(original, (root / "src" / "example.py").read_bytes())
            self.assertTrue(output.is_file())

    def test_target_cli_requires_explicit_review_root(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            create_file_target(root)
            code, payload = self.run_script(
                "review_target.py",
                "files",
                "--workspace",
                str(root),
                "--file",
                "src/example.py",
                "--output",
                str(root / "target.json"),
            )
            self.assertEqual(1, code)
            self.assertEqual("REVIEW_OUTPUT_ROOT_REQUIRED", payload["error"]["code"])

    def test_target_cli_refuses_overwrite(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            create_file_target(root)
            review_root = root / "reviews"
            review_root.mkdir()
            output = review_root / "target.json"
            output.write_text("existing\n", encoding="utf-8")
            code, payload = self.run_script(
                "review_target.py",
                "files",
                "--workspace",
                str(root),
                "--file",
                "src/example.py",
                "--review-root",
                str(review_root),
                "--output",
                str(output),
            )
            self.assertEqual(1, code)
            self.assertEqual("REVIEW_OUTPUT_EXISTS", payload["error"]["code"])

    def test_validate_and_render_cli(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            review_root = root / "reviews"
            receipt_path = review_root / "receipt.json"
            write_json(receipt_path, receipt)
            code, payload = self.run_script(
                "review_validate.py",
                "--receipt",
                str(receipt_path),
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--expected-profile",
                "code-review",
                "--expected-scope",
                "standalone",
                "--expected-dispatch-policy",
                "conditional",
            )
            self.assertEqual(0, code, payload)
            self.assertEqual(0, payload["result"]["agent_calls"])
            self.assertEqual(0, payload["result"]["network_calls"])
            output = review_root / "receipt.md"
            code, payload = self.run_script(
                "review_render.py",
                "--receipt",
                str(receipt_path),
                "--workspace",
                str(root),
                "--review-root",
                str(review_root),
                "--expected-dispatch-policy",
                "conditional",
                "--output",
                str(output),
            )
            self.assertEqual(0, code, payload)
            self.assertIn("# Review REV-CODE-001", output.read_text(encoding="utf-8"))

    def test_dispatch_and_assemble_cli_remain_agent_free(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            review_root = root / "reviews"
            dispatch_path = review_root / Path(
                *receipt["reviewer"]["dispatch_ref"].split("/")
            )
            dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
            target_path = review_root / Path(*dispatch["inputs"]["target_ref"].split("/"))
            context_path = review_root / Path(*dispatch["inputs"]["context_ref"].split("/"))
            result_path = review_root / Path(
                *dispatch["inputs"]["semantic_result_ref"].split("/")
            )
            code, payload = self.run_script(
                "review_dispatch.py",
                "validate",
                "--dispatch",
                str(dispatch_path),
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--expected-dispatch-policy",
                "conditional",
                "--require-receipt-ready",
            )
            self.assertEqual(0, code, payload)
            self.assertEqual(0, payload["result"]["agent_calls"])
            assembled_path = review_root / "assembled-cli.json"
            code, payload = self.run_script(
                "review_assemble.py",
                "--target",
                str(target_path),
                "--context",
                str(context_path),
                "--dispatch",
                str(dispatch_path),
                "--semantic-result",
                str(result_path),
                "--workspace",
                str(root),
                "--review-root",
                str(review_root),
                "--expected-dispatch-policy",
                "conditional",
                "--output",
                str(assembled_path),
            )
            self.assertEqual(0, code, payload)
            self.assertTrue(payload["result"]["gate_ready"])
            self.assertEqual(0, payload["result"]["agent_calls"])

            preparation_path = review_root / "dispatches" / "cli-prepare.json"
            code, payload = self.run_script(
                "review_dispatch.py",
                "prepare",
                "--review-id",
                "REV-CLI-002",
                "--target",
                str(target_path),
                "--context",
                str(context_path),
                "--policy",
                "conditional",
                "--capability-status",
                "unavailable",
                "--tool-family",
                "cli-test-host",
                "--prepared-at",
                "2026-07-16T00:00:00+00:00",
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--output",
                str(preparation_path),
            )
            self.assertEqual(0, code, payload)
            self.assertEqual("fallback", payload["result"]["decision"])
            outcome_path = review_root / "dispatches" / "cli-outcome.json"
            write_json(
                outcome_path,
                {
                    "status": "fallback",
                    "agent_id": None,
                    "fork_context": None,
                    "started_at": None,
                    "completed_at": "2026-07-16T00:00:02+00:00",
                    "schema_repair_count": 0,
                    "context_expansion_requested": False,
                    "parent_judgment_included": False,
                    "recursive_delegation_allowed": False,
                    "failure": None,
                    "close": {
                        "required": False,
                        "attempted": False,
                        "status": "not-required",
                        "closed_at": None,
                        "error": None,
                    },
                    "fallback": {
                        "mode": "same-context",
                        "reason_code": "REVIEW_HOST_TOOLS_UNAVAILABLE",
                        "reason": "CLI 测试宿主没有 Agent 工具。",
                    },
                },
            )
            finalized_path = review_root / "dispatches" / "cli-final.json"
            code, payload = self.run_script(
                "review_dispatch.py",
                "finalize",
                "--preparation",
                str(preparation_path),
                "--outcome",
                str(outcome_path),
                "--finalized-at",
                "2026-07-16T00:00:03+00:00",
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--output",
                str(finalized_path),
            )
            self.assertEqual(0, code, payload)
            self.assertEqual("fallback", payload["result"]["lifecycle_status"])
            self.assertEqual(0, payload["result"]["agent_calls"])

    def test_finalize_cli_reports_unclosed_agent_as_non_gating(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(
                create_file_target(root),
                root=root,
                delegated=True,
            )
            review_root = root / "reviews"
            dispatch_path = review_root / Path(
                *receipt["reviewer"]["dispatch_ref"].split("/")
            )
            dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
            preparation_path = review_root / Path(
                *dispatch["preparation_ref"].split("/")
            )
            outcome_path = review_root / "outcomes" / "unclosed-agent.json"
            write_json(
                outcome_path,
                {
                    "status": "failed",
                    "agent_id": "unit-agent-unclosed",
                    "fork_context": False,
                    "started_at": "2026-07-16T00:00:01+00:00",
                    "completed_at": "2026-07-16T00:00:02+00:00",
                    "schema_repair_count": 0,
                    "context_expansion_requested": False,
                    "parent_judgment_included": False,
                    "recursive_delegation_allowed": False,
                    "failure": {
                        "code": "REVIEW_DISPATCH_AGENT_UNCLOSED",
                        "reason": "close_agent 返回失败。",
                        "retryable": False,
                    },
                    "close": {
                        "required": True,
                        "attempted": True,
                        "status": "failed",
                        "closed_at": None,
                        "error": "close_agent 返回失败。",
                    },
                    "fallback": {
                        "mode": "none",
                        "reason_code": None,
                        "reason": None,
                    },
                },
            )
            finalized_path = review_root / "dispatches" / "unclosed-final.json"
            code, payload = self.run_script(
                "review_dispatch.py",
                "finalize",
                "--preparation",
                str(preparation_path),
                "--outcome",
                str(outcome_path),
                "--finalized-at",
                "2026-07-16T00:00:04+00:00",
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--output",
                str(finalized_path),
            )
            self.assertEqual(0, code, payload)
            self.assertEqual("failed", payload["result"]["lifecycle_status"])
            self.assertFalse(payload["result"]["receipt_ready"])
            self.assertEqual(0, payload["result"]["agent_calls"])

    def test_gating_cli_requires_explicit_dispatch_policy(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            review_root = root / "reviews"
            receipt_path = review_root / "receipt-policy.json"
            write_json(receipt_path, receipt)
            code, payload = self.run_script(
                "review_validate.py",
                "--receipt",
                str(receipt_path),
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
            )
            self.assertEqual(1, code)
            self.assertEqual(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                payload["error"]["code"],
            )

            dispatch_path = review_root / Path(
                *receipt["reviewer"]["dispatch_ref"].split("/")
            )
            dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
            output = review_root / "missing-policy.json"
            code, payload = self.run_script(
                "review_assemble.py",
                "--target",
                str(review_root / Path(*dispatch["inputs"]["target_ref"].split("/"))),
                "--context",
                str(review_root / Path(*dispatch["inputs"]["context_ref"].split("/"))),
                "--dispatch",
                str(dispatch_path),
                "--semantic-result",
                str(
                    review_root
                    / Path(*dispatch["inputs"]["semantic_result_ref"].split("/"))
                ),
                "--workspace",
                str(root),
                "--review-root",
                str(review_root),
                "--output",
                str(output),
            )
            self.assertEqual(1, code)
            self.assertEqual(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                payload["error"]["code"],
            )
            self.assertFalse(output.exists())

    def test_context_and_package_cli_are_bounded_and_read_only(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            review_root = root / "reviews"
            context_path = review_root / "context.json"
            brief_path = next(
                item["path"]
                for item in receipt["context"]["manifest"]
                if item["role"] == "brief"
            )
            code, payload = self.run_script(
                "review_context.py",
                "target",
                "--root",
                str(root),
                "--root-kind",
                "workspace",
                "--label",
                "cli-context",
                "--entry",
                f"{brief_path}=brief",
                "--entry",
                "src/example.py=adjacent-code",
                "--review-root",
                str(review_root),
                "--output",
                str(context_path),
            )
            self.assertEqual(0, code, payload)
            self.assertEqual(0, payload["result"]["agent_calls"])
            target_path = review_root / "target.json"
            write_json(target_path, receipt["target"])
            package_path = review_root / "package.json"
            code, payload = self.run_script(
                "review_package.py",
                "--target",
                str(target_path),
                "--context",
                str(context_path),
                "--workspace",
                str(root),
                "--generated-at",
                "2026-07-16T00:00:00+00:00",
                "--review-root",
                str(review_root),
                "--output",
                str(package_path),
            )
            self.assertEqual(0, code, payload)
            package = payload["result"]["package"]
            self.assertEqual(receipt["target"]["digest"], package["target_digest"])
            self.assertFalse(package["truncated"])

    def test_validate_rejects_receipt_outside_review_root(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            receipt_path = root / "outside.json"
            review_root = root / "reviews"
            review_root.mkdir(exist_ok=True)
            write_json(receipt_path, receipt)
            code, payload = self.run_script(
                "review_validate.py",
                "--receipt",
                str(receipt_path),
                "--review-root",
                str(review_root),
                "--workspace",
                str(root),
                "--expected-dispatch-policy",
                "conditional",
            )
            self.assertEqual(1, code)
            self.assertEqual("REVIEW_OUTPUT_PATH_ESCAPE", payload["error"]["code"])


if __name__ == "__main__":
    unittest.main()
