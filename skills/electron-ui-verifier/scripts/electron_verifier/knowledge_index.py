"""Canonical knowledge 的可重建 SQLite derived index。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .errors import VerifierError
from .knowledge_models import CanonicalAsset
from .text_normalization import all_ngrams, normalize_text, search_terms


INDEX_SCHEMA_VERSION = 2


class KnowledgeIndex:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.connection = sqlite3.connect(path, timeout=5.0)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA busy_timeout=5000")
            mode = str(self.connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if mode == "wal":
                raise VerifierError("wal_not_allowed", "当前 runtime 禁止 knowledge index 使用 WAL", status=500)
            self._initialize()
        except VerifierError:
            if self.connection is not None:
                self.connection.close()
            raise
        except (sqlite3.Error, OSError) as exc:
            if self.connection is not None:
                self.connection.close()
            raise VerifierError("knowledge_index_open_failed", f"无法打开 derived index：{exc}", status=500) from exc

    def _initialize(self) -> None:
        assert self.connection is not None
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('action', 'workflow')),
                app_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                normalized_goal TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status = 'approved'),
                aliases_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                canonical_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                app_version_min TEXT,
                app_version_max TEXT,
                screen_digest TEXT,
                pre_state TEXT,
                post_state TEXT,
                risk_level TEXT NOT NULL DEFAULT 'low',
                success_count INTEGER NOT NULL DEFAULT 1,
                failure_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS aliases (
                asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                alias TEXT NOT NULL,
                alias_norm TEXT NOT NULL,
                PRIMARY KEY(asset_id, alias)
            );
            CREATE TABLE IF NOT EXISTS ngrams (
                asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                gram TEXT NOT NULL,
                PRIMARY KEY(asset_id, gram)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS asset_fts USING fts5(
                asset_id UNINDEXED,
                search_text,
                tokenize='unicode61 remove_diacritics 2'
            );
            """
        )
        row = self.connection.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is not None and int(row[0]) != INDEX_SCHEMA_VERSION:
            raise VerifierError("knowledge_index_schema_mismatch", "derived index schema version 不匹配", status=500)
        self.connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(INDEX_SCHEMA_VERSION),),
        )
        self.connection.commit()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "KnowledgeIndex":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.close()

    def upsert(self, assets: Iterable[tuple[CanonicalAsset, Path]], ngrams: dict[str, set[str]] | None = None) -> None:
        assert self.connection is not None
        rows = list(assets)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            for asset, path in rows:
                workflow = asset.payload.get("workflow") if isinstance(asset.payload.get("workflow"), dict) else {}
                compatibility = asset.payload.get("compatibility")
                if not isinstance(compatibility, dict):
                    compatibility = workflow.get("compatibility") if isinstance(workflow.get("compatibility"), dict) else {}
                stats = asset.payload.get("stats") if isinstance(asset.payload.get("stats"), dict) else {}
                risk = str(compatibility.get("risk") or "low")
                grams = (ngrams or {}).get(asset.asset_id) or all_ngrams((asset.goal, *asset.aliases))
                self.connection.execute(
                    """
                    INSERT INTO assets(
                        asset_id, kind, app_id, goal, normalized_goal, status, aliases_json,
                        payload_json, evidence_json, canonical_path, created_at,
                        app_version_min, app_version_max, screen_digest, pre_state, post_state,
                        risk_level, success_count, failure_count
                    )
                    VALUES(?, ?, ?, ?, ?, 'approved', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_id) DO UPDATE SET
                        kind=excluded.kind, app_id=excluded.app_id, goal=excluded.goal, normalized_goal=excluded.normalized_goal,
                        aliases_json=excluded.aliases_json, payload_json=excluded.payload_json,
                        evidence_json=excluded.evidence_json, canonical_path=excluded.canonical_path,
                        created_at=excluded.created_at, app_version_min=excluded.app_version_min,
                        app_version_max=excluded.app_version_max, screen_digest=excluded.screen_digest,
                        pre_state=excluded.pre_state, post_state=excluded.post_state,
                        risk_level=excluded.risk_level, success_count=excluded.success_count,
                        failure_count=excluded.failure_count
                    """,
                    (
                        asset.asset_id,
                        asset.kind,
                        asset.app_id,
                        asset.goal,
                        normalize_text(asset.goal),
                        json.dumps(asset.aliases, ensure_ascii=False),
                        json.dumps(asset.payload, ensure_ascii=False, sort_keys=True),
                        json.dumps(asset.evidence, ensure_ascii=False, sort_keys=True),
                        str(path),
                        asset.created_at,
                        compatibility.get("appVersionMin"),
                        compatibility.get("appVersionMax"),
                        compatibility.get("screenDigest"),
                        compatibility.get("preState"),
                        compatibility.get("postState"),
                        risk,
                        int(stats.get("successCount", 1)),
                        int(stats.get("failureCount", 0)),
                    ),
                )
                self.connection.execute("DELETE FROM aliases WHERE asset_id=?", (asset.asset_id,))
                self.connection.executemany(
                    "INSERT INTO aliases(asset_id, alias, alias_norm) VALUES(?, ?, ?)",
                    [(asset.asset_id, alias, normalize_text(alias)) for alias in asset.aliases],
                )
                self.connection.execute("DELETE FROM ngrams WHERE asset_id=?", (asset.asset_id,))
                self.connection.executemany(
                    "INSERT INTO ngrams(asset_id, gram) VALUES(?, ?)",
                    [(asset.asset_id, gram) for gram in sorted(grams)],
                )
                self.connection.execute("DELETE FROM asset_fts WHERE asset_id=?", (asset.asset_id,))
                search_text = " ".join((normalize_text(asset.goal), *(normalize_text(item) for item in asset.aliases), *sorted(grams)))
                self.connection.execute(
                    "INSERT INTO asset_fts(asset_id, search_text) VALUES(?, ?)",
                    (asset.asset_id, search_text),
                )
            self.connection.commit()
        except sqlite3.Error as exc:
            self.connection.rollback()
            raise VerifierError("knowledge_index_write_failed", f"derived index transaction 失败：{exc}", status=500) from exc

    def count(self) -> int:
        assert self.connection is not None
        return int(self.connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def verify(self) -> dict[str, Any]:
        assert self.connection is not None
        integrity = str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        mode = str(self.connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if integrity != "ok" or foreign or mode == "wal":
            raise VerifierError(
                "knowledge_index_invalid",
                "derived index 完整性检查失败",
                status=500,
                details={"integrity": integrity, "foreignKeyFailures": len(foreign), "journalMode": mode},
            )
        return {"integrity": integrity, "foreignKeyFailures": 0, "journalMode": mode, "assetCount": self.count()}

    def exact(self, app_id: str, normalized_query: str, limit: int = 50) -> dict[str, list[str]]:
        assert self.connection is not None
        goals = [
            str(row[0])
            for row in self.connection.execute(
                "SELECT asset_id FROM assets WHERE app_id=? AND normalized_goal=? LIMIT ?",
                (app_id, normalized_query, limit),
            )
        ]
        aliases = [
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT a.asset_id FROM aliases x
                JOIN assets a ON a.asset_id=x.asset_id
                WHERE a.app_id=? AND x.alias_norm=? LIMIT ?
                """,
                (app_id, normalized_query, limit),
            )
        ]
        return {"goal": goals, "alias": aliases}

    def fts(self, app_id: str, query: str, limit: int = 50) -> list[str]:
        assert self.connection is not None
        terms = search_terms(query)
        if not terms:
            return []
        expression = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
        try:
            rows = self.connection.execute(
                """
                SELECT f.asset_id FROM asset_fts f
                JOIN assets a ON a.asset_id=f.asset_id
                WHERE a.app_id=? AND asset_fts MATCH ?
                ORDER BY bm25(asset_fts) LIMIT ?
                """,
                (app_id, expression, limit),
            )
            return [str(row[0]) for row in rows]
        except sqlite3.OperationalError as exc:
            raise VerifierError("knowledge_query_invalid", f"FTS query 失败：{exc}") from exc

    def ngram(self, app_id: str, grams: set[str], limit: int = 50) -> list[tuple[str, int]]:
        assert self.connection is not None
        selected = sorted(grams)[:64]
        if not selected:
            return []
        placeholders = ",".join("?" for _ in selected)
        rows = self.connection.execute(
            f"""
            SELECT n.asset_id, COUNT(*) AS hits FROM ngrams n
            JOIN assets a ON a.asset_id=n.asset_id
            WHERE a.app_id=? AND n.gram IN ({placeholders})
            GROUP BY n.asset_id ORDER BY hits DESC, n.asset_id LIMIT ?
            """,
            (app_id, *selected, limit),
        )
        return [(str(row[0]), int(row[1])) for row in rows]

    def rows(self, asset_ids: set[str]) -> dict[str, dict[str, Any]]:
        assert self.connection is not None
        if not asset_ids:
            return {}
        selected = sorted(asset_ids)
        placeholders = ",".join("?" for _ in selected)
        rows = self.connection.execute(f"SELECT * FROM assets WHERE asset_id IN ({placeholders})", selected)
        return {str(row["asset_id"]): dict(row) for row in rows}

    def get(self, asset_id: str) -> dict[str, Any] | None:
        assert self.connection is not None
        row = self.connection.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        return dict(row) if row is not None else None

    def list(self, app_id: str | None, kind: str | None, limit: int) -> list[dict[str, Any]]:
        assert self.connection is not None
        clauses = []
        values: list[Any] = []
        if app_id:
            clauses.append("app_id=?")
            values.append(app_id)
        if kind:
            clauses.append("kind=?")
            values.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(limit, 200)))
        rows = self.connection.execute(
            f"SELECT * FROM assets {where} ORDER BY created_at DESC, asset_id LIMIT ?",
            values,
        )
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        assert self.connection is not None
        kinds = {
            str(row[0]): int(row[1])
            for row in self.connection.execute("SELECT kind, COUNT(*) FROM assets GROUP BY kind ORDER BY kind")
        }
        apps = {
            str(row[0]): int(row[1])
            for row in self.connection.execute("SELECT app_id, COUNT(*) FROM assets GROUP BY app_id ORDER BY app_id")
        }
        return {"assetCount": sum(kinds.values()), "kinds": kinds, "apps": apps}
