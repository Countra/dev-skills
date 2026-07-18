from __future__ import annotations

import os
import socket
import stat
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from helpers import workspace_directory  # noqa: E402
from process_manager.errors import ProbeLimitError  # noqa: E402
from process_manager.logs import IncrementalLogScanner, read_log_tail  # noqa: E402
from process_manager.probes import LoopbackRedirectHandler, wait_for_readiness  # noqa: E402
from process_manager.service_host import RotatingBinaryLog, SecretRedactor  # noqa: E402


class ReadyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):  # noqa: ANN001
        return


class LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class LogAndProbeTests(unittest.TestCase):
    def test_rotated_tail_preserves_order_and_budget(self) -> None:
        with workspace_directory() as directory:
            root = Path(directory)
            path = root / "stdout.log"
            (root / "stdout.log.2").write_text("old-1\n", encoding="utf-8")
            (root / "stdout.log.1").write_text("old-2\n", encoding="utf-8")
            path.write_text("new-1\nnew-2\n", encoding="utf-8")
            value = read_log_tail(path, 2, tail_lines=3, max_bytes=1024)
            self.assertEqual(value["lines"], ["old-2", "new-1", "new-2"])
            self.assertTrue(value["truncated"])
            self.assertEqual([item["name"] for item in value["files"]], ["stdout.log.2", "stdout.log.1", "stdout.log"])

    def test_rotated_tail_skips_file_removed_during_snapshot(self) -> None:
        with workspace_directory() as directory:
            root = Path(directory)
            path = root / "stdout.log"
            rotated = root / "stdout.log.1"
            rotated.write_text("old\n", encoding="utf-8")
            path.write_text("new\n", encoding="utf-8")
            original_open = Path.open

            def disappearing_open(candidate: Path, *args, **kwargs):  # noqa: ANN002,ANN003,ANN202
                if candidate == rotated and candidate.exists():
                    candidate.unlink()
                    raise FileNotFoundError(candidate)
                return original_open(candidate, *args, **kwargs)

            with mock.patch.object(Path, "open", new=disappearing_open):
                value = read_log_tail(path, 1, tail_lines=10, max_bytes=1024)
            self.assertEqual(value["lines"], ["new"])
            self.assertEqual([item["name"] for item in value["files"]], ["stdout.log"])

    def test_incremental_scanner_skips_file_removed_during_snapshot(self) -> None:
        with workspace_directory() as directory:
            root = Path(directory)
            path = root / "stdout.log"
            rotated = root / "stdout.log.1"
            rotated.write_text("old\n", encoding="utf-8")
            path.write_text("ready\n", encoding="utf-8")
            scanner = IncrementalLogScanner(path, 1, 1024)
            original_open = Path.open

            def disappearing_open(candidate: Path, *args, **kwargs):  # noqa: ANN002,ANN003,ANN202
                if candidate == rotated and candidate.exists():
                    candidate.unlink()
                    raise FileNotFoundError(candidate)
                return original_open(candidate, *args, **kwargs)

            with mock.patch.object(Path, "open", new=disappearing_open):
                self.assertTrue(scanner.scan())
            self.assertEqual(scanner.text.splitlines(), ["ready"])

    def test_log_rotation_and_secret_redaction_cross_chunk_boundary(self) -> None:
        redactor = SecretRedactor(["secret-value"])
        value = redactor.feed(b"before-secret-") + redactor.feed(b"value-after") + redactor.finish()
        self.assertEqual(value, b"before-***redacted***-after")
        with workspace_directory() as directory:
            path = Path(directory) / "service.log"
            log = RotatingBinaryLog(path, max_bytes=10, backups=2)
            log.write(b"12345678")
            log.write(b"abcdefgh")
            log.close()
            self.assertEqual((path.with_name("service.log.1")).read_bytes(), b"12345678")
            self.assertEqual(path.read_bytes(), b"abcdefgh")

    @unittest.skipUnless(hasattr(os, "fchmod") and hasattr(os, "getuid"), "仅 POSIX 验证日志 mode")
    def test_service_log_initial_and_rotated_generations_are_private(self) -> None:
        with workspace_directory() as directory:
            path = Path(directory) / "service.log"
            path.write_bytes(b"12345678")
            os.chmod(path, 0o666)
            log = RotatingBinaryLog(path, max_bytes=10, backups=1)
            log.write(b"abcdefgh")
            log.close()
            for candidate in (path, path.with_name("service.log.1")):
                self.assertEqual(stat.S_IMODE(candidate.stat().st_mode), 0o600)

    def test_log_rotation_retries_windows_sharing_violation(self) -> None:
        with workspace_directory() as directory:
            path = Path(directory) / "service.log"
            log = RotatingBinaryLog(path, max_bytes=10, backups=1)
            log.write(b"12345678")
            original_replace = Path.replace
            attempts = 0

            def flaky_replace(source: Path, target: Path) -> Path:
                nonlocal attempts
                if source == path and attempts < 2:
                    attempts += 1
                    error = PermissionError("sharing violation")
                    error.winerror = 32
                    raise error
                return original_replace(source, target)

            with (
                mock.patch("process_manager.atomic._windows_file_retry_enabled", return_value=True),
                mock.patch.object(Path, "replace", new=flaky_replace),
                mock.patch("process_manager.atomic.time.sleep") as sleep,
            ):
                log.write(b"abcdefgh")
            log.close()
            self.assertEqual(attempts, 2)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(path.with_name("service.log.1").read_bytes(), b"12345678")
            self.assertEqual(path.read_bytes(), b"abcdefgh")

    def test_process_tcp_and_http_probes_share_one_result_contract(self) -> None:
        clock = [0.0]

        def monotonic() -> float:
            return clock[0]

        def sleep(delay: float) -> None:
            clock[0] += delay

        process = wait_for_readiness(
            {"type": "process", "stableSeconds": 0.2, "timeoutSeconds": 1},
            log_path=Path("unused"),
            log_backups=0,
            is_running=lambda: True,
            monotonic=monotonic,
            sleep=sleep,
        )
        self.assertTrue(process["ready"])

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        try:
            tcp = wait_for_readiness(
                {"type": "tcp", "host": "127.0.0.1", "port": listener.getsockname()[1], "timeoutSeconds": 1},
                log_path=Path("unused"),
                log_backups=0,
                is_running=lambda: True,
            )
        finally:
            listener.close()
        self.assertTrue(tcp["ready"])

        server = LoopbackHTTPServer(("127.0.0.1", 0), ReadyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            http = wait_for_readiness(
                {"type": "http", "url": f"http://127.0.0.1:{server.server_address[1]}/ready", "timeoutSeconds": 1},
                log_path=Path("unused"),
                log_backups=0,
                is_running=lambda: True,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertTrue(http["ready"])
        self.assertEqual(set(process) - {"elapsedSeconds"}, set(tcp) - {"elapsedSeconds"})
        self.assertEqual(set(tcp) - {"elapsedSeconds"}, set(http) - {"elapsedSeconds"})

    def test_log_probe_is_incremental_extracting_and_budgeted(self) -> None:
        with workspace_directory() as directory:
            path = Path(directory) / "stdout.log"
            path.write_text("booting\n", encoding="utf-8")
            clock = [0.0]
            appended = [False]

            def sleep(delay: float) -> None:
                clock[0] += delay
                if not appended[0]:
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write("ready http://127.0.0.1:43210\n")
                    appended[0] = True

            value = wait_for_readiness(
                {
                    "type": "log",
                    "pattern": r"ready http://127\.0\.0\.1:(?P<port>\d+)",
                    "extract": {"ports": ["port"]},
                    "scanBytes": 4096,
                    "timeoutSeconds": 1,
                },
                log_path=path,
                log_backups=1,
                is_running=lambda: True,
                monotonic=lambda: clock[0],
                sleep=sleep,
            )
            self.assertEqual(value["observed"], {"ports": ["43210"]})
            self.assertLessEqual(value["bytesScanned"], 4096)

            path.write_bytes(b"x" * 1024)
            with self.assertRaises(ProbeLimitError):
                wait_for_readiness(
                    {
                        "type": "log",
                        "pattern": "never",
                        "extract": {},
                        "scanBytes": 1024,
                        "timeoutSeconds": 1,
                    },
                    log_path=path,
                    log_backups=0,
                    is_running=lambda: True,
                )

    def test_http_redirect_cannot_leave_loopback(self) -> None:
        handler = LoopbackRedirectHandler()
        request = urllib.request.Request("http://127.0.0.1:8000/ready")
        with self.assertRaises(urllib.error.URLError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/ready")

    def test_http_probe_disables_environment_proxies(self) -> None:
        real_builder = urllib.request.build_opener
        observed_handlers: list[object] = []

        def build_opener(*handlers):  # noqa: ANN001,ANN202
            observed_handlers.extend(handlers)
            return real_builder(*handlers)

        server = LoopbackHTTPServer(("127.0.0.1", 0), ReadyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch("process_manager.probes.urllib.request.build_opener", side_effect=build_opener):
                result = wait_for_readiness(
                    {
                        "type": "http",
                        "url": f"http://127.0.0.1:{server.server_address[1]}/ready",
                        "timeoutSeconds": 1,
                    },
                    log_path=Path("unused"),
                    log_backups=0,
                    is_running=lambda: True,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertTrue(result["ready"])
        proxies = [handler for handler in observed_handlers if isinstance(handler, urllib.request.ProxyHandler)]
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0].proxies, {})


if __name__ == "__main__":
    unittest.main()
