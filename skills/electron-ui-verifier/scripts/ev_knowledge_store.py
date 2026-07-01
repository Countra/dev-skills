#!/usr/bin/env python3
"""Electron verifier 应用知识库的本地存储层。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ev_common import EVConfig, EVError, EVPaths, write_json


SCHEMA_VERSION = 1
VALID_STATUSES = {"observed", "candidate", "verified", "stable", "stale", "deprecated"}
DEFAULT_STATUS = "observed"
TEXT_LIMIT = 2000
KIND_TABLES = {
    "app": ("apps", "app_id"),
    "apps": ("apps", "app_id"),
    "screen": ("screens", "screen_id"),
    "screens": ("screens", "screen_id"),
    "element": ("elements", "element_id"),
    "elements": ("elements", "element_id"),
    "workflow": ("workflows", "workflow_id"),
    "workflows": ("workflows", "workflow_id"),
    "evidence": ("evidences", "evidence_id"),
    "evidences": ("evidences", "evidence_id"),
}
STATUS_TABLES = {"apps", "screens", "elements", "workflows"}


@dataclass(frozen=True)
class KnowledgePaths:
    """知识库运行时路径，全部位于 verifier stateRoot 下。"""

    root: Path
    db_file: Path
    manifest_file: Path


def knowledge_paths_for_state(state_root: Path) -> KnowledgePaths:
    root = state_root / "knowledge"
    return KnowledgePaths(root=root, db_file=root / "knowledge.sqlite", manifest_file=root / "manifest.json")


def knowledge_paths_from_ev_paths(paths: EVPaths) -> KnowledgePaths:
    return knowledge_paths_for_state(paths.state_root)


def knowledge_paths_from_config(config: EVConfig) -> KnowledgePaths:
    return knowledge_paths_for_state(config.state_root)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clip_text(value: Any, limit: int = TEXT_LIMIT) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def normalize_status(value: Any) -> str:
    status = str(value or DEFAULT_STATUS).strip()
    if status not in VALID_STATUSES:
        raise EVError(f"invalid knowledge status: {status}")
    return status


def kind_table(kind: str) -> tuple[str, str]:
    item = KIND_TABLES.get(str(kind or "").strip())
    if item is None:
        raise EVError(f"unsupported knowledge kind: {kind}")
    return item


def ensure_object(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise EVError(f"{label} must be an object")
    return value


def ensure_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise EVError(f"{label} must be a list")
    return value


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in (
        "data_json",
        "key_texts_json",
        "selectors_json",
        "anchors_json",
        "preconditions_json",
        "steps_json",
        "assertions_json",
        "artifact_refs_json",
    ):
        if key in data:
            data[key[:-5]] = json_load(data.pop(key), [] if key.endswith("s_json") else {})
    return data


def joined_text(parts: Iterable[Any]) -> str:
    return " ".join(clip_text(part, 500) for part in parts if part not in (None, ""))


class KnowledgeStore:
    """管理本地 SQLite 知识库和热启动 manifest。"""

    def __init__(self, paths: KnowledgePaths) -> None:
        self.paths = paths
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.paths.db_file))
        self.conn.row_factory = sqlite3.Row
        self.fts_available = self._detect_fts5()
        self._init_schema()
        self.write_manifest()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "KnowledgeStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _detect_fts5(self) -> bool:
        try:
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __ev_fts_probe USING fts5(value)")
            self.conn.execute("DROP TABLE IF EXISTS __ev_fts_probe")
            self.conn.commit()
            return True
        except sqlite3.DatabaseError:
            self.conn.rollback()
            return False

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS apps (
              app_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              exe_path_hash TEXT,
              product_name TEXT,
              version TEXT,
              data_json TEXT NOT NULL,
              status TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS screens (
              screen_id TEXT PRIMARY KEY,
              app_id TEXT NOT NULL,
              route TEXT,
              title TEXT,
              fingerprint TEXT,
              summary TEXT,
              key_texts_json TEXT NOT NULL,
              status TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              FOREIGN KEY(app_id) REFERENCES apps(app_id)
            );
            CREATE TABLE IF NOT EXISTS elements (
              element_id TEXT PRIMARY KEY,
              screen_id TEXT NOT NULL,
              app_id TEXT NOT NULL,
              name TEXT NOT NULL,
              role TEXT,
              text TEXT,
              selectors_json TEXT NOT NULL,
              anchors_json TEXT NOT NULL,
              confidence REAL NOT NULL,
              status TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              FOREIGN KEY(screen_id) REFERENCES screens(screen_id)
            );
            CREATE TABLE IF NOT EXISTS workflows (
              workflow_id TEXT PRIMARY KEY,
              app_id TEXT NOT NULL,
              goal TEXT NOT NULL,
              preconditions_json TEXT NOT NULL,
              steps_json TEXT NOT NULL,
              assertions_json TEXT NOT NULL,
              confidence REAL NOT NULL,
              status TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              FOREIGN KEY(app_id) REFERENCES apps(app_id)
            );
            CREATE TABLE IF NOT EXISTS evidences (
              evidence_id TEXT PRIMARY KEY,
              source_report TEXT,
              artifact_refs_json TEXT NOT NULL,
              notes TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schemaVersion', ?)", (str(SCHEMA_VERSION),))
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('ftsAvailable', ?)", ("true" if self.fts_available else "false",))
        if self.fts_available:
            self.conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                USING fts5(kind, entity_id, app_id, title, body);
                """
            )
        self.conn.commit()

    def write_manifest(self) -> dict[str, Any]:
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "updatedAt": utc_now(),
            "ftsAvailable": self.fts_available,
            "counts": {
                "apps": self.count("apps"),
                "screens": self.count("screens"),
                "elements": self.count("elements"),
                "workflows": self.count("workflows"),
                "evidences": self.count("evidences"),
            },
        }
        write_json(self.paths.manifest_file, manifest)
        return manifest

    def count(self, table: str) -> int:
        if table not in {"apps", "screens", "elements", "workflows", "evidences"}:
            raise EVError(f"unsupported knowledge table: {table}")
        row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def meta(self) -> dict[str, Any]:
        rows = self.conn.execute("SELECT key, value FROM meta ORDER BY key").fetchall()
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ftsAvailable": self.fts_available,
            "database": str(self.paths.db_file),
            "manifest": str(self.paths.manifest_file),
            "meta": {row["key"]: row["value"] for row in rows},
            "counts": {
                "apps": self.count("apps"),
                "screens": self.count("screens"),
                "elements": self.count("elements"),
                "workflows": self.count("workflows"),
                "evidences": self.count("evidences"),
            },
        }

    def _replace_fts(self, kind: str, entity_id: str, app_id: str, title: str, body: str) -> None:
        if not self.fts_available:
            return
        self.conn.execute("DELETE FROM knowledge_fts WHERE kind = ? AND entity_id = ?", (kind, entity_id))
        self.conn.execute(
            "INSERT INTO knowledge_fts(kind, entity_id, app_id, title, body) VALUES(?, ?, ?, ?, ?)",
            (kind, entity_id, app_id, clip_text(title, 500), clip_text(body, 8000)),
        )

    def upsert_app(self, item: dict[str, Any]) -> dict[str, Any]:
        app_id = str(item.get("appId") or "").strip()
        display_name = clip_text(item.get("displayName") or app_id or "unknown-app", 300)
        if not app_id:
            app_id = stable_id("app", display_name, item.get("exePathHash"), item.get("productName"), item.get("version"))
        now = utc_now()
        status = normalize_status(item.get("status"))
        data = ensure_object(item.get("data"), "app.data")
        existing = self.conn.execute("SELECT first_seen_at FROM apps WHERE app_id = ?", (app_id,)).fetchone()
        first_seen = existing["first_seen_at"] if existing else now
        self.conn.execute(
            """
            INSERT OR REPLACE INTO apps(
              app_id, display_name, exe_path_hash, product_name, version, data_json,
              status, first_seen_at, last_seen_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app_id,
                display_name,
                clip_text(item.get("exePathHash"), 300),
                clip_text(item.get("productName"), 300),
                clip_text(item.get("version"), 120),
                json_dump(data),
                status,
                first_seen,
                now,
            ),
        )
        self._replace_fts("app", app_id, app_id, display_name, joined_text([display_name, item.get("productName"), item.get("version")]))
        self.conn.commit()
        self.write_manifest()
        return self.get_app(app_id)

    def upsert_screen(self, item: dict[str, Any]) -> dict[str, Any]:
        app_id = str(item.get("appId") or "").strip()
        if not app_id:
            raise EVError("screen.appId is required")
        title = clip_text(item.get("title"), 500)
        route = clip_text(item.get("route"), 1000)
        fingerprint = clip_text(item.get("fingerprint"), 300)
        screen_id = str(item.get("screenId") or "").strip() or stable_id("screen", app_id, route, title, fingerprint)
        key_texts = [clip_text(text, 500) for text in ensure_list(item.get("keyTexts"), "screen.keyTexts")]
        now = utc_now()
        status = normalize_status(item.get("status"))
        existing = self.conn.execute("SELECT first_seen_at FROM screens WHERE screen_id = ?", (screen_id,)).fetchone()
        first_seen = existing["first_seen_at"] if existing else now
        self.conn.execute(
            """
            INSERT OR REPLACE INTO screens(
              screen_id, app_id, route, title, fingerprint, summary, key_texts_json,
              status, first_seen_at, last_seen_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                screen_id,
                app_id,
                route,
                title,
                fingerprint,
                clip_text(item.get("summary"), 2000),
                json_dump(key_texts),
                status,
                first_seen,
                now,
            ),
        )
        self._replace_fts("screen", screen_id, app_id, title, joined_text([route, title, item.get("summary"), *key_texts]))
        self.conn.commit()
        self.write_manifest()
        return self.get_screen(screen_id)

    def upsert_element(self, item: dict[str, Any]) -> dict[str, Any]:
        app_id = str(item.get("appId") or "").strip()
        screen_id = str(item.get("screenId") or "").strip()
        name = clip_text(item.get("name") or item.get("text") or "element", 300)
        if not app_id or not screen_id:
            raise EVError("element.appId and element.screenId are required")
        element_id = str(item.get("elementId") or "").strip() or stable_id("element", screen_id, name, item.get("role"), item.get("text"))
        selectors = ensure_list(item.get("selectorCandidates"), "element.selectorCandidates")
        anchors = ensure_list(item.get("anchors"), "element.anchors")
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.3))))
        now = utc_now()
        status = normalize_status(item.get("status"))
        existing = self.conn.execute("SELECT first_seen_at FROM elements WHERE element_id = ?", (element_id,)).fetchone()
        first_seen = existing["first_seen_at"] if existing else now
        self.conn.execute(
            """
            INSERT OR REPLACE INTO elements(
              element_id, screen_id, app_id, name, role, text, selectors_json, anchors_json,
              confidence, status, first_seen_at, last_seen_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                element_id,
                screen_id,
                app_id,
                name,
                clip_text(item.get("role"), 120),
                clip_text(item.get("text"), 1000),
                json_dump(selectors),
                json_dump(anchors),
                confidence,
                status,
                first_seen,
                now,
            ),
        )
        self._replace_fts("element", element_id, app_id, name, joined_text([name, item.get("role"), item.get("text"), selectors, anchors]))
        self.conn.commit()
        self.write_manifest()
        return self.get_element(element_id)

    def upsert_workflow(self, item: dict[str, Any]) -> dict[str, Any]:
        app_id = str(item.get("appId") or "").strip()
        goal = clip_text(item.get("goal"), 1000)
        if not app_id or not goal:
            raise EVError("workflow.appId and workflow.goal are required")
        workflow_id = str(item.get("workflowId") or "").strip() or stable_id("workflow", app_id, goal, item.get("steps"))
        preconditions = ensure_list(item.get("preconditions"), "workflow.preconditions")
        steps = ensure_list(item.get("steps"), "workflow.steps")
        assertions = ensure_list(item.get("assertions"), "workflow.assertions")
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.3))))
        now = utc_now()
        status = normalize_status(item.get("status", "candidate"))
        existing = self.conn.execute("SELECT first_seen_at FROM workflows WHERE workflow_id = ?", (workflow_id,)).fetchone()
        first_seen = existing["first_seen_at"] if existing else now
        self.conn.execute(
            """
            INSERT OR REPLACE INTO workflows(
              workflow_id, app_id, goal, preconditions_json, steps_json, assertions_json,
              confidence, status, first_seen_at, last_seen_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                app_id,
                goal,
                json_dump(preconditions),
                json_dump(steps),
                json_dump(assertions),
                confidence,
                status,
                first_seen,
                now,
            ),
        )
        self._replace_fts("workflow", workflow_id, app_id, goal, joined_text([goal, preconditions, steps, assertions]))
        self.conn.commit()
        self.write_manifest()
        return self.get_workflow(workflow_id)

    def add_evidence(self, item: dict[str, Any]) -> dict[str, Any]:
        evidence_id = str(item.get("evidenceId") or "").strip() or stable_id("evidence", item.get("sourceReport"), item.get("artifactRefs"), utc_now())
        artifact_refs = ensure_list(item.get("artifactRefs"), "evidence.artifactRefs")
        created_at = str(item.get("createdAt") or utc_now())
        self.conn.execute(
            """
            INSERT OR REPLACE INTO evidences(evidence_id, source_report, artifact_refs_json, notes, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                clip_text(item.get("sourceReport"), 2000),
                json_dump([clip_text(ref, 2000) for ref in artifact_refs]),
                clip_text(item.get("notes"), 2000),
                created_at,
            ),
        )
        self.conn.commit()
        self.write_manifest()
        return self.get_evidence(evidence_id)

    def get_app(self, app_id: str) -> dict[str, Any]:
        return self._get_one("apps", "app_id", app_id)

    def get_screen(self, screen_id: str) -> dict[str, Any]:
        return self._get_one("screens", "screen_id", screen_id)

    def get_element(self, element_id: str) -> dict[str, Any]:
        return self._get_one("elements", "element_id", element_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        return self._get_one("workflows", "workflow_id", workflow_id)

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        return self._get_one("evidences", "evidence_id", evidence_id)

    def get_item(self, kind: str, entity_id: str) -> dict[str, Any]:
        table, key = kind_table(kind)
        return self._get_one(table, key, entity_id)

    def _get_one(self, table: str, key: str, value: str) -> dict[str, Any]:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,)).fetchone()
        if row is None:
            raise EVError(f"knowledge item not found: {table}.{value}")
        return row_to_dict(row)

    def list_items(self, kind: str, app_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        table, _key = kind_table(kind)
        limit = max(1, min(200, int(limit)))
        if app_id and table in {"screens", "elements", "workflows"}:
            rows = self.conn.execute(f"SELECT * FROM {table} WHERE app_id = ? ORDER BY last_seen_at DESC LIMIT ?", (app_id, limit)).fetchall()
        else:
            rows = self.conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [row_to_dict(row) for row in rows]

    def update_status(self, kind: str, entity_id: str, status: str) -> dict[str, Any]:
        table, key = kind_table(kind)
        if table not in STATUS_TABLES:
            raise EVError(f"knowledge kind does not support status update: {kind}")
        normalized = normalize_status(status)
        cursor = self.conn.execute(f"UPDATE {table} SET status = ?, last_seen_at = ? WHERE {key} = ?", (normalized, utc_now(), entity_id))
        if cursor.rowcount < 1:
            raise EVError(f"knowledge item not found: {kind}.{entity_id}")
        self.conn.commit()
        self.write_manifest()
        return self.get_item(kind, entity_id)

    def search(self, query: str, app_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            raise EVError("search query is required")
        limit = max(1, min(100, int(limit)))
        if self.fts_available:
            try:
                return self._search_fts(query, app_id, limit)
            except sqlite3.DatabaseError:
                # FTS5 MATCH 对特殊字符较敏感，查询语法失败时降级为普通 LIKE。
                return self._search_like(query, app_id, limit)
        return self._search_like(query, app_id, limit)

    def _search_fts(self, query: str, app_id: str | None, limit: int) -> list[dict[str, Any]]:
        safe_query = " ".join(part.replace('"', '""') for part in query.split())
        if app_id:
            rows = self.conn.execute(
                """
                SELECT kind, entity_id, app_id, title, snippet(knowledge_fts, 4, '[', ']', '...', 20) AS preview
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ? AND app_id = ?
                LIMIT ?
                """,
                (safe_query, app_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT kind, entity_id, app_id, title, snippet(knowledge_fts, 4, '[', ']', '...', 20) AS preview
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                LIMIT ?
                """,
                (safe_query, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _search_like(self, query: str, app_id: str | None, limit: int) -> list[dict[str, Any]]:
        like = f"%{query}%"
        results: list[dict[str, Any]] = []
        specs = [
            ("app", "apps", "app_id", "app_id", "display_name", "display_name || ' ' || product_name || ' ' || version"),
            ("screen", "screens", "screen_id", "app_id", "title", "title || ' ' || route || ' ' || summary || ' ' || key_texts_json"),
            ("element", "elements", "element_id", "app_id", "name", "name || ' ' || role || ' ' || text || ' ' || selectors_json || ' ' || anchors_json"),
            ("workflow", "workflows", "workflow_id", "app_id", "goal", "goal || ' ' || preconditions_json || ' ' || steps_json || ' ' || assertions_json"),
        ]
        for kind, table, id_col, app_col, title_col, body_expr in specs:
            if len(results) >= limit:
                break
            if app_id and app_col:
                sql = f"SELECT '{kind}' AS kind, {id_col} AS entity_id, {app_col} AS app_id, {title_col} AS title, {body_expr} AS preview FROM {table} WHERE {app_col} = ? AND ({body_expr}) LIKE ? LIMIT ?"
                rows = self.conn.execute(sql, (app_id, like, limit - len(results))).fetchall()
            else:
                sql = f"SELECT '{kind}' AS kind, {id_col} AS entity_id, {app_col} AS app_id, {title_col} AS title, {body_expr} AS preview FROM {table} WHERE ({body_expr}) LIKE ? LIMIT ?"
                rows = self.conn.execute(sql, (like, limit - len(results))).fetchall()
            for row in rows:
                item = dict(row)
                item["preview"] = clip_text(item.get("preview"), 500)
                results.append(item)
        return results

    def cleanup(self, keep_inactive: int = 200) -> dict[str, Any]:
        keep_inactive = max(0, int(keep_inactive))
        removed: dict[str, int] = {}
        for table, id_col in (("screens", "screen_id"), ("elements", "element_id"), ("workflows", "workflow_id")):
            rows = self.conn.execute(
                f"""
                SELECT {id_col} AS id FROM {table}
                WHERE status IN ('stale', 'deprecated')
                ORDER BY last_seen_at DESC
                LIMIT -1 OFFSET ?
                """,
                (keep_inactive,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            removed[table] = len(ids)
            for entity_id in ids:
                self.conn.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (entity_id,))
                if self.fts_available:
                    self.conn.execute("DELETE FROM knowledge_fts WHERE entity_id = ?", (entity_id,))
        self.conn.commit()
        manifest = self.write_manifest()
        return {"removed": removed, "manifest": manifest}


def open_store_from_paths(paths: KnowledgePaths) -> KnowledgeStore:
    return KnowledgeStore(paths)
