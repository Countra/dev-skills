"""可恢复 session intent 与 live handle 生命周期。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .driver import PlaywrightCdpDriver
from .errors import VerifierError
from .models import SessionIntent
from .security import normalize_loopback_endpoint
from .sensitivity import sanitize_url


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SessionManager:
    """持久化 intent，但只通过 driver health 声明实时连接。"""

    def __init__(self, sessions_file: Path, driver: PlaywrightCdpDriver) -> None:
        self.sessions_file = sessions_file
        self.driver = driver
        self._intents: dict[str, SessionIntent] = {}

    async def load(self) -> None:
        if not self.sessions_file.exists():
            await self._persist()
            return
        try:
            data = json.loads(self.sessions_file.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("sessions_corrupt", f"无法读取 session intent：{type(exc).__name__}", status=500) from exc
        rows = data.get("sessions", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            raise VerifierError("sessions_corrupt", "sessions.json 的 sessions 必须是数组", status=500)
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            endpoint = str(row.get("cdp") or "").strip()
            if not name or not endpoint:
                continue
            endpoint = normalize_loopback_endpoint(endpoint)
            selector = {"targetId": str(row["targetId"])} if row.get("targetId") else {}
            created = str(row.get("createdAt") or _now())
            self._intents[name] = SessionIntent(
                session_id=str(row.get("sessionId") or uuid.uuid4()),
                name=name,
                cdp=endpoint,
                selector=dict(selector),
                app_id=str(row.get("appId")) if row.get("appId") else None,
                status="stale",
                target_id=str(row.get("targetId")) if row.get("targetId") else None,
                target_url=sanitize_url(str(row.get("targetUrl"))) if row.get("targetUrl") else None,
                target_title=str(row.get("targetTitle")) if row.get("targetTitle") else None,
                created_at=created,
                updated_at=_now(),
            )
        await self._persist()

    async def _persist(self) -> None:
        sessions = []
        for item in sorted(self._intents.values(), key=lambda value: value.name):
            record = item.to_dict()
            record["targetTitle"] = None
            sessions.append(record)
        atomic_write_json(
            self.sessions_file,
            {
                "schemaVersion": 1,
                "updatedAt": _now(),
                "sessions": sessions,
            },
        )

    def _find(self, value: str) -> SessionIntent | None:
        intent = self._intents.get(value)
        if intent is not None:
            return intent
        return next((item for item in self._intents.values() if item.session_id == value), None)

    def _selector(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: payload[key]
            for key in ("targetType", "targetUrlContains", "targetTitleContains", "targetIndex", "targetId")
            if payload.get(key) not in (None, "")
        }

    async def attach(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or payload.get("session") or "").strip()
        if not name:
            raise VerifierError("session_name_required", "session name 不能为空")
        endpoint = normalize_loopback_endpoint(str(payload.get("cdp") or ""))
        selector = self._selector(payload)
        existing = self._intents.get(name)
        if existing is not None and not selector:
            selector = dict(existing.selector)
        reuse = payload.get("reuse", True) is not False
        if existing is not None and reuse and existing.cdp == endpoint and existing.selector == selector:
            health = await self.driver.health(existing.session_id)
            if health.get("connected"):
                return {"ok": True, "reused": True, "reconnected": False, "session": self._record(existing, health)}
        if existing is not None:
            await self.driver.close(existing.session_id)
        session_id = existing.session_id if existing is not None else str(uuid.uuid4())
        live = await self.driver.attach(session_id, name, endpoint, selector)
        now = _now()
        intent = SessionIntent(
            session_id=session_id,
            name=name,
            cdp=endpoint,
            selector={"targetId": live.target.target_id},
            app_id=str(payload.get("appId")) if payload.get("appId") else (existing.app_id if existing else None),
            status="connected",
            target_id=live.target.target_id,
            target_url=sanitize_url(live.target.url),
            target_title=live.target.title,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._intents[name] = intent
        await self._persist()
        return {
            "ok": True,
            "reused": False,
            "reconnected": existing is not None,
            "session": self._record(intent, {"connected": True, "status": "connected"}),
        }

    def _record(self, intent: SessionIntent, health: dict[str, Any]) -> dict[str, Any]:
        record = intent.to_dict()
        record["status"] = health.get("status", "stale")
        record["connected"] = health.get("connected") is True
        if health.get("reason"):
            record["reason"] = health["reason"]
        if health.get("url"):
            record["targetUrl"] = sanitize_url(str(health["url"]))
        if health.get("title"):
            record["targetTitle"] = health["title"]
        return record

    async def status(self, value: str) -> dict[str, Any]:
        intent = self._find(value)
        if intent is None:
            raise VerifierError("session_not_found", f"session 不存在：{value}", status=404)
        health = await self.driver.health(intent.session_id)
        intent.status = str(health.get("status") or "stale")
        intent.updated_at = _now()
        await self._persist()
        return {"ok": health.get("connected") is True, "connected": health.get("connected") is True, "session": self._record(intent, health)}

    async def list(self) -> dict[str, Any]:
        records = []
        for intent in sorted(self._intents.values(), key=lambda item: item.name):
            health = await self.driver.health(intent.session_id)
            records.append(self._record(intent, health))
        return {"ok": True, "sessions": records}

    async def detach(self, value: str) -> dict[str, Any]:
        intent = self._find(value)
        if intent is None:
            return {"ok": True, "detached": True, "alreadyDetached": True, "warnings": []}
        warnings = await self.driver.close(intent.session_id)
        self._intents.pop(intent.name, None)
        await self._persist()
        record = intent.to_dict()
        record["status"] = "detached"
        record["connected"] = False
        return {"ok": True, "detached": True, "alreadyDetached": False, "warnings": warnings, "session": record}

    async def shutdown(self) -> None:
        for intent in self._intents.values():
            await self.driver.close(intent.session_id)
            intent.status = "stale"
            intent.updated_at = _now()
        await self._persist()

    def intent(self, value: str) -> SessionIntent:
        intent = self._find(value)
        if intent is None:
            raise VerifierError("session_not_found", f"session 不存在：{value}", status=404)
        return intent
