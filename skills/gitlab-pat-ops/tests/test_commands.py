from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import gl_capabilities  # noqa: E402
import gl_branches  # noqa: E402
import gl_issue_templates  # noqa: E402
import gl_issues  # noqa: E402
import gl_labels  # noqa: E402
import gl_members  # noqa: E402
import gl_milestones  # noqa: E402
import gl_mrs  # noqa: E402
import gl_notes  # noqa: E402
import gl_projects  # noqa: E402


class FakeClient:
    def __init__(self) -> None:
        self.preview_calls = []
        self.request_calls = []

    def preview(self, method, path, params, json_body):  # noqa: ANN001
        self.preview_calls.append((method, path, params, json_body))
        return {"dry_run": True, "method": method, "path": path, "json_body": json_body}

    def request(self, method, path, params=None, json_body=None, **kwargs):  # noqa: ANN001
        self.request_calls.append((method, path, params, json_body, kwargs))
        if kwargs.get("raw"):
            return b"template body"
        return {"sent": True, "method": method, "path": path, "json_body": json_body}


def run_and_parse(module, argv, client: FakeClient):  # noqa: ANN001
    output = io.StringIO()
    with mock.patch.object(module, "make_client", return_value=client):
        with mock.patch("sys.stdout", output):
            code = module.main(argv)
    return code, json.loads(output.getvalue())


