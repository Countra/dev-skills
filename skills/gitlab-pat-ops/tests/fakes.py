from __future__ import annotations

import io
import json
import urllib.parse
from types import SimpleNamespace
from unittest import mock


class FakeClient:
    def __init__(self, raw_data: bytes = b"template body") -> None:
        self.config = SimpleNamespace(origin=("https", "gitlab.example.com", 443), token="fake-token")
        self.request_calls: list[tuple[str, str, object, object, dict[str, object]]] = []
        self.last_meta = {"request_id": "fake-request"}
        self.raw_data = raw_data

    def build_url(self, path, params=None):  # noqa: ANN001
        base = path if str(path).startswith("http") else "https://gitlab.example.com/api/v4/" + str(path).lstrip("/")
        if params:
            clean = {key: value for key, value in params.items() if value is not None and value != ""}
            if clean:
                base += "?" + urllib.parse.urlencode(clean, doseq=True)
        return base

    def request(self, method, path, params=None, json_body=None, **kwargs):  # noqa: ANN001
        method = method.upper()
        self.request_calls.append((method, path, params, json_body, kwargs))
        if kwargs.get("raw"):
            return self.raw_data
        if method in {"POST", "PUT"}:
            return {"sent": True, "method": method, "path": path, "json_body": json_body}
        if path == "/user":
            return {"id": 10, "username": "tester", "name": "Tester"}
        if "/namespaces/" in path:
            return {"id": 20, "full_path": "group", "kind": "group"}
        if "/templates/" in path:
            if path.endswith(("/issues", "/merge_requests")):
                return [{"name": "feature"}]
            return {"name": urllib.parse.unquote(path.rsplit("/", 1)[-1]), "content": "template body"}
        if "/repository/branches/" in path:
            return {
                "name": urllib.parse.unquote(path.rsplit("/", 1)[-1]),
                "merged": False,
                "protected": False,
                "default": False,
            }
        if "/labels/" in path:
            return {"id": 30, "name": urllib.parse.unquote(path.rsplit("/", 1)[-1])}
        if "/discussions/" in path:
            return {
                "id": path.rsplit("/", 1)[-1],
                "individual_note": False,
                "notes": [
                    {
                        "id": 60,
                        "body": "private discussion body",
                        "resolvable": True,
                        "resolved": False,
                        "author": {"id": 10},
                    }
                ],
            }
        if "/issues/" in path and not path.endswith(("related_merge_requests", "closed_by")):
            return {
                "id": 40,
                "iid": 3,
                "state": "opened",
                "title": "Issue",
                "updated_at": "2026-07-10T00:00:00Z",
                "description": "old issue description",
                "labels": [],
                "milestone": None,
                "assignees": [],
            }
        if "/merge_requests/" in path and not path.endswith(("/notes", "/pipelines")):
            return {
                "id": 50,
                "iid": 4,
                "state": "opened",
                "title": "MR",
                "updated_at": "2026-07-10T00:00:00Z",
                "description": "old MR description",
                "source_branch": "feature",
                "target_branch": "main",
                "detailed_merge_status": "mergeable",
            }
        if "/projects/" in path and all(
            marker not in path
            for marker in ("/repository/", "/issues", "/merge_requests", "/labels", "/milestones", "/members", "/pipelines", "/jobs", "/templates")
        ):
            return {
                "id": 1,
                "path_with_namespace": "group/proj",
                "archived": False,
                "visibility": "private",
                "default_branch": "main",
            }
        return []

    def paginate(self, path, params=None, **limits):  # noqa: ANN001
        del limits
        value = self.request("GET", path, params=params)
        return value if isinstance(value, list) else [value]


def run_and_parse(module, argv, client: FakeClient):  # noqa: ANN001
    output = io.StringIO()
    with mock.patch.object(module, "make_client", return_value=client):
        with mock.patch("sys.stdout", output):
            code = module.main(argv)
    return code, json.loads(output.getvalue())


def write_calls(client: FakeClient) -> list[tuple[str, str, object, object, dict[str, object]]]:
    return [item for item in client.request_calls if item[0] in {"POST", "PUT"}]
