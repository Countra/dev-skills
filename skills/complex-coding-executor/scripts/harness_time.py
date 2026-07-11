#!/usr/bin/env python3
"""为 task bundle 提供严格一致的 RFC3339 时间解析。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def parse_rfc3339(value: Any) -> datetime:
    if not isinstance(value, str) or not RFC3339_PATTERN.fullmatch(value):
        raise ValueError("invalid RFC3339 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed
