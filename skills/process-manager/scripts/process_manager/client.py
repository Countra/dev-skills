"""bundled CLI 使用的身份校验与控制面 client。"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import ManagerOfflineError, PMError
from .models import ManagerConfig
from .platforms.base import PlatformAdapter
from .runtime import read_manager_identity, read_token


MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise ManagerOfflineError("manager control endpoint 不允许 redirect")


class ManagerClient:
    def __init__(
        self,
        config: ManagerConfig,
        adapter: PlatformAdapter,
        *,
        timeout: float = 35,
        opener: Any | None = None,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirectHandler(),
        )

    def _runtime(self) -> tuple[dict[str, Any], str]:
        try:
            return read_manager_identity(self.config, self.adapter), read_token(self.config, self.adapter)
        except PMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ManagerOfflineError("manager runtime identity 不可用") from exc

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        identity, token = self._runtime()
        query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"http://{self.config.host}:{identity['port']}{path}"
        if query:
            url += "?" + query
        body = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(body) > self.config.max_request_bytes:
                raise PMError("控制请求超过 maxRequestBytes")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            response = self.opener.open(request, timeout=self.timeout)
            status = int(response.status)
        except urllib.error.HTTPError as exc:
            response = exc
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ManagerOfflineError("manager control endpoint 不可用") from exc
        try:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            response.close()
        if len(data) > MAX_RESPONSE_BYTES:
            raise ManagerOfflineError("manager response 超过上限")
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManagerOfflineError("manager response 不是有效 JSON") from exc
        if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
            raise ManagerOfflineError("manager response envelope 无效")
        meta = value.get("meta")
        response_instance = meta.get("managerInstanceId") if isinstance(meta, dict) else None
        if response_instance != identity.get("instanceId"):
            raise ManagerOfflineError("manager response instance identity 不匹配")
        return status, value
