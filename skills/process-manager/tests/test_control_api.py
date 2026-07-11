from __future__ import annotations

import json
import sys
import threading
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import FakeAdapter, create_config, workspace_directory  # noqa: E402
from process_manager.client import ManagerClient  # noqa: E402
from process_manager.control_api import ControlHandler, ControlServer  # noqa: E402
from process_manager.errors import ManagerOfflineError, RequestError  # noqa: E402
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
    def test_control_server_bind_does_not_resolve_host_name(self) -> None:
        manager = FakeManager()
        with mock.patch("http.server.socket.getfqdn", side_effect=AssertionError("DNS lookup")):
            server = ControlServer(("127.0.0.1", 0), manager, "token", 128)
        try:
            self.assertEqual(server.server_name, "127.0.0.1")
            self.assertGreater(server.server_port, 0)
        finally:
            server.server_close()

    def test_shutdown_schedules_server_stop_after_response(self) -> None:
        events: list[str] = []
        manager = FakeManager()
        manager.shutdown = lambda: events.append("manager") or {"cleanupVerified": True}  # type: ignore[method-assign]
        server = types.SimpleNamespace(manager=manager, shutdown=lambda: events.append("server"))
        handler = object.__new__(ControlHandler)
        handler.server = server
        handler.path = "/shutdown"
        handler._deny_unless_authorized = lambda: False  # type: ignore[method-assign]
        handler._read_body = lambda: {}  # type: ignore[method-assign]
        handler._send = lambda status, value: events.append("response")  # type: ignore[method-assign]

        class ImmediateThread:
            def __init__(self, *, target, daemon):  # noqa: ANN001
                del daemon
                self.target = target

            def start(self) -> None:
                self.target()

        with mock.patch("process_manager.control_api.threading.Thread", ImmediateThread):
            handler.do_POST()
        self.assertEqual(events, ["manager", "response", "server"])

    def test_shutdown_error_does_not_stop_control_server(self) -> None:
        events: list[str] = []
        manager = FakeManager()

        def fail_shutdown():  # noqa: ANN202
            events.append("manager")
            raise RequestError("shutdown failed")

        manager.shutdown = fail_shutdown  # type: ignore[method-assign]
        server = types.SimpleNamespace(manager=manager, shutdown=lambda: events.append("server"))
        handler = object.__new__(ControlHandler)
        handler.server = server
        handler.path = "/shutdown"
        handler._deny_unless_authorized = lambda: False  # type: ignore[method-assign]
        handler._read_body = lambda: {}  # type: ignore[method-assign]
        handler._send = lambda status, value: events.append("response")  # type: ignore[method-assign]
        handler.do_POST()
        self.assertEqual(events, ["manager", "response"])

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
