from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from gitlab_ops import (  # noqa: E402
    ConflictError,
    GitLabApiError,
    GitLabClient,
    GitLabConfig,
    MissingEnvironmentError,
    NetworkError,
    ResponseLimitError,
    UnsafeUrlError,
    execute_guarded_write,
    load_config,
    normalize_api_url,
    parse_bool,
    parse_int_csv,
    read_optional_text_from_args,
    resource_snapshot,
    validate_iso8601,
    validate_yyyy_mm_dd,
)
from gitlab_ops.transport import SameOriginRedirectHandler  # noqa: E402


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
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[tuple[object, int]] = []

    def __call__(self, request, timeout=30):  # noqa: ANN001
        self.requests.append((request, timeout))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def make_config(token: str = "secret-token") -> GitLabConfig:
    return GitLabConfig(
        base_url="https://gitlab.example.com",
        api_url="https://gitlab.example.com/api/v4",
        api_path="/api/v4",
        token=token,
    )


def http_error(status: int, body: bytes = b'{"message":"failed"}') -> urllib.error.HTTPError:
    headers = FakeHeaders({"X-Request-Id": "request-1"})
    return urllib.error.HTTPError("https://gitlab.example.com/api/v4/projects", status, "failed", headers, io.BytesIO(body))


class CommonTests(unittest.TestCase):
    def test_load_config_uses_only_current_skill_env(self) -> None:
        env = {
            "SKILL_GITLAB_BASE_URL": "https://gitlab.example.com/root",
            "SKILL_GITLAB_PAT": "secret-token",
            "SKILL_GITLAB_TOKEN": "ignored-old-alias",
            "GITLAB_TOKEN": "ignored-generic-token",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()
        self.assertEqual(config.api_url, "https://gitlab.example.com/root/api/v4")
        self.assertEqual(config.token_source, "SKILL_GITLAB_PAT")
        self.assertEqual(config.token, "secret-token")

    def test_old_token_alias_does_not_satisfy_configuration(self) -> None:
        env = {
            "SKILL_GITLAB_BASE_URL": "https://gitlab.example.com",
            "SKILL_GITLAB_TOKEN": "old-alias",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(MissingEnvironmentError):
                load_config()

    def test_normalize_url_rejects_credentials_query_and_plain_http(self) -> None:
        for value in (
            "https://user:pass@gitlab.example.com",
            "https://gitlab.example.com?token=x",
            "https://gitlab.example.com/#fragment",
            "http://gitlab.example.com",
        ):
            with self.subTest(value=value):
                with self.assertRaises(Exception):
                    normalize_api_url(value)
        base, api = normalize_api_url("http://127.0.0.1:8080/gitlab")
        self.assertEqual(base, "http://127.0.0.1:8080/gitlab")
        self.assertEqual(api, "http://127.0.0.1:8080/gitlab/api/v4")
        with self.assertRaises(Exception):
            normalize_api_url("https://gitlab.example.com:invalid")

    def test_request_adds_pat_and_bounded_metadata(self) -> None:
        response = FakeResponse(b'{"id":1}', {"X-Request-Id": "req-1", "RateLimit-Remaining": "99"})
        opener = FakeOpener([response])
        client = GitLabClient(config=make_config(), opener=opener, sleep=lambda _: None)
        result = client.request("GET", "/user")
        request, timeout = opener.requests[0]
        self.assertEqual(result, {"id": 1})
        self.assertEqual(timeout, 30)
        self.assertEqual(request.headers["Private-token"], "secret-token")
        self.assertEqual(client.last_meta["request_id"], "req-1")
        self.assertTrue(response.closed)

    def test_success_json_and_preview_redact_current_pat(self) -> None:
        opener = FakeOpener([FakeResponse(b'{"value":"prefix secret-token suffix"}')])
        client = GitLabClient(config=make_config(), opener=opener)
        self.assertEqual(client.request("GET", "/user"), {"value": "prefix ***redacted*** suffix"})
        preview = client.preview(
            "POST",
            "/projects",
            {"search": "secret-token"},
            {"name": "secret-token"},
            target={"name": "secret-token"},
        )
        self.assertNotIn("secret-token", str(preview))

    def test_cross_origin_link_is_rejected_before_second_request(self) -> None:
        headers = {"Link": '<https://evil.example/api/v4/projects?page=2>; rel="next"'}
        opener = FakeOpener([FakeResponse(b'[{"id":1}]', headers)])
        client = GitLabClient(config=make_config(), opener=opener, sleep=lambda _: None)
        with self.assertRaises(UnsafeUrlError):
            client.paginate("/projects")
        self.assertEqual(len(opener.requests), 1)

    def test_redirects_are_limited_to_safe_same_origin_reads(self) -> None:
        handler = SameOriginRedirectHandler(make_config())
        read_request = urllib.request.Request(
            "https://gitlab.example.com/api/v4/projects",
            headers={"PRIVATE-TOKEN": "secret-token"},
            method="GET",
        )
        with self.assertRaises(UnsafeUrlError):
            handler.redirect_request(
                read_request,
                None,
                302,
                "Found",
                FakeHeaders(),
                "https://evil.example/api/v4/projects",
            )
        write_request = urllib.request.Request(
            "https://gitlab.example.com/api/v4/projects",
            data=b"{}",
            headers={"PRIVATE-TOKEN": "secret-token"},
            method="POST",
        )
        with self.assertRaises(UnsafeUrlError):
            handler.redirect_request(
                write_request,
                None,
                307,
                "Temporary Redirect",
                FakeHeaders(),
                "https://gitlab.example.com/api/v4/projects/1",
            )

    def test_same_origin_pagination_obeys_item_budget(self) -> None:
        headers = {"Link": '<https://gitlab.example.com/api/v4/projects?page=2>; rel="next"'}
        opener = FakeOpener([FakeResponse(b'[{"id":1}]', headers), FakeResponse(b'[{"id":2}]')])
        client = GitLabClient(config=make_config(), opener=opener, sleep=lambda _: None)
        self.assertEqual(client.paginate("/projects", max_items=2), [{"id": 1}, {"id": 2}])
        self.assertEqual(client.last_meta["pagination"]["pages"], 2)
        self.assertEqual(client.last_meta["pagination"]["items"], 2)
        opener = FakeOpener([FakeResponse(b'[{"id":1}]', headers), FakeResponse(b'[{"id":2}]')])
        client = GitLabClient(config=make_config(), opener=opener, sleep=lambda _: None)
        with self.assertRaises(ResponseLimitError):
            client.paginate("/projects", max_items=1)

        client = GitLabClient(
            config=make_config(),
            opener=FakeOpener([FakeResponse(b'{"id":1}')]),
            sleep=lambda _: None,
        )
        with self.assertRaises(NetworkError):
            client.paginate("/projects")

    def test_write_request_never_retries_http_or_network_failure(self) -> None:
        opener = FakeOpener([http_error(503), FakeResponse(b'{"id":1}')])
        client = GitLabClient(config=make_config(), opener=opener, sleep=lambda _: None)
        with self.assertRaises(GitLabApiError) as raised:
            client.request("POST", "/projects", json_body={"name": "demo"})
        self.assertEqual(raised.exception.request_id, "request-1")
        self.assertEqual(raised.exception.outcome, "unknown")
        self.assertFalse(raised.exception.retryable)
        self.assertIn("禁止直接重放", raised.exception.guidance)
        self.assertEqual(client.last_meta["request_id"], "request-1")
        self.assertEqual(len(opener.requests), 1)

        opener = FakeOpener([urllib.error.URLError("connection reset"), FakeResponse(b'{"id":1}')])
        client = GitLabClient(config=make_config(), opener=opener, sleep=lambda _: None)
        with self.assertRaises(NetworkError) as raised:
            client.request("PUT", "/projects/1", json_body={"name": "demo"})
        self.assertEqual(raised.exception.outcome, "unknown")
        self.assertIn("禁止直接重放", raised.exception.guidance)
        self.assertEqual(len(opener.requests), 1)

    def test_ambiguous_write_responses_require_read_before_replay(self) -> None:
        cases = (
            (FakeResponse(b"not-json", {"X-Request-Id": "invalid-json"}), 1024),
            (FakeResponse(b"x" * 32, {"X-Request-Id": "too-large"}), 16),
        )
        for response, max_bytes in cases:
            with self.subTest(request_id=response.headers["X-Request-Id"]):
                client = GitLabClient(
                    config=make_config(),
                    opener=FakeOpener([response]),
                    max_response_bytes=max_bytes,
                )
                with self.assertRaises(NetworkError) as raised:
                    client.request("POST", "/projects", json_body={"name": "demo"})
                self.assertEqual(raised.exception.outcome, "unknown")
                self.assertFalse(raised.exception.retryable)
                self.assertIn("禁止直接重放", raised.exception.guidance)

        client = GitLabClient(config=make_config(), opener=FakeOpener([http_error(422)]))
        with self.assertRaises(GitLabApiError) as raised:
            client.request("PUT", "/projects/1/issues/2", json_body={"title": "demo"})
        self.assertEqual(raised.exception.outcome, "rejected")
        self.assertIsNone(raised.exception.guidance)

    def test_request_body_budget_rejects_before_network(self) -> None:
        opener = FakeOpener([FakeResponse(b'{"id":1}')])
        client = GitLabClient(config=make_config(), opener=opener, max_request_bytes=16)
        with self.assertRaises(ResponseLimitError):
            client.request("POST", "/projects", json_body={"description": "x" * 100})
        self.assertEqual(opener.requests, [])

    def test_safe_read_retries_within_budget(self) -> None:
        opener = FakeOpener([http_error(503), FakeResponse(b'{"id":1}')])
        sleeps: list[float] = []
        client = GitLabClient(
            config=make_config(),
            opener=opener,
            sleep=sleeps.append,
            random_value=lambda: 0.0,
        )
        self.assertEqual(client.request("GET", "/projects/1"), {"id": 1})
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(len(sleeps), 1)

        now = [0.0]
        sleeps = []

        def bounded_sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        opener = FakeOpener([http_error(503), http_error(503), http_error(503), FakeResponse(b'{"id":1}')])
        client = GitLabClient(
            config=make_config(),
            opener=opener,
            max_attempts=3,
            sleep=bounded_sleep,
            clock=lambda: now[0],
            random_value=lambda: 0.0,
        )
        with self.assertRaises(GitLabApiError):
            client.request("GET", "/projects/1")
        self.assertEqual(len(opener.requests), 3)
        self.assertLessEqual(sum(sleeps), client.retry_budget_seconds)

    def test_response_size_is_checked_even_without_content_length(self) -> None:
        opener = FakeOpener([FakeResponse(b"x" * 11)])
        client = GitLabClient(config=make_config(), opener=opener, max_response_bytes=10)
        with self.assertRaises(ResponseLimitError):
            client.request("GET", "/projects", raw=True)

    def test_preview_hashes_body_and_requires_exact_confirmation(self) -> None:
        opener = FakeOpener([FakeResponse(b'{"id":1}')])
        client = GitLabClient(config=make_config(), opener=opener)
        kwargs = {
            "operation": "issues.create",
            "method": "POST",
            "path": "/projects/1/issues",
            "params": None,
            "json_body": {"title": "Demo", "description": "private text"},
            "target": {"project": 1},
            "preflight": {"project_id": 1},
        }
        preview = execute_guarded_write(client, confirm=None, **kwargs)
        self.assertNotIn("private text", str(preview))
        self.assertTrue(preview["confirm_fingerprint"].startswith("sha256:"))
        with self.assertRaises(ConflictError):
            execute_guarded_write(client, confirm="sha256:wrong", **kwargs)
        applied = execute_guarded_write(client, confirm=preview["confirm_fingerprint"], **kwargs)
        self.assertTrue(applied["applied"])

    def test_guard_rejects_apply_time_preflight_drift_before_write(self) -> None:
        opener = FakeOpener([FakeResponse(b'{"id":1}')])
        client = GitLabClient(config=make_config(), opener=opener)
        kwargs = {
            "operation": "issues.close",
            "method": "PUT",
            "path": "/projects/1/issues/2",
            "params": None,
            "json_body": {"state_event": "close"},
            "target": {"project": 1, "iid": 2},
            "preflight": {"state": "opened", "updated_at": "before"},
        }
        preview = execute_guarded_write(client, confirm=None, **kwargs)
        with self.assertRaises(ConflictError):
            execute_guarded_write(
                client,
                confirm=preview["confirm_fingerprint"],
                reread_preflight=lambda: {"state": "opened", "updated_at": "after"},
                **kwargs,
            )
        self.assertEqual(opener.requests, [])

    def test_resource_snapshot_compacts_nested_private_metadata(self) -> None:
        class SnapshotClient:
            def request(self, method, path):  # noqa: ANN001
                del method, path
                return {
                    "id": 1,
                    "iid": 2,
                    "state": "opened",
                    "title": "Issue",
                    "updated_at": "2026-07-10T00:00:00Z",
                    "description": "private description",
                    "labels": ["bug"],
                    "milestone": {"id": 3, "description": "private milestone"},
                    "assignees": [{"id": 4, "email": "private@example.com"}],
                    "reviewers": [{"id": 5, "name": "Private Reviewer"}],
                }

        value = resource_snapshot(SnapshotClient(), "issue", "group/proj", 2)
        serialized = str(value)
        self.assertEqual(value["milestone_id"], 3)
        self.assertEqual(value["assignee_ids"], [4])
        self.assertEqual(value["reviewer_ids"], [5])
        self.assertIn("description_sha256", value)
        self.assertNotIn("private", serialized.lower())

    def test_text_and_scalar_parsers(self) -> None:
        self.assertEqual(parse_int_csv("1, 2", "assignee_ids"), [1, 2])
        with self.assertRaises(Exception):
            parse_int_csv("1,x", "assignee_ids")
        self.assertEqual(validate_yyyy_mm_dd("2026-07-09", "due_date"), "2026-07-09")
        self.assertEqual(validate_iso8601("2026-07-09T12:30:00Z", "updated_after"), "2026-07-09T12:30:00Z")
        self.assertIs(parse_bool("false", "confidential"), False)
        with self.assertRaises(Exception):
            parse_bool("sometimes", "confidential")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("hello")
            body_path = handle.name
        try:
            args = type("Args", (), {"description": None, "description_file": body_path, "stdin": False})()
            value, source = read_optional_text_from_args(args, "description", "description_file", "stdin", "描述")
        finally:
            Path(body_path).unlink(missing_ok=True)
        self.assertEqual((value, source), ("hello", "description-file"))


if __name__ == "__main__":
    unittest.main()
