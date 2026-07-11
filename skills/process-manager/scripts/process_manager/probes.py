"""平台无关、loopback-only 且有界的 readiness probes。"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .errors import ProbeLimitError, ReadinessTimeoutError, StateError, ValidationError
from .logs import IncrementalLogScanner
from .patterns import compile_log_pattern
from .runtime import now_text


POLL_SECONDS = 0.1


def _resolved_loopback(host: str, port: int) -> list[tuple[int, int, int, tuple[Any, ...]]]:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    result: list[tuple[int, int, int, tuple[Any, ...]]] = []
    for family, socktype, protocol, _, sockaddr in addresses:
        try:
            if not ipaddress.ip_address(str(sockaddr[0])).is_loopback:
                return []
        except ValueError:
            return []
        result.append((family, socktype, protocol, sockaddr))
    return result


def _loopback_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host_is_loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and host_is_loopback
        and bool(_resolved_loopback(parsed.hostname or "", port))
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    )


class LoopbackRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if not _loopback_url(newurl):
            raise urllib.error.URLError("readiness redirect 越过 loopback 边界")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_ready(url: str, timeout: float) -> bool:
    if not _loopback_url(url):
        return False
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        LoopbackRedirectHandler(),
    )
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "dev-skills-process-manager"})
    try:
        response = opener.open(request, timeout=max(0.1, min(timeout, 2.0)))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    try:
        return 200 <= int(response.status) < 400
    finally:
        response.close()


def _tcp_ready(host: str, port: int, timeout: float) -> bool:
    for family, socktype, protocol, sockaddr in _resolved_loopback(host, port):
        connection = socket.socket(family, socktype, protocol)
        try:
            connection.settimeout(max(0.1, min(timeout, 1.0)))
            connection.connect(sockaddr)
            return True
        except OSError:
            continue
        finally:
            connection.close()
    return False


def _extract(match: re.Match[str], extract: dict[str, list[str]]) -> dict[str, list[str]]:
    observed: dict[str, list[str]] = {}
    for key, selectors in extract.items():
        values: list[str] = []
        for selector in selectors:
            try:
                value = match.group(int(selector) if selector.isdigit() else selector)
            except (IndexError, KeyError):
                continue
            if value is not None:
                values.append(str(value))
        observed[key] = values
    return observed


def wait_for_readiness(
    readiness: dict[str, Any],
    *,
    log_path: Path,
    log_backups: int,
    is_running: Callable[[], bool],
    timeout_override: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    configured_timeout = float(readiness.get("timeoutSeconds", 30))
    timeout = configured_timeout if timeout_override is None else float(timeout_override)
    if not 0.1 <= timeout <= 600:
        raise ValidationError("readiness timeout 必须在 0.1-600 秒")
    strategy = str(readiness["type"])
    started = monotonic()
    deadline = started + timeout
    stable_since: float | None = None
    scanner = None
    pattern = None
    if strategy == "log":
        pattern = compile_log_pattern(str(readiness["pattern"]))
        scanner = IncrementalLogScanner(log_path, log_backups, int(readiness["scanBytes"]))
    while True:
        if not is_running():
            raise StateError("managed process 在 readiness 完成前退出")
        now = monotonic()
        ready = False
        observed: dict[str, Any] = {}
        if strategy == "process":
            stable_since = stable_since if stable_since is not None else now
            ready = now - stable_since >= float(readiness["stableSeconds"])
        elif strategy == "tcp":
            ready = _tcp_ready(str(readiness["host"]), int(readiness["port"]), deadline - now)
        elif strategy == "http":
            ready = _http_ready(str(readiness["url"]), deadline - now)
        elif strategy == "log" and scanner is not None and pattern is not None:
            scanner.scan()
            match = pattern.search(scanner.text)
            ready = match is not None
            if match is not None:
                observed = _extract(match, dict(readiness.get("extract", {})))
            elif scanner.exhausted:
                raise ProbeLimitError(
                    "readiness log scanBytes 已耗尽",
                    diagnostics={"strategy": strategy, "bytesScanned": scanner.bytes_scanned},
                )
        else:
            raise ValidationError("readiness strategy 无效")
        if ready:
            return {
                "ready": True,
                "strategy": strategy,
                "checkedAt": now_text(),
                "elapsedSeconds": round(max(0.0, monotonic() - started), 3),
                "observed": observed,
                "bytesScanned": scanner.bytes_scanned if scanner is not None else 0,
            }
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ReadinessTimeoutError(
                "readiness probe 超时",
                diagnostics={
                    "strategy": strategy,
                    "timeoutSeconds": timeout,
                    "bytesScanned": scanner.bytes_scanned if scanner is not None else 0,
                },
            )
        sleep(min(POLL_SECONDS, remaining))
