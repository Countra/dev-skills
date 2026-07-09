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
            code = gl_capabilities.main(["--section", "not-supported"])
        value = json.loads(output.getvalue())
        unsupported = value["result"]["not_supported"]
        self.assertEqual(code, 0)
        self.assertEqual(value["result"]["skill"]["name"], "gitlab-pat-ops")
        self.assertTrue(any(item["capability"] == "create_issue" for item in unsupported))

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


if __name__ == "__main__":
    unittest.main()
