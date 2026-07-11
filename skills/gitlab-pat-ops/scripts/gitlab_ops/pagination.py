"""GitLab 分页与列表预算。"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from typing import Any

from .errors import NetworkError, ResponseLimitError


DEFAULT_MAX_PAGES = 20
DEFAULT_MAX_ITEMS = 2000
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
HARD_MAX_PAGES = 100
HARD_MAX_ITEMS = 10000
HARD_MAX_BYTES = 20 * 1024 * 1024


def _header(headers: Any, name: str) -> str | None:
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return str(value) if value else None


def next_url_from_headers(headers: Any) -> str | None:
    link_header = _header(headers, "Link")
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part and "rel=next" not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start >= 0 and end > start:
            return part[start + 1 : end]
    return None


def _replace_page(url: str, next_page: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "page"]
    query.append(("page", next_page))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), ""))


def paginate(
    client: Any,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    per_page: int = 100,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[Any]:
    max_pages = min(max(1, int(max_pages)), HARD_MAX_PAGES)
    max_items = min(max(1, int(max_items)), HARD_MAX_ITEMS)
    max_bytes = min(max(1, int(max_bytes)), HARD_MAX_BYTES)
    current_params = dict(params or {})
    current_params["per_page"] = min(max(int(per_page), 1), 100)
    current_params.setdefault("page", 1)
    next_url: str | None = None
    values: list[Any] = []
    visited: set[str] = set()
    total_bytes = 0
    for page_number in range(1, max_pages + 1):
        current_url = client.build_url(next_url or path, None if next_url else current_params)
        if current_url in visited:
            raise ResponseLimitError("GitLab pagination 出现循环")
        visited.add(current_url)
        page_value, headers = client.request("GET", current_url, include_headers=True)
        if not isinstance(page_value, list):
            raise NetworkError("GitLab pagination 响应不是 JSON array")
        page_items = page_value
        total_bytes += len(json.dumps(page_value, ensure_ascii=False).encode("utf-8"))
        if len(values) + len(page_items) > max_items:
            raise ResponseLimitError("GitLab pagination 超过 max-items")
        if total_bytes > max_bytes:
            raise ResponseLimitError("GitLab pagination 超过 max-bytes")
        values.extend(page_items)
        next_url = next_url_from_headers(headers)
        if not next_url:
            next_page = _header(headers, "X-Next-Page")
            next_url = _replace_page(current_url, next_page) if next_page else None
        if not next_url:
            client.last_meta = {
                **client.last_meta,
                "pagination": {
                    "pages": page_number,
                    "items": len(values),
                    "bytes": total_bytes,
                },
            }
            return values
        if page_number == max_pages:
            raise ResponseLimitError("GitLab pagination 超过 max-pages")
    return values


def add_pagination_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="在预算内读取全部分页")
    parser.add_argument("--page", type=int, default=1, help="页码")
    parser.add_argument("--per-page", type=int, default=100, help="每页数量，最大 100")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)


def request_list(client: Any, path: str, args: argparse.Namespace, params: dict[str, Any] | None = None) -> Any:
    final_params = dict(params or {})
    if getattr(args, "all", False):
        return client.paginate(
            path,
            params=final_params,
            per_page=getattr(args, "per_page", 100),
            max_pages=getattr(args, "max_pages", DEFAULT_MAX_PAGES),
            max_items=getattr(args, "max_items", DEFAULT_MAX_ITEMS),
            max_bytes=getattr(args, "max_bytes", DEFAULT_MAX_BYTES),
        )
    final_params["page"] = max(1, int(getattr(args, "page", 1)))
    final_params["per_page"] = min(max(int(getattr(args, "per_page", 100)), 1), 100)
    return client.request("GET", path, params=final_params)
