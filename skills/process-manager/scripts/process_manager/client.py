"""bundled CLI 使用的身份校验与控制面 client。"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import ManagerOfflineError, ManagerUnresponsiveError, PMError, RuntimeCorruptError
from .models import ManagerConfig
from .platforms.base import PlatformAdapter
from .protocol import verify_control_busy
from .runtime import read_manager_identity, read_token


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_BUSY_LOCK = threading.Lock()
_BUSY_NONCES: dict[str, int] = {}


def _remember_busy(instance_id: str, evidence: dict[str, Any]) -> None:
    now = time.time_ns() // 1_000_000
    key = f"{instance_id}:{evidence['nonce']}"
    with _BUSY_LOCK:
        for expired in [item for item, deadline in _BUSY_NONCES.items() if deadline < now]:
            _BUSY_NONCES.pop(expired, None)
        if key in _BUSY_NONCES:
            raise RuntimeCorruptError("control_busy evidence 被重放")
        if len(_BUSY_NONCES) >= 1024:
            raise RuntimeCorruptError("control_busy replay cache 已达到安全上限")
        _BUSY_NONCES[key] = int(evidence["issuedAtUnixMs"]) + int(evidence["validForMs"])


def request_manager_shutdown(
    client: Any,
    operation_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or timeout_seconds <= 0
    ):
        raise ValueError("manager shutdown timeoutSeconds 必须是有限正数")
    status, response = client.request(
        "POST",
        "/shutdown",
        {"operationId": operation_id, "timeoutSeconds": float(timeout_seconds)},
    )
    data = response.get("data")
    if (
        status >= 400
        or response.get("ok") is not True
        or not isinstance(data, dict)
        or data.get("shutdownAccepted") is not True
        or data.get("operationId") != operation_id
    ):
        raise ManagerUnresponsiveError("manager shutdown ack 无效", recommended_action="doctor")
    return data


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
        except (TimeoutError, OSError) as exc:
            raise ManagerUnresponsiveError(
                "manager control response 读取失败",
                recommended_action="wait",
                retryable=True,
            ) from exc
        finally:
            response.close()
        if len(data) > MAX_RESPONSE_BYTES:
            raise RuntimeCorruptError("manager response 超过上限")
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeCorruptError("manager response 不是有效 JSON") from exc
        if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
            raise RuntimeCorruptError("manager response envelope 无效")
        instance_id = str(identity.get("instanceId"))
        if status == 503 and isinstance(value.get("error"), dict) and (
            value["error"].get("code") == "control_busy"
        ):
            evidence = verify_control_busy(value, token, instance_id)
            _remember_busy(instance_id, evidence)
            raise ManagerUnresponsiveError(
                "manager 控制面已达到并发上限",
                diagnostics={
                    "endpointState": "busy",
                    "retryAfterMs": evidence["retryAfterMs"],
                },
                recommended_action="wait",
                retryable=True,
            )
        meta = value.get("meta")
        response_instance = meta.get("managerInstanceId") if isinstance(meta, dict) else None
        if response_instance != identity.get("instanceId"):
            raise RuntimeCorruptError("manager response instance identity 不匹配")
        return status, value