class CommandTests(unittest.TestCase):
    def test_capabilities_lists_supported_and_unsupported_boundaries(self) -> None:
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            code = gl_capabilities.main(["--section", "guarded-writes"])
        value = json.loads(output.getvalue())
        guarded = value["result"]["guarded_writes"]
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["skill"]["name"], "gitlab-pat-ops")
        self.assertTrue(any(item["capability"] == "create_issue" for item in guarded))
        self.assertTrue(any(item["capability"] == "close_or_reopen_issue" for item in guarded))
        self.assertTrue(any(item["capability"] == "update_issue_description" for item in guarded))

    def test_project_create_without_confirm_is_dry_run(self) -> None:
        client = FakeClient()
        code, value = run_and_parse(gl_projects, ["create", "--name", "demo"], client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["dry_run"], True)
        self.assertEqual(client.request_calls, [])

    def test_project_create_with_confirm_sends_post(self) -> None:
        client = FakeClient()
        code, value = run_and_parse(gl_projects, ["create", "--name", "demo", "--confirm"], client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["sent"], True)
        self.assertEqual(client.request_calls[0][0], "POST")

    def test_issue_reply_dry_run_uses_body_file(self) -> None:
        client = FakeClient()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("[gitlab-pat-ops smoke] hello")
            body_path = handle.name
        try:
            argv = ["issue-reply", "--project", "group/proj", "--iid", "1", "--body-file", body_path]
            code, value = run_and_parse(gl_notes, argv, client)
        finally:
            Path(body_path).unlink(missing_ok=True)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["body_source"], "body-file")
        self.assertEqual(client.request_calls, [])

    def test_issue_reply_confirm_sends_post(self) -> None:
        client = FakeClient()
        argv = ["issue-reply", "--project", "group/proj", "--iid", "1", "--body", "hello", "--confirm"]
        code, value = run_and_parse(gl_notes, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["sent"], True)
        method, path, _params, body, _kwargs = client.request_calls[0]
        self.assertEqual(method, "POST")
        self.assertIn("/issues/1/notes", path)
        self.assertEqual(body["body"], "hello")

    def test_mr_create_dry_run_does_not_send_post(self) -> None:
        client = FakeClient()
        argv = [
            "create",
            "--project",
            "group/proj",
            "--source-branch",
            "feature",
            "--target-branch",
            "main",
            "--title",
            "Demo",
        ]
        code, value = run_and_parse(gl_mrs, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["dry_run"], True)
        self.assertEqual(client.request_calls, [])

    def test_labels_list_is_read_only(self) -> None:
        client = FakeClient()
        argv = ["list", "--project", "group/proj", "--search", "bug", "--with-counts"]
        code, value = run_and_parse(gl_labels, argv, client)
        self.assertEqual(code, 0)
        method, path, params, _body, _kwargs = client.request_calls[0]
        self.assertEqual(value["result"]["sent"], True)
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/projects/group%2Fproj/labels")
        self.assertEqual(params["search"], "bug")
        self.assertEqual(params["with_counts"], True)

    def test_milestone_issues_uses_project_milestone_endpoint(self) -> None:
        client = FakeClient()
        argv = ["issues", "--project", "group/proj", "--milestone-id", "7"]
        code, _value = run_and_parse(gl_milestones, argv, client)
        self.assertEqual(code, 0)
        method, path, _params, _body, _kwargs = client.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/projects/group%2Fproj/milestones/7/issues")

    def test_members_list_can_include_inherited_members(self) -> None:
        client = FakeClient()
        argv = ["list", "--project", "group/proj", "--include-inherited", "--query", "alice", "--user-ids", "1,2"]
        code, _value = run_and_parse(gl_members, argv, client)
        self.assertEqual(code, 0)
        method, path, params, _body, _kwargs = client.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/projects/group%2Fproj/members/all")
        self.assertEqual(params["query"], "alice")
        self.assertEqual(params["user_ids"], ["1", "2"])

    def test_branch_get_encodes_branch_name(self) -> None:
        client = FakeClient()
        argv = ["get", "--project", "group/proj", "--branch", "feature/demo"]
        code, _value = run_and_parse(gl_branches, argv, client)
        self.assertEqual(code, 0)
        method, path, _params, _body, _kwargs = client.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(path, "/projects/group%2Fproj/repository/branches/feature%2Fdemo")

    def test_issue_template_get_reads_raw_template(self) -> None:
        client = FakeClient()
        argv = ["get", "--project", "group/proj", "--name", "bug", "--ref", "main"]
        code, value = run_and_parse(gl_issue_templates, argv, client)
        self.assertEqual(code, 0)
        method, path, params, _body, kwargs = client.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertIn(".gitlab%2Fissue_templates%2Fbug.md", path)
        self.assertEqual(params["ref"], "main")
        self.assertEqual(kwargs["raw"], True)
        self.assertEqual(value["result"]["content"], "template body")

    def test_issue_template_rejects_nested_name(self) -> None:
        with self.assertRaises(gl_issue_templates.GitLabSkillError):
            gl_issue_templates.normalize_template_name("../bug.md")

    def test_issue_create_dry_run_does_not_send_post(self) -> None:
        client = FakeClient()
        argv = ["create", "--project", "group/proj", "--title", "Demo", "--description", "hello"]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["dry_run"], True)
        self.assertEqual(client.request_calls, [])
        self.assertEqual(client.preview_calls[0][0], "POST")
        self.assertEqual(client.preview_calls[0][3]["title"], "Demo")

    def test_issue_create_prechecks_labels_by_default(self) -> None:
        client = FakeClient()
        argv = ["create", "--project", "group/proj", "--title", "Demo", "--labels", "bug,feature"]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["checked_labels"], ["bug", "feature"])
        self.assertEqual(client.request_calls[0][1], "/projects/group%2Fproj/labels/bug")
        self.assertEqual(client.request_calls[1][1], "/projects/group%2Fproj/labels/feature")
        self.assertEqual(client.preview_calls[0][3]["labels"], "bug,feature")

    def test_issue_create_can_use_template_description(self) -> None:
        client = FakeClient()
        argv = ["create", "--project", "group/proj", "--title", "Demo", "--template", "bug", "--template-ref", "main"]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["description_source"], "template:.gitlab/issue_templates/bug.md@main")
        self.assertEqual(client.preview_calls[0][3]["description"], "template body")

    def test_issue_close_dry_run_does_not_send_put(self) -> None:
        client = FakeClient()
        argv = ["close", "--project", "group/proj", "--iid", "3"]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["dry_run"], True)
        self.assertEqual(client.request_calls, [])
        self.assertEqual(client.preview_calls[0][0], "PUT")
        self.assertEqual(client.preview_calls[0][3]["state_event"], "close")

    def test_issue_update_description_dry_run_uses_description_file(self) -> None:
        client = FakeClient()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("新的 issue 描述")
            description_path = handle.name
        try:
            argv = [
                "update-description",
                "--project",
                "group/proj",
                "--iid",
                "3",
                "--description-file",
                description_path,
            ]
            code, value = run_and_parse(gl_issues, argv, client)
        finally:
            Path(description_path).unlink(missing_ok=True)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["dry_run"], True)
        self.assertEqual(value["result"]["description_source"], "description-file")
        self.assertEqual(client.request_calls, [])
        self.assertEqual(client.preview_calls[0][0], "PUT")
        self.assertEqual(client.preview_calls[0][3]["description"], "新的 issue 描述")

    def test_issue_update_description_confirm_sends_put(self) -> None:
        client = FakeClient()
        argv = [
            "update-description",
            "--project",
            "group/proj",
            "--iid",
            "3",
            "--description",
            "新的 issue 描述",
            "--confirm",
        ]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["sent"], True)
        method, path, _params, body, _kwargs = client.request_calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(path, "/projects/group%2Fproj/issues/3")
        self.assertEqual(body, {"description": "新的 issue 描述"})

    def test_issue_update_description_rejects_empty_description_by_default(self) -> None:
        client = FakeClient()
        argv = ["update-description", "--project", "group/proj", "--iid", "3", "--description", ""]
        with self.assertRaises(gl_issues.GitLabSkillError):
            run_and_parse(gl_issues, argv, client)
        self.assertEqual(client.preview_calls, [])
        self.assertEqual(client.request_calls, [])

    def test_issue_update_description_allows_explicit_empty_description(self) -> None:
        client = FakeClient()
        argv = [
            "update-description",
            "--project",
            "group/proj",
            "--iid",
            "3",
            "--description",
            "",
            "--allow-empty-description",
        ]
        code, value = run_and_parse(gl_issues, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["dry_run"], True)
        self.assertEqual(client.preview_calls[0][3], {"description": ""})

    def test_mr_reopen_confirm_sends_put(self) -> None:
        client = FakeClient()
        argv = ["reopen", "--project", "group/proj", "--iid", "4", "--confirm"]
        code, value = run_and_parse(gl_mrs, argv, client)
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["sent"], True)
        method, path, _params, body, _kwargs = client.request_calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(path, "/projects/group%2Fproj/merge_requests/4")
        self.assertEqual(body["state_event"], "reopen")


if __name__ == "__main__":
    unittest.main()
