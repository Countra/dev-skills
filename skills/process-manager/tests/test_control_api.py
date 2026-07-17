from __future__ import annotations

import json
import socket
import sys
import threading
import time
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
from process_manager.errors import (  # noqa: E402
    ControlTimeoutError,
    ManagerOfflineError,
    ManagerUnresponsiveError,
    RequestError,
    RuntimeCorruptError,
    StateError,
)
from process_manager.runtime import (  # noqa: E402
    build_manager_identity,
    initialize_runtime,
    read_token,
    write_manager_identity,
)
from process_manager.protocol import verify_control_busy  # noqa: E402


class FakeManager:
    def __init__(self) -> None:
        self.instance_id = "control-instance"
        self.operation_id = "00000000000000000000000000000000"
        self.runtime_fingerprint = "a" * 64

    def health(self):  # noqa: ANN201
        return {
            "managerReady": True,
            "supervisorReady": True,
            "instance": {"id": self.instance_id},
            "operationId": self.operation_id,
            "runtimeFingerprint": self.runtime_fingerprint,
            "endpointHealthy": True,
        }

    def doctor(self):  # noqa: ANN201
        return {**self.health(), "diagnostics": {"platform": "test"}}

    def list_processes(self, *, include_history=False):  # noqa: ANN001,ANN201
        return {"active": {}, "running": {}, "history": include_history}

    def status(self, **kwargs):  # noqa: ANN003,ANN201
        return kwargs

    def start(self, path, **kwargs):  # noqa: ANN001,ANN003,ANN201
        return {"service": str(path), "state": "running", **kwargs}

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

    def open_session(self, **kwargs):  # noqa: ANN003,ANN201
        return {"sessionId": "1" * 32, **kwargs}

    def renew_session(self, session_id, **kwargs):  # noqa: ANN001,ANN003,ANN201
        return {"sessionId": session_id, **kwargs}

    def session_status(self, session_id):  # noqa: ANN001,ANN201
        return {"sessionId": session_id, "state": "open"}

    def close_session(self, session_id):  # noqa: ANN001,ANN201
        return {"sessionId": session_id, "state": "closed", "workGeneration": 1}

    def shutdown(self):  # noqa: ANN201
        return {"cleanupVerified": True}

    def accept_shutdown(self, *, operation_id=None, timeout_seconds=30):  # noqa: ANN001,ANN201
        del timeout_seconds
        return {"shutdownAccepted": True, "operationId": operation_id}


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
        manager.accept_shutdown = (  # type: ignore[method-assign]
            lambda *, operation_id=None, timeout_seconds=None: events.append("accepted")
            or {"shutdownAccepted": True, "operationId": operation_id}
        )
        manager.shutdown = lambda: events.append("manager") or {"cleanupVerified": True}  # type: ignore[method-assign]
        server = types.SimpleNamespace(manager=manager, shutdown=lambda: events.append("server"))

        def begin_shutdown() -> None:
            try:
                manager.shutdown()
            finally:
                server.shutdown()

        server.begin_shutdown = begin_shutdown
        server.defer_shutdown = lambda request, deadline: events.append("deferred")
        handler = object.__new__(ControlHandler)
        handler.server = server
        handler.request = object()
        handler.path = "/shutdown"
        handler._deny_unless_authorized = lambda: False  # type: ignore[method-assign]
        handler._read_body = lambda: {  # type: ignore[method-assign]
            "operationId": "0" * 32,
            "timeoutSeconds": 2.0,
        }
        handler._send = lambda status, value: events.append("response") or True  # type: ignore[method-assign]

        handler.do_POST()
        self.assertEqual(events, ["accepted", "response", "deferred"])
        server.begin_shutdown()
        self.assertEqual(events, ["accepted", "response", "deferred", "manager", "server"])

    def test_control_server_hands_off_only_after_request_thread_release(self) -> None:
        events: list[str] = []
        server = ControlServer(("127.0.0.1", 0), FakeManager(), "token", 128)
        request = object()
        server.defer_shutdown(request, time.monotonic() + 1)
        try:
            with (
                mock.patch(
                    "socketserver.ThreadingMixIn.process_request_thread",
                    side_effect=lambda *_: events.append("released"),
                ),
                mock.patch.object(server, "begin_shutdown", side_effect=lambda: events.append("coordinator")),
            ):
                server.process_request_thread(request, ("127.0.0.1", 10000))
        finally:
            server.server_close()
        self.assertEqual(events, ["released", "coordinator"])

    def test_control_server_hands_off_when_request_release_raises(self) -> None:
        events: list[str] = []
        server = ControlServer(("127.0.0.1", 0), FakeManager(), "token", 128)
        request = mock.Mock()
        self.assertTrue(server._request_gate.acquire(request))  # noqa: SLF001
        server.defer_shutdown(request, time.monotonic() + 1)
        try:
            with (
                mock.patch(
                    "socketserver.ThreadingMixIn.process_request_thread",
                    side_effect=RuntimeError("release failed"),
                ),
                mock.patch.object(server, "begin_shutdown", side_effect=lambda: events.append("coordinator")),
                self.assertRaisesRegex(RuntimeError, "release failed"),
            ):
                server.process_request_thread(request, ("127.0.0.1", 10000))
        finally:
            server.server_close()
        self.assertEqual(events, ["coordinator"])
        self.assertEqual(server._request_gate.active_count(), 0)  # noqa: SLF001

    def test_shutdown_coordinator_stops_intake_drains_then_cleans_manager(self) -> None:
        events: list[str] = []
        drain_timeouts: list[float] = []
        manager = FakeManager()
        manager.shutdown = lambda: events.append("manager") or {"cleanupVerified": True}  # type: ignore[method-assign]
        server = ControlServer(("127.0.0.1", 0), manager, "token", 128)
        server._shutdown_deadline = time.monotonic() + 0.5  # noqa: SLF001
        try:
            with (
                mock.patch.object(server, "shutdown", side_effect=lambda: events.append("intake")),
                mock.patch.object(
                    server._request_gate, "drain",  # noqa: SLF001
                    side_effect=lambda timeout: drain_timeouts.append(timeout)
                    or events.append("drain") or True,
                ),
            ):
                server.begin_shutdown()
                self.assertTrue(server.wait_for_shutdown(timeout=1))
            self.assertEqual(events, ["intake", "drain", "manager"])
            self.assertTrue(0 < drain_timeouts[0] <= 0.5)
            self.assertEqual(server.shutdown_result, {"cleanupVerified": True})
        finally:
            server.server_close()

    def test_slow_header_saturates_before_thread_creation_and_returns_signed_busy(self) -> None:
        manager = FakeManager()
        manager.config = types.SimpleNamespace(limits={"maxConcurrentControlRequests": 1})
        token = "bounded-control-token"
        server = ControlServer(("127.0.0.1", 0), manager, token, 128)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        first = second = None
        try:
            address = ("127.0.0.1", int(server.server_address[1]))
            first = socket.create_connection(address, timeout=2)
            first.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n")
            deadline = time.monotonic() + 2
            while server._request_gate.active_count() != 1 and time.monotonic() < deadline:  # noqa: SLF001
                time.sleep(0.01)
            self.assertEqual(server._request_gate.active_count(), 1)  # noqa: SLF001
            second = socket.create_connection(address, timeout=2)
            second.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = second.recv(65536)
            self.assertIn(b"503 Service Unavailable", response)
            envelope = json.loads(response.split(b"\r\n\r\n", 1)[1])
            verify_control_busy(envelope, token, manager.instance_id)
            self.assertEqual(server._request_gate.active_count(), 1)  # noqa: SLF001
        finally:
            if first is not None:
                try:
                    first.sendall(b"\r\n")
                    first.recv(65536)
                except OSError:
                    pass
                first.close()
            if second is not None:
                second.close()
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.assertEqual(server._request_gate.active_count(), 0)  # noqa: SLF001

    def test_slow_body_saturates_before_second_handler_thread(self) -> None:
        manager = FakeManager()
        manager.config = types.SimpleNamespace(limits={"maxConcurrentControlRequests": 1})
        token = "slow-body-token"
        server = ControlServer(("127.0.0.1", 0), manager, token, 128)
        server._request_gate.timeout = 0.5  # noqa: SLF001
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        first = second = None
        try:
            address = ("127.0.0.1", int(server.server_address[1]))
            first = socket.create_connection(address, timeout=2)
            first.sendall(
                b"POST /sessions/open HTTP/1.1\r\nHost: localhost\r\n"
                + f"Authorization: Bearer {token}\r\n".encode("ascii")
                + b"Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"
            )
            deadline = time.monotonic() + 2
            while server._request_gate.active_count() != 1 and time.monotonic() < deadline:  # noqa: SLF001
                time.sleep(0.01)
            second = socket.create_connection(address, timeout=2)
            second.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            response = second.recv(65536)
            self.assertIn(b"503 Service Unavailable", response)
            verify_control_busy(
                json.loads(response.split(b"\r\n\r\n", 1)[1]),
                token,
                manager.instance_id,
            )
            self.assertIn(b"408 Request Timeout", first.recv(65536))
        finally:
            if first is not None:
                first.close()
            if second is not None:
                second.close()
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        deadline = time.monotonic() + 2
        while server._request_gate.active_count() and time.monotonic() < deadline:  # noqa: SLF001
            time.sleep(0.01)
        self.assertEqual(server._request_gate.active_count(), 0)  # noqa: SLF001

    def test_shutdown_rejects_null_operation_id(self) -> None:
        with self.assertRaisesRegex(RequestError, "canonical UUID"):
            ControlHandler._operation_id(None)  # noqa: SLF001

    def test_request_body_timeout_uses_closed_control_error(self) -> None:
        handler = object.__new__(ControlHandler)
        handler.headers = {"Content-Length": "2"}
        handler.server = types.SimpleNamespace(max_request_bytes=128)
        handler.rfile = mock.Mock()
        handler.rfile.read.side_effect = TimeoutError("fixture")
        with self.assertRaises(ControlTimeoutError) as raised:
            handler._read_body()  # noqa: SLF001
        self.assertEqual(raised.exception.code, "control_timeout")

    def test_request_body_rejects_truncated_content_length(self) -> None:
        handler = object.__new__(ControlHandler)
        handler.headers = {"Content-Length": "4"}
        handler.server = types.SimpleNamespace(max_request_bytes=128)
        handler.rfile = mock.Mock()
        handler.rfile.read.return_value = b"{}"
        with self.assertRaisesRegex(RequestError, "Content-Length"):
            handler._read_body()  # noqa: SLF001

    def test_response_disconnect_returns_unflushed_without_retrying(self) -> None:
        handler = object.__new__(ControlHandler)
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        handler.wfile = mock.Mock()
        handler.wfile.write.side_effect = BrokenPipeError("fixture")
        self.assertFalse(handler._send(200, {"ok": True}))  # noqa: SLF001
        handler.wfile.write.assert_called_once()

    def test_acquire_failure_closes_request(self) -> None:
        server = ControlServer(("127.0.0.1", 0), FakeManager(), "token", 128)
        request = mock.Mock()
        try:
            with (
                mock.patch.object(
                    server._request_gate, "acquire", side_effect=StateError("fixture")  # noqa: SLF001
                ),
                mock.patch.object(server, "shutdown_request") as shutdown,
                self.assertRaisesRegex(StateError, "fixture"),
            ):
                server.process_request(request, ("127.0.0.1", 10000))
            shutdown.assert_called_once_with(request)
        finally:
            server.server_close()

    def test_shutdown_error_still_stops_control_server_after_ack(self) -> None:
        events: list[str] = []
        manager = FakeManager()
        manager.accept_shutdown = (  # type: ignore[method-assign]
            lambda *, operation_id=None, timeout_seconds=None: events.append("accepted")
            or {"shutdownAccepted": True, "operationId": operation_id}
        )

        def fail_shutdown():  # noqa: ANN202
            events.append("manager")
            raise RequestError("shutdown failed")

        manager.shutdown = fail_shutdown  # type: ignore[method-assign]
        server = types.SimpleNamespace(manager=manager, shutdown=lambda: events.append("server"))

        def begin_shutdown() -> None:
            try:
                manager.shutdown()
            except RequestError:
                pass
            finally:
                server.shutdown()

        server.begin_shutdown = begin_shutdown
        server.defer_shutdown = lambda request, deadline: events.append("deferred")
        handler = object.__new__(ControlHandler)
        handler.server = server
        handler.request = object()
        handler.path = "/shutdown"
        handler._deny_unless_authorized = lambda: False  # type: ignore[method-assign]
        handler._read_body = lambda: {  # type: ignore[method-assign]
            "operationId": "0" * 32,
            "timeoutSeconds": 2.0,
        }
        handler._send = lambda status, value: events.append("response") or True  # type: ignore[method-assign]
        handler.do_POST()
        self.assertEqual(events, ["accepted", "response", "deferred"])
        server.begin_shutdown()
        self.assertEqual(events, ["accepted", "response", "deferred", "manager", "server"])

    def test_client_requires_response_instance_identity(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id="00000000000000000000000000000000",
                instance_id="expected-instance",
                port=43210,
                bootstrap_backend="test",
                bootstrap_selection_reason="test fixture",
                runtime_fingerprint="a" * 64,
            )
            write_manager_identity(config, adapter, identity)
            for meta in ({}, {"managerInstanceId": "other-instance"}):
                with self.subTest(meta=meta):
                    client = ManagerClient(
                        config,
                        adapter,
                        opener=StaticOpener({"ok": True, "operation": "health", "data": {}, "meta": meta}),
                    )
                    with self.assertRaises(RuntimeCorruptError):
                        client.request("GET", "/health")

    def test_client_classifies_response_read_timeout_as_unresponsive(self) -> None:
        with workspace_directory() as directory:
            workspace = Path(directory)
            config = create_config(workspace)
            adapter = FakeAdapter(workspace, config.state_root)
            initialize_runtime(config, adapter)
            identity = build_manager_identity(
                config,
                adapter,
                operation_id="0" * 32,
                instance_id="expected-instance",
                port=43210,
                bootstrap_backend="test",
                bootstrap_selection_reason="test fixture",
                runtime_fingerprint="a" * 64,
            )
            write_manager_identity(config, adapter, identity)
            response = mock.Mock(status=200)
            response.read.side_effect = TimeoutError("fixture")
            opener = mock.Mock()
            opener.open.return_value = response
            client = ManagerClient(config, adapter, opener=opener)
            with self.assertRaises(ManagerUnresponsiveError) as raised:
                client.request("GET", "/health")
            self.assertEqual(raised.exception.recommended_action, "wait")
            response.close.assert_called_once_with()
            oversized = mock.Mock(status=200)
            oversized.read.return_value = b"{}"
            oversized_opener = mock.Mock()
            oversized_opener.open.return_value = oversized
            with (
                mock.patch("process_manager.client.MAX_RESPONSE_BYTES", 1),
                self.assertRaises(RuntimeCorruptError),
            ):
                ManagerClient(config, adapter, opener=oversized_opener).request("GET", "/health")
            oversized.close.assert_called_once_with()

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
                    operation_id=manager.operation_id,
                    instance_id=manager.instance_id,
                    port=int(server.server_address[1]),
                    bootstrap_backend="test",
                    bootstrap_selection_reason="test fixture",
                    runtime_fingerprint=manager.runtime_fingerprint,
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
                status, value = client.request(
                    "POST",
                    "/sessions/open",
                    {"kind": "validation", "ttlSeconds": 1800, "holder": "control-test"},
                )
                session_id = value["data"]["sessionId"]
                self.assertEqual(status, 200)
                status, value = client.request(
                    "GET",
                    "/sessions/status",
                    params={"sessionId": session_id},
                )
                self.assertEqual((status, value["data"]["state"]), (200, "open"))
                status, value = client.request(
                    "POST",
                    "/sessions/renew",
                    {"sessionId": session_id, "ttlSeconds": 3600},
                )
                self.assertEqual((status, value["data"]["ttl_seconds"]), (200, 3600))
                status, value = client.request(
                    "POST",
                    "/processes/start",
                    {
                        "servicePath": "service.json",
                        "sessionId": session_id,
                        "persistent": False,
                    },
                )
                self.assertEqual(
                    (status, value["data"]["session_id"], value["data"]["persistent"]),
                    (200, session_id, False),
                )
                status, value = client.request(
                    "POST",
                    "/sessions/close",
                    {"sessionId": session_id},
                )
                self.assertEqual((status, value["data"]["state"]), (200, "closed"))
                status, value = client.request(
                    "POST",
                    "/processes/start",
                    {
                        "servicePath": "service.json",
                        "sessionId": None,
                        "persistent": "true",
                    },
                )
                self.assertEqual((status, value["error"]["code"]), (400, "invalid_request"))

                url = f"http://127.0.0.1:{server.server_address[1]}/health"
                with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                    urllib.request.urlopen(url, timeout=2)
                self.assertEqual(unauthorized.exception.code, 401)
                unauthorized.exception.close()

                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/processes/start",
                    data=b"x" * 129,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as oversized:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(oversized.exception.code, 400)
                oversized.exception.close()

                manager.instance_id = "different-instance"
                with self.assertRaises(RuntimeCorruptError):
                    client.request("GET", "/health")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
