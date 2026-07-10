from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory  # noqa: E402
from process_manager.client import ManagerClient  # noqa: E402
from process_manager.control_api import ControlServer  # noqa: E402
from process_manager.errors import ManagerOfflineError  # noqa: E402
from process_manager.runtime import (  # noqa: E402
    build_manager_identity,
    initialize_runtime,
    read_token,
    write_manager_identity,
)


class FakeManager:
    def __init__(self) -> None:
        self.instance_id = "control-instance"

    def health(self):  # noqa: ANN201
        return {
            "managerReady": True,
            "supervisorReady": True,
            "instance": {"id": self.instance_id},
            "endpointHealthy": True,
        }

    def doctor(self):  # noqa: ANN201
        return {**self.health(), "diagnostics": {"platform": "test"}}

    def list_processes(self, *, include_history=False):  # noqa: ANN001,ANN201
        return {"active": {}, "running": {}, "history": include_history}

    def status(self, **kwargs):  # noqa: ANN003,ANN201
        return kwargs

    def start(self, path):  # noqa: ANN001,ANN201
        return {"service": str(path), "state": "running"}

    def stop(self, **kwargs):  # noqa: ANN003,ANN201
        return {**kwargs, "state": "stopped", "cleanupVerified": True}

    def ready(self, **kwargs):  # noqa: ANN003,ANN201
        return {**kwargs, "ready": True}

    def logs(self, **kwargs):  # noqa: ANN003,ANN201
        return {**kwargs, "lines": []}

    def restart(self, path, **kwargs):  # noqa: ANN001,ANN003,ANN201
        return {"service": str(path), **kwargs}

    def prune(self, **kwargs):  # noqa: ANN003,ANN201
        return kwargs

    def shutdown(self):  # noqa: ANN201
        return {"cleanupVerified": True}


class StaticResponse:
    status = 200

    def __init__(self, value):  # noqa: ANN001
        self.body = json.dumps(value).encode("utf-8")

    def read(self, size=-1):  # noqa: ANN001,ANN201
        return self.body[:size] if size >= 0 else self.body

    def close(self) -> None:
        return


class StaticOpener:
    def __init__(self, value):  # noqa: ANN001
        self.value = value

    def open(self, request, timeout):  # noqa: ANN001,ANN201
        del request, timeout
        return StaticResponse(self.value)


class ControlApiTests(unittest.TestCase):
    def test_client_requires_response_instance_identity(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                instance_id="expected-instance",
                port=43210,
                bootstrap_backend="test",
                bootstrap_selection_reason="test fixture",
            )
            write_manager_identity(config, adapter, identity)
            for meta in ({}, {"managerInstanceId": "other-instance"}):
                with self.subTest(meta=meta):
                    client = ManagerClient(
                        config,
                        adapter,
                        opener=StaticOpener({"ok": True, "operation": "health", "data": {}, "meta": meta}),
                    )
                    with self.assertRaises(ManagerOfflineError):
                        client.request("GET", "/health")

    def test_client_auth_instance_and_request_budget(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            token = read_token(config, adapter)
            manager = FakeManager()
            server = ControlServer(("127.0.0.1", 0), manager, token, 128)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                identity = build_manager_identity(
                    config,
                    adapter,
                    instance_id=manager.instance_id,
                    port=int(server.server_address[1]),
                    bootstrap_backend="test",
                    bootstrap_selection_reason="test fixture",
                )
                write_manager_identity(config, adapter, identity)
                client = ManagerClient(config, adapter, timeout=2)
                status, value = client.request("GET", "/health")
                self.assertEqual(status, 200)
                self.assertTrue(value["ok"])
                self.assertNotIn("platform", json.dumps(value["data"]))

                status, value = client.request(
                    "POST",
                    "/processes/ready",
                    {"service": "demo", "processKey": None, "timeoutSeconds": 1},
                )
                self.assertEqual(status, 200)
                self.assertTrue(value["data"]["ready"])
                status, value = client.request(
                    "GET",
                    "/processes/logs",
                    params={"service": "demo", "stream": "stdout", "tail": 5, "maxBytes": 1024},
                )
                self.assertEqual(status, 200)
                self.assertEqual(value["data"]["lines"], [])
                status, value = client.request(
                    "POST",
                    "/processes/prune",
                    {"dryRun": True, "maxInactive": 2, "keepRuns": False},
                )
                self.assertEqual(status, 200)
                self.assertTrue(value["data"]["dry_run"])

                url = f"http://127.0.0.1:{server.server_address[1]}/health"
                with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                    urllib.request.urlopen(url, timeout=2)
                self.assertEqual(unauthorized.exception.code, 401)

                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/processes/start",
                    data=b"x" * 129,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as oversized:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(oversized.exception.code, 400)

                manager.instance_id = "different-instance"
                with self.assertRaises(ManagerOfflineError):
                    client.request("GET", "/health")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
