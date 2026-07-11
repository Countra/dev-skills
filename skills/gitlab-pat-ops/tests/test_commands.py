from __future__ import annotations

import base64
import io
import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
TEST_TMP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPT_DIR))

import gl_branches  # noqa: E402
import gl_capabilities  # noqa: E402
import gl_discussions  # noqa: E402
import gl_issues  # noqa: E402
import gl_labels  # noqa: E402
import gl_members  # noqa: E402
import gl_milestones  # noqa: E402
import gl_mrs  # noqa: E402
import gl_notes  # noqa: E402
import gl_projects  # noqa: E402
import gl_repo  # noqa: E402
import gl_templates  # noqa: E402
from fakes import FakeClient, run_and_parse, write_calls  # noqa: E402
from gitlab_ops import ConflictError, GitLabSkillError, UnsupportedCapabilityError  # noqa: E402


class CommandTests(unittest.TestCase):
    def test_capability_query_distinguishes_supported_forbidden_and_unknown(self) -> None:
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            code = gl_capabilities.main(["--capability", "issues.update"])
        value = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(value["data"]["supported"])
        self.assertEqual(value["data"]["capabilities"][0]["subcommand"], "update")
        self.assertNotIn("version", json.dumps(value))

        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            gl_capabilities.main(["--capability", "unknown.operation"])
        self.assertFalse(json.loads(output.getvalue())["data"]["supported"])
        with self.assertRaises(UnsupportedCapabilityError):
            gl_capabilities.main(["--capability", "merge_requests.merge"])
        with self.assertRaises(GitLabSkillError):
            gl_capabilities.main([])

    def test_every_allowed_write_defaults_to_preview_and_sends_once_after_confirm(self) -> None:
        cases = (
            (gl_projects, ["create", "--name", "demo"], "POST", "/projects"),
            (gl_issues, ["create", "--project", "group/proj", "--title", "Demo"], "POST", "/issues"),
            (gl_issues, ["update", "--project", "group/proj", "--iid", "3", "--title", "New"], "PUT", "/issues/3"),
            (gl_issues, ["close", "--project", "group/proj", "--iid", "3"], "PUT", "/issues/3"),
            (gl_issues, ["reopen", "--project", "group/proj", "--iid", "3"], "PUT", "/issues/3"),
            (
                gl_mrs,
                ["create", "--project", "group/proj", "--source-branch", "feature", "--target-branch", "main", "--title", "Demo"],
                "POST",
                "/merge_requests",
            ),
            (gl_mrs, ["update", "--project", "group/proj", "--iid", "4", "--title", "New"], "PUT", "/merge_requests/4"),
            (gl_mrs, ["close", "--project", "group/proj", "--iid", "4"], "PUT", "/merge_requests/4"),
            (gl_mrs, ["reopen", "--project", "group/proj", "--iid", "4"], "PUT", "/merge_requests/4"),
            (gl_notes, ["issue-reply", "--project", "group/proj", "--iid", "3", "--body", "hello"], "POST", "/issues/3/notes"),
            (gl_notes, ["mr-reply", "--project", "group/proj", "--iid", "4", "--body", "hello"], "POST", "/merge_requests/4/notes"),
            (
                gl_discussions,
                ["reply", "--resource", "issue", "--project", "group/proj", "--iid", "3", "--discussion-id", "abc", "--body", "hello"],
                "POST",
                "/discussions/abc/notes",
            ),
            (gl_discussions, ["resolve", "--project", "group/proj", "--iid", "4", "--discussion-id", "abc"], "PUT", "/discussions/abc"),
            (gl_discussions, ["reopen", "--project", "group/proj", "--iid", "4", "--discussion-id", "abc"], "PUT", "/discussions/abc"),
        )
        for module, argv, method, suffix in cases:
            with self.subTest(module=module.__name__, argv=argv[0]):
                client = FakeClient()
                code, preview = run_and_parse(module, argv, client)
                self.assertEqual(code, 0)
                self.assertTrue(preview["data"]["dry_run"])
                self.assertEqual(write_calls(client), [])
                fingerprint = preview["data"]["confirm_fingerprint"]
                code, applied = run_and_parse(module, [*argv, "--confirm", fingerprint], client)
                self.assertEqual(code, 0)
                self.assertTrue(applied["data"]["applied"])
                writes = write_calls(client)
                self.assertEqual(len(writes), 1)
                self.assertEqual(writes[0][0], method)
                self.assertIn(suffix, writes[0][1])

    def test_issue_update_has_explicit_clear_unassign_and_empty_rules(self) -> None:
        client = FakeClient()
        argv = [
            "update",
            "--project",
            "group/proj",
            "--iid",
            "3",
            "--clear-description",
            "--unassign",
            "--clear-labels",
            "--remove-milestone",
            "--remove-due-date",
            "--confidential",
            "false",
        ]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        body = value["data"]["json_body"]
        self.assertEqual(body["assignee_ids"], [])
        self.assertEqual(body["labels"], "")
        self.assertEqual(body["milestone_id"], 0)
        self.assertEqual(body["due_date"], "")
        self.assertFalse(body["confidential"])
        self.assertEqual(body["description"]["length"], 0)
        with self.assertRaises(GitLabSkillError):
            run_and_parse(gl_issues, ["update", "--project", "group/proj", "--iid", "3"], FakeClient())
        with self.assertRaises(GitLabSkillError):
            run_and_parse(
                gl_issues,
                ["update", "--project", "group/proj", "--iid", "3", "--description", ""],
                FakeClient(),
            )
        with self.assertRaises(GitLabSkillError):
            run_and_parse(
                gl_issues,
                ["update", "--project", "group/proj", "--iid", "3", "--labels", "bug", "--add-labels", "feature"],
                FakeClient(),
            )
        for extra_args in (
            ["--labels", ""],
            ["--assignee-ids", ""],
            ["--milestone-id", "0"],
        ):
            with self.subTest(extra_args=extra_args):
                with self.assertRaises(GitLabSkillError):
                    run_and_parse(
                        gl_issues,
                        ["update", "--project", "group/proj", "--iid", "3", *extra_args],
                        FakeClient(),
                    )

    def test_mr_update_supports_reviewer_unassign_and_false_booleans(self) -> None:
        code, value = run_and_parse(
            gl_mrs,
            [
                "update",
                "--project",
                "group/proj",
                "--iid",
                "4",
                "--unassign-reviewers",
                "--remove-source-branch",
                "false",
                "--squash",
                "false",
            ],
            FakeClient(),
        )
        self.assertEqual(code, 0)
        self.assertEqual(value["data"]["json_body"]["reviewer_ids"], [])
        self.assertFalse(value["data"]["json_body"]["remove_source_branch"])
        self.assertFalse(value["data"]["json_body"]["squash"])

    def test_project_templates_compose_issue_and_mr_without_repository_fallback(self) -> None:
        for module, resource_type, create_args in (
            (gl_issues, "issues", ["create", "--project", "group/proj", "--title", "Issue", "--template", "feature"]),
            (
                gl_mrs,
                "merge_requests",
                [
                    "create",
                    "--project",
                    "group/proj",
                    "--source-branch",
                    "feature",
                    "--target-branch",
                    "main",
                    "--title",
                    "MR",
                    "--template",
                    "feature",
                ],
            ),
        ):
            with self.subTest(resource_type=resource_type):
                client = FakeClient()
                code, value = run_and_parse(module, create_args, client)
                self.assertEqual(code, 0)
                self.assertEqual(value["data"]["description_source"], f"template:{resource_type}/feature")
                self.assertNotIn("template body", json.dumps(value))
                paths = [call[1] for call in client.request_calls]
                self.assertTrue(any(f"/templates/{resource_type}/feature" in path for path in paths))
                self.assertFalse(any("/repository/files/" in path for path in paths))

        code, template = run_and_parse(
            gl_templates,
            ["get", "--project", "group/proj", "--type", "issues", "--name", "feature"],
            FakeClient(),
        )
        self.assertEqual(code, 0)
        self.assertEqual(template["data"]["content"], "template body")
        with self.assertRaises(GitLabSkillError):
            run_and_parse(
                gl_issues,
                ["create", "--project", "group/proj", "--title", "Issue", "--source-template-project-id", "9"],
                FakeClient(),
            )

    def test_note_and_discussion_previews_hash_private_bodies(self) -> None:
        note_client = FakeClient()
        _, note = run_and_parse(
            gl_notes,
            ["issue-reply", "--project", "group/proj", "--iid", "3", "--body", "private reply"],
            note_client,
        )
        self.assertNotIn("private reply", json.dumps(note))

        discussion_client = FakeClient()
        _, discussion = run_and_parse(
            gl_discussions,
            ["resolve", "--project", "group/proj", "--iid", "4", "--discussion-id", "abc"],
            discussion_client,
        )
        self.assertNotIn("private discussion body", json.dumps(discussion))
        self.assertIn("body_sha256", json.dumps(discussion))

    def test_repository_raw_output_is_binary_safe_and_non_overwriting(self) -> None:
        raw = b"\xff\x00binary"
        code, value = run_and_parse(
            gl_repo,
            ["raw", "--project", "group/proj", "--file-path", "asset.bin", "--ref", "main"],
            FakeClient(raw),
        )
        self.assertEqual(code, 0)
        self.assertEqual(base64.b64decode(value["data"]["content"]), raw)
        self.assertEqual(value["data"]["encoding"], "base64")

        output_path = TEST_TMP_ROOT / f".gitlab-pat-ops-{uuid.uuid4().hex}.bin"
        try:
            argv = [
                "raw",
                "--project",
                "group/proj",
                "--file-path",
                "asset.bin",
                "--ref",
                "main",
                "--output",
                str(output_path),
            ]
            run_and_parse(gl_repo, argv, FakeClient(raw))
            self.assertEqual(output_path.read_bytes(), raw)
            with self.assertRaises(GitLabSkillError):
                run_and_parse(gl_repo, argv, FakeClient(raw))
        finally:
            output_path.unlink(missing_ok=True)

    def test_existing_metadata_resources_keep_independent_endpoints(self) -> None:
        cases = (
            (gl_labels, ["list", "--project", "group/proj", "--search", "bug"], "/labels"),
            (gl_milestones, ["issues", "--project", "group/proj", "--milestone-id", "7"], "/milestones/7/issues"),
            (gl_members, ["list", "--project", "group/proj", "--include-inherited"], "/members/all"),
            (gl_branches, ["get", "--project", "group/proj", "--branch", "feature/demo"], "/branches/feature%2Fdemo"),
        )
        for module, argv, suffix in cases:
            with self.subTest(module=module.__name__):
                client = FakeClient()
                code, value = run_and_parse(module, argv, client)
                self.assertEqual(code, 0)
                self.assertTrue(value["ok"])
                self.assertTrue(any(suffix in call[1] for call in client.request_calls))

    def test_wrong_confirmation_never_sends(self) -> None:
        with self.assertRaises(ConflictError):
            run_and_parse(
                gl_issues,
                ["close", "--project", "group/proj", "--iid", "3", "--confirm", "sha256:wrong"],
                FakeClient(),
            )


if __name__ == "__main__":
    unittest.main()
