from __future__ import annotations

import json
import random
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .utils import ensure_dir, now_iso


KEY_ALPHABET = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"


def object_title(kind: str, payload: dict[str, Any]) -> str:
    data = payload.get("data", payload)
    if kind == "collection":
        return data.get("name") or payload.get("title") or "[collection]"
    if kind == "search":
        return data.get("name") or payload.get("title") or "[search]"
    return data.get("title") or data.get("name") or payload.get("title") or f"[{kind}]"


class MirrorStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path.expanduser()
        ensure_dir(self.db_path.parent)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS libraries (
                    library_id TEXT PRIMARY KEY,
                    library_type TEXT NOT NULL,
                    remote_id TEXT NOT NULL,
                    name TEXT,
                    version INTEGER DEFAULT 0,
                    meta_version INTEGER DEFAULT 0,
                    editable INTEGER DEFAULT 0,
                    files_editable INTEGER DEFAULT 0,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS objects (
                    library_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    version INTEGER DEFAULT 0,
                    synced INTEGER DEFAULT 1,
                    deleted INTEGER DEFAULT 0,
                    parent_key TEXT,
                    title TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (library_id, kind, object_key)
                );

                CREATE INDEX IF NOT EXISTS idx_objects_library_kind ON objects (library_id, kind, deleted, title);
                """
            )

    def upsert_library(
        self,
        library_id: str,
        library_type: str,
        remote_id: str,
        name: str | None,
        source: str,
        version: int = 0,
        meta_version: int = 0,
        editable: bool = False,
        files_editable: bool = False,
    ) -> None:
        timestamp = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO libraries (
                    library_id, library_type, remote_id, name, version, meta_version,
                    editable, files_editable, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_id) DO UPDATE SET
                    library_type = excluded.library_type,
                    remote_id = excluded.remote_id,
                    name = excluded.name,
                    version = excluded.version,
                    meta_version = excluded.meta_version,
                    editable = excluded.editable,
                    files_editable = excluded.files_editable,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    library_id,
                    library_type,
                    str(remote_id),
                    name,
                    version,
                    meta_version,
                    int(editable),
                    int(files_editable),
                    source,
                    timestamp,
                ),
            )

    def set_library_version(self, library_id: str, version: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE libraries SET version = ?, updated_at = ? WHERE library_id = ?",
                (version, now_iso(), library_id),
            )

    def list_libraries(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM libraries ORDER BY library_type, remote_id").fetchall()
        return [dict(row) for row in rows]

    def get_library(self, library_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM libraries WHERE library_id = ?", (library_id,)).fetchone()
        return dict(row) if row else None

    def upsert_object(
        self,
        library_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        version: int | None = None,
        synced: bool = True,
        deleted: bool = False,
        parent_key: str | None = None,
    ) -> None:
        data = payload.get("data", payload)
        object_key = payload.get("key") or data.get("key")
        if not object_key:
            raise ValueError(f"Object payload is missing a key: {payload!r}")
        object_version = version if version is not None else payload.get("version") or data.get("version") or 0
        derived_parent = parent_key or data.get("parentItem") or data.get("parentCollection")
        title = object_title(kind, payload)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO objects (
                    library_id, kind, object_key, version, synced, deleted,
                    parent_key, title, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_id, kind, object_key) DO UPDATE SET
                    version = excluded.version,
                    synced = excluded.synced,
                    deleted = excluded.deleted,
                    parent_key = excluded.parent_key,
                    title = excluded.title,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    library_id,
                    kind,
                    object_key,
                    object_version,
                    int(synced),
                    int(deleted),
                    derived_parent,
                    title,
                    json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    now_iso(),
                ),
            )

    def mark_missing_deleted(self, library_id: str, kind: str, remote_keys: set[str]) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT object_key FROM objects WHERE library_id = ? AND kind = ? AND deleted = 0",
                (library_id, kind),
            ).fetchall()
            local_keys = {row["object_key"] for row in rows}
            missing = sorted(local_keys - remote_keys)
            if not missing:
                return 0
            conn.executemany(
                "UPDATE objects SET deleted = 1, synced = 1, updated_at = ? WHERE library_id = ? AND kind = ? AND object_key = ?",
                [(now_iso(), library_id, kind, key) for key in missing],
            )
            return len(missing)

    def next_object_key(self) -> str:
        while True:
            key = "".join(random.choice(KEY_ALPHABET) for _ in range(8))
            with self._connect() as conn:
                row = conn.execute("SELECT 1 FROM objects WHERE object_key = ? LIMIT 1", (key,)).fetchone()
            if not row:
                return key

    def list_objects(
        self,
        library_id: str,
        kind: str = "item",
        *,
        limit: int = 100,
        offset: int = 0,
        query: str | None = None,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        predicates = ["library_id = ?", "kind = ?"]
        params: list[Any] = [library_id, kind]
        if not include_deleted:
            predicates.append("deleted = 0")
        if query:
            predicates.append("(title LIKE ? OR payload_json LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        sql = (
            "SELECT library_id, kind, object_key, version, synced, deleted, parent_key, title, payload_json, updated_at "
            "FROM objects "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY title COLLATE NOCASE, object_key LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            results.append(result)
        return results

    def get_object(self, library_id: str, kind: str, object_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT library_id, kind, object_key, version, synced, deleted, parent_key, title, payload_json, updated_at
                FROM objects
                WHERE library_id = ? AND kind = ? AND object_key = ?
                """,
                (library_id, kind, object_key),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def save_local_item(self, library_id: str, item_data: dict[str, Any], *, item_key: str | None = None, replace: bool = False) -> dict[str, Any]:
        existing = self.get_object(library_id, "item", item_key) if item_key else None
        key = item_key or self.next_object_key()
        if existing:
            base = dict(existing["payload"].get("data", {}))
            version = int(existing["version"]) + 1
            if replace:
                merged = dict(item_data)
            else:
                merged = {**base, **item_data}
        else:
            merged = dict(item_data)
            version = 1
        merged["key"] = key
        merged["version"] = version
        merged.setdefault("itemType", "document")
        merged.setdefault("title", merged.get("name") or "[item]")
        merged.setdefault("dateAdded", now_iso())
        merged["dateModified"] = now_iso()
        payload = {"key": key, "version": version, "data": merged}
        self.upsert_object(library_id, "item", payload, version=version, synced=True, deleted=False)
        return self.get_object(library_id, "item", key) or {"payload": payload}

    def delete_local_item(self, library_id: str, item_key: str) -> dict[str, Any] | None:
        current = self.get_object(library_id, "item", item_key)
        if not current:
            return None
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE objects
                SET deleted = 1, version = ?, updated_at = ?, synced = 1
                WHERE library_id = ? AND kind = 'item' AND object_key = ?
                """,
                (int(current["version"]) + 1, now_iso(), library_id, item_key),
            )
        return self.get_object(library_id, "item", item_key)
