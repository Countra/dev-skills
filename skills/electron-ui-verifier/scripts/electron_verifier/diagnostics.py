"""有界、脱敏的 renderer diagnostics ring。"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .limits import DEFAULT_LIMITS, RuntimeLimits
from .security import redact


def _safe_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https", "file", "app"}:
        return f"{parsed.scheme}:"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path[:2000]
    return urllib.parse.urlunsplit((parsed.scheme, f"{host}{port}", path, "", ""))


@dataclass
class EventRing:
    limits: RuntimeLimits = DEFAULT_LIMITS
    _rows: deque[dict[str, Any]] = field(default_factory=deque)
    _bytes: int = 0

    def add(self, kind: str, value: dict[str, Any]) -> None:
        row = {
            "kind": kind,
            "timestampMs": int(time.time() * 1000),
            **redact(value, text_limit=4000),
        }
        size = len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if size > self.limits.event_bytes:
            return
        while self._rows and (
            len(self._rows) >= self.limits.event_count
            or self._bytes + size > self.limits.event_bytes
        ):
            removed = self._rows.popleft()
            self._bytes -= len(json.dumps(removed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        self._rows.append(row)
        self._bytes += size

    def select(self, kind: str, maximum: int, **filters: Any) -> list[dict[str, Any]]:
        maximum = max(0, min(maximum, self.limits.event_count))
        rows = [row for row in self._rows if row.get("kind") == kind]
        if kind == "console" and filters.get("levels"):
            allowed = {str(item) for item in filters["levels"]}
            rows = [row for row in rows if row.get("level") in allowed]
        if kind == "network" and filters.get("urlContains"):
            needle = str(filters["urlContains"])
            rows = [row for row in rows if needle in str(row.get("url") or "")]
        if kind == "network" and filters.get("includeFailedOnly"):
            rows = [row for row in rows if row.get("failed") is True or int(row.get("status") or 0) >= 400]
        return rows[-maximum:]


class DiagnosticRecorder:
    """注册 Playwright page 事件，不保存 headers、body、cookie 或 storage。"""

    def __init__(self, limits: RuntimeLimits = DEFAULT_LIMITS) -> None:
        self.ring = EventRing(limits)

    def bind(self, page: Any) -> None:
        page.on(
            "console",
            lambda message: self.ring.add(
                "console",
                {
                    "level": message.type,
                    "text": message.text,
                    "location": redact(message.location),
                },
            ),
        )
        page.on("pageerror", lambda error: self.ring.add("exception", {"message": str(error)}))
        page.on(
            "requestfailed",
            lambda request: self.ring.add(
                "network",
                {
                    "method": request.method,
                    "url": _safe_url(request.url),
                    "failed": True,
                    "failure": request.failure,
                },
            ),
        )
        page.on(
            "response",
            lambda response: self.ring.add(
                "network",
                {
                    "method": response.request.method,
                    "url": _safe_url(response.url),
                    "status": response.status,
                    "failed": response.status >= 400,
                },
            ),
        )
