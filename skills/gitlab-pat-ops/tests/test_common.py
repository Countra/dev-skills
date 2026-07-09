from __future__ import annotations

import os
import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import gitlab_common as common  # noqa: E402


class FakeHeaders(dict):
    def get(self, key, default=None):  # type: ignore[override]
        for item_key, value in self.items():
            if item_key.lower() == key.lower():
                return value
        return default


class FakeResponse:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.headers = FakeHeaders(headers or {})

    def read(self) -> bytes:
        return self.payload


class FakeOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests = []

    def __call__(self, request, timeout=30):  # noqa: ANN001
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class CommonTests(unittest.TestCase):
    def test_load_config_uses_skill_scoped_env(self) -> None:
        env = {
            "SKILL_GITLAB_BASE_URL": "https://gitlab.example.com",
            "SKILL_GITLAB_PAT": "secret-token",
            "GITLAB_TOKEN": "ignored-token",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = common.load_config()
        self.assertEqual(config.base_url, "https://gitlab.example.com")
        self.assertEqual(config.api_url, "https://gitlab.example.com/api/v4")
        self.assertEqual(config.token_source, "SKILL_GITLAB_PAT")
        self.assertEqual(config.token, "secret-token")

    def test_missing_env_reports_skill_names(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(common.MissingEnvironmentError) as raised:
                common.load_config()
        message = str(raised.exception)
        self.assertIn("SKILL_GITLAB_BASE_URL", message)
        self.assertIn("SKILL_GITLAB_PAT", message)

    def test_request_adds_private_token_header(self) -> None:
        config = common.GitLabConfig(
            base_url="https://gitlab.example.com",
            api_url="https://gitlab.example.com/api/v4",
            token="secret-token",
            token_source="SKILL_GITLAB_PAT",
        )
        opener = FakeOpener([FakeResponse(b'{"id":1}')])
        client = common.GitLabClient(config=config, opener=opener, sleep=lambda _: None)
        result = client.request("GET", "/user")
        request, timeout = opener.requests[0]
        self.assertEqual(result, {"id": 1})
        self.assertEqual(timeout, common.DEFAULT_TIMEOUT)
        self.assertEqual(request.headers["Private-token"], "secret-token")

    def test_paginate_follows_link_header(self) -> None:
        config = common.GitLabConfig("https://gitlab.example.com", "https://gitlab.example.com/api/v4", "tok", "env")
        first_headers = {"Link": '<https://gitlab.example.com/api/v4/projects?page=2>; rel="next"'}
        opener = FakeOpener([FakeResponse(b'[{"id":1}]', first_headers), FakeResponse(b'[{"id":2}]')])
        client = common.GitLabClient(config=config, opener=opener, sleep=lambda _: None)
        result = client.paginate("/projects")
        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(len(opener.requests), 2)

    def test_preview_summarizes_sensitive_body(self) -> None:
        config = common.GitLabConfig("https://gitlab.example.com", "https://gitlab.example.com/api/v4", "tok", "env")
        client = common.GitLabClient(config=config, opener=FakeOpener([]), sleep=lambda _: None)
        preview = client.preview("POST", "/notes", None, {"body": "x" * 120, "title": "T"})
        self.assertEqual(preview["json_body"]["body"]["length"], 120)
        self.assertEqual(preview["json_body"]["title"], "T")

    def test_parse_int_csv_rejects_invalid_value(self) -> None:
        self.assertEqual(common.parse_int_csv("1, 2", "assignee_ids"), [1, 2])
        with self.assertRaises(common.GitLabSkillError):
            common.parse_int_csv("1,x", "assignee_ids")

    def test_validate_yyyy_mm_dd(self) -> None:
        self.assertEqual(common.validate_yyyy_mm_dd("2026-07-09", "due_date"), "2026-07-09")
        with self.assertRaises(common.GitLabSkillError):
            common.validate_yyyy_mm_dd("2026/07/09", "due_date")

    def test_read_optional_text_from_args_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("hello")
            body_path = handle.name
        try:
            args = argparse.Namespace(description=None, description_file=body_path, stdin=False)
            value, source = common.read_optional_text_from_args(
                args,
                "description",
                "description_file",
                "stdin",
                "描述",
            )
        finally:
            Path(body_path).unlink(missing_ok=True)
        self.assertEqual(value, "hello")
        self.assertEqual(source, "description-file")


if __name__ == "__main__":
    unittest.main()
