from __future__ import annotations

import json
import random
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..utils import ensure_dir, now_iso
from .changes import ChangeRecord, ChangeType, EntityType


KEY_ALPHABET = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"


def _entity_title(entity_type: str, payload: dict[str, Any]) -> str:
    if entity_type == EntityType.COLLECTION.value:
        return str(payload.get("name") or payload.get("title") or "[collection]")
    if entity_type == EntityType.SEARCH.value:
        return str(payload.get("name") or payload.get("title") or "[search]")
    return str(payload.get("title") or payload.get("name") or f"[{entity_type}]")


class CanonicalStore:
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
                    library_kind TEXT NOT NULL,
                    library_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    editable INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS entities (
                    library_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    title TEXT,
                    version INTEGER NOT NULL DEFAULT 0,
                    remote_version INTEGER,
                    synced INTEGER NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    conflict_json TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (library_id, entity_type, entity_key),
                    FOREIGN KEY (library_id) REFERENCES libraries(library_id)
                );

                CREATE TABLE IF NOT EXISTS change_log (
                    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    library_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    base_version INTEGER,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (library_id) REFERENCES libraries(library_id)
                );

                CREATE INDEX IF NOT EXISTS idx_entities_library_type
                    ON entities (library_id, entity_type, deleted, title);
                CREATE INDEX IF NOT EXISTS idx_changes_library
                    ON change_log (library_id, change_id DESC);
                """
            )
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(entities)").fetchall()
            }
            if "remote_version" not in columns:
                conn.execute("ALTER TABLE entities ADD COLUMN remote_version INTEGER")
            if "conflict_json" not in columns:
                conn.execute("ALTER TABLE entities ADD COLUMN conflict_json TEXT")

    def next_key(self) -> str:
        while True:
            key = "".join(random.choice(KEY_ALPHABET) for _ in range(8))
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM entities WHERE entity_key = ? LIMIT 1",
                    (key,),
                ).fetchone()
            if not row:
                return key

    def upsert_library(
        self,
        library_id: str,
        *,
        name: str,
        source: str = "headless",
        editable: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if ":" not in library_id:
            raise ValueError(f"Invalid library id: {library_id!r}")
        library_kind, library_key = library_id.split(":", 1)
        timestamp = now_iso()
        payload = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO libraries (
                    library_id, library_kind, library_key, name, source, editable,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_id) DO UPDATE SET
                    name = excluded.name,
                    source = excluded.source,
                    editable = excluded.editable,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    library_id,
                    library_kind,
                    library_key,
                    name,
                    source,
                    int(editable),
                    payload,
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_library(library_id) or {}

    def list_libraries(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT library_id, library_kind, library_key, name, source, editable,
                       metadata_json, created_at, updated_at
                FROM libraries
                ORDER BY library_kind, library_key
                """
            ).fetchall()
        return [self._library_row(row) for row in rows]

    def get_library(self, library_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT library_id, library_kind, library_key, name, source, editable,
                       metadata_json, created_at, updated_at
                FROM libraries
                WHERE library_id = ?
                """,
                (library_id,),
            ).fetchone()
        return self._library_row(row) if row else None

    def save_entity(
        self,
        library_id: str,
        entity_type: EntityType | str,
        payload: dict[str, Any],
        *,
        entity_key: str | None = None,
        version: int | None = None,
        remote_version: int | None = None,
        synced: bool = False,
        deleted: bool = False,
        change_type: ChangeType | str | None = None,
        base_version: int | None = None,
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        if not self.get_library(library_id):
            raise ValueError(f"Unknown library: {library_id}")
        existing = None
        if entity_key:
            existing = self.get_entity(library_id, entity_type_value, entity_key)
        key = entity_key or payload.get("key") or self.next_key()
        current_version = int(version if version is not None else ((existing or {}).get("version") or 0))
        if existing and version is None:
            current_version += 1
        current_remote_version = remote_version
        if current_remote_version is None:
            if synced:
                current_remote_version = current_version
            elif existing:
                current_remote_version = existing.get("remote_version")
        title = _entity_title(entity_type_value, payload)
        timestamp = now_iso()
        payload_json = json.dumps({**payload, "key": key}, ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO entities (
                    library_id, entity_type, entity_key, title, version, remote_version, synced, deleted,
                    conflict_json, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_id, entity_type, entity_key) DO UPDATE SET
                    title = excluded.title,
                    version = excluded.version,
                    remote_version = excluded.remote_version,
                    synced = excluded.synced,
                    deleted = excluded.deleted,
                    conflict_json = excluded.conflict_json,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    library_id,
                    entity_type_value,
                    key,
                    title,
                    current_version,
                    current_remote_version,
                    int(synced),
                    int(deleted),
                    None,
                    payload_json,
                    timestamp,
                    timestamp,
                ),
            )
        if change_type:
            self.append_change(
                ChangeRecord(
                    library_id=library_id,
                    entity_type=EntityType(entity_type_value),
                    entity_key=key,
                    change_type=ChangeType(change_type),
                    payload={**payload, "key": key},
                    base_version=base_version if base_version is not None else (existing or {}).get("version"),
                )
            )
        return self.get_entity(library_id, entity_type_value, key) or {}

    def delete_entity(
        self,
        library_id: str,
        entity_type: EntityType | str,
        entity_key: str,
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        existing = self.get_entity(library_id, entity_type_value, entity_key)
        if not existing:
            raise KeyError(f"Entity not found: {library_id}/{entity_type_value}/{entity_key}")
        timestamp = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE entities
                SET deleted = 1, synced = 0, version = ?, conflict_json = NULL, updated_at = ?
                WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                """,
                (
                    int(existing["version"]) + 1,
                    timestamp,
                    library_id,
                    entity_type_value,
                    entity_key,
                ),
            )
        self.append_change(
            ChangeRecord(
                library_id=library_id,
                entity_type=EntityType(entity_type_value),
                entity_key=entity_key,
                change_type=ChangeType.DELETE,
                payload={"key": entity_key},
                base_version=existing["version"],
            )
        )
        return self.get_entity(library_id, entity_type_value, entity_key) or {}

    def get_entity(self, library_id: str, entity_type: EntityType | str, entity_key: str) -> dict[str, Any] | None:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT library_id, entity_type, entity_key, title, version, synced, deleted,
                       remote_version,
                       conflict_json,
                       payload_json, created_at, updated_at
                FROM entities
                WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                """,
                (library_id, entity_type_value, entity_key),
            ).fetchone()
        return self._entity_row(row) if row else None

    def list_entities(
        self,
        library_id: str,
        entity_type: EntityType | str,
        *,
        limit: int = 100,
        query: str | None = None,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        predicates = ["library_id = ?", "entity_type = ?"]
        params: list[Any] = [library_id, entity_type_value]
        if not include_deleted:
            predicates.append("deleted = 0")
        if query:
            predicates.append("(title LIKE ? OR payload_json LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        sql = (
            "SELECT library_id, entity_type, entity_key, title, version, remote_version, synced, deleted, conflict_json, payload_json, created_at, updated_at "
            "FROM entities "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY title COLLATE NOCASE, entity_key LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._entity_row(row) for row in rows]

    def append_change(self, change: ChangeRecord) -> dict[str, Any]:
        payload_json = json.dumps(change.payload, ensure_ascii=True, sort_keys=True)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO change_log (
                    library_id, entity_type, entity_key, change_type, base_version,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change.library_id,
                    change.entity_type.value,
                    change.entity_key,
                    change.change_type.value,
                    change.base_version,
                    payload_json,
                    change.created_at,
                ),
            )
            change_id = int(cursor.lastrowid)
        return self.get_change(change_id) or {}

    def get_change(self, change_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT change_id, library_id, entity_type, entity_key, change_type, base_version,
                       payload_json, created_at
                FROM change_log
                WHERE change_id = ?
                """,
                (change_id,),
            ).fetchone()
        return self._change_row(row) if row else None

    def list_changes(self, *, library_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        predicates: list[str] = []
        params: list[Any] = []
        if library_id:
            predicates.append("library_id = ?")
            params.append(library_id)
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        sql = (
            "SELECT change_id, library_id, entity_type, entity_key, change_type, base_version, payload_json, created_at "
            f"FROM change_log {where} "
            "ORDER BY change_id DESC LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._change_row(row) for row in rows]

    def list_unsynced_entities(
        self,
        library_id: str,
        entity_type: EntityType | str,
        *,
        limit: int = 1000,
        include_conflicts: bool = False,
    ) -> list[dict[str, Any]]:
        return self._list_unsynced_entities(library_id, entity_type, limit=limit, include_conflicts=include_conflicts)

    def _list_unsynced_entities(
        self,
        library_id: str,
        entity_type: EntityType | str,
        *,
        limit: int = 1000,
        include_conflicts: bool = False,
    ) -> list[dict[str, Any]]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        predicates = ["library_id = ?", "entity_type = ?", "synced = 0"]
        if not include_conflicts:
            predicates.append("conflict_json IS NULL")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT library_id, entity_type, entity_key, title, version, remote_version, synced, deleted,
                       conflict_json, payload_json, created_at, updated_at
                FROM entities
                WHERE """ + " AND ".join(predicates) + """
                ORDER BY updated_at, entity_key
                LIMIT ?
                """,
                (library_id, entity_type_value, limit),
            ).fetchall()
        return [self._entity_row(row) for row in rows]

    def list_conflicted_entities(
        self,
        library_id: str,
        entity_type: EntityType | str | None = None,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        predicates = ["library_id = ?", "conflict_json IS NOT NULL"]
        params: list[Any] = [library_id]
        if entity_type is not None:
            entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
            predicates.append("entity_type = ?")
            params.append(entity_type_value)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT library_id, entity_type, entity_key, title, version, remote_version, synced, deleted,
                       conflict_json, payload_json, created_at, updated_at
                FROM entities
                WHERE """ + " AND ".join(predicates) + """
                ORDER BY updated_at, entity_key
                LIMIT ?
                """,
                tuple(params + [limit]),
            ).fetchall()
        return [self._entity_row(row) for row in rows]

    def set_entity_conflict(
        self,
        library_id: str,
        entity_type: EntityType | str,
        entity_key: str,
        conflict: dict[str, Any],
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE entities
                SET conflict_json = ?, updated_at = ?
                WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                """,
                (
                    json.dumps(conflict, ensure_ascii=True, sort_keys=True),
                    now_iso(),
                    library_id,
                    entity_type_value,
                    entity_key,
                ),
            )
        return self.get_entity(library_id, entity_type_value, entity_key) or {}

    def clear_entity_conflict(
        self,
        library_id: str,
        entity_type: EntityType | str,
        entity_key: str,
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE entities
                SET conflict_json = NULL, updated_at = ?
                WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                """,
                (now_iso(), library_id, entity_type_value, entity_key),
            )
        return self.get_entity(library_id, entity_type_value, entity_key) or {}

    def rebase_conflict_keep_local(
        self,
        library_id: str,
        entity_type: EntityType | str,
        entity_key: str,
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        entity = self.get_entity(library_id, entity_type_value, entity_key)
        if not entity:
            raise KeyError(f"Entity not found: {library_id}/{entity_type_value}/{entity_key}")
        conflict = dict(entity.get("conflict") or {})
        remote = conflict.get("remote") or {}
        remote_version = remote.get("version")
        if remote_version is None:
            raise ValueError(f"No remote version available to rebase conflict for {library_id}/{entity_key}")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE entities
                SET remote_version = ?, conflict_json = NULL, updated_at = ?
                WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                """,
                (int(remote_version), now_iso(), library_id, entity_type_value, entity_key),
            )
        return self.get_entity(library_id, entity_type_value, entity_key) or {}

    def accept_remote_conflict(
        self,
        library_id: str,
        entity_type: EntityType | str,
        entity_key: str,
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        entity = self.get_entity(library_id, entity_type_value, entity_key)
        if not entity:
            raise KeyError(f"Entity not found: {library_id}/{entity_type_value}/{entity_key}")
        conflict = dict(entity.get("conflict") or {})
        remote = conflict.get("remote") or {}
        remote_data = remote.get("data")
        remote_version = remote.get("version")
        if not isinstance(remote_data, dict) or remote_version is None:
            raise ValueError(f"No remote payload available to accept for {library_id}/{entity_key}")
        return self.save_entity(
            library_id,
            entity_type_value,
            remote_data,
            entity_key=entity_key,
            version=int(remote_version),
            remote_version=int(remote_version),
            synced=True,
            deleted=False,
        )

    def mark_entity_synced(
        self,
        library_id: str,
        entity_type: EntityType | str,
        entity_key: str,
        *,
        remote_version: int,
        deleted: bool | None = None,
    ) -> dict[str, Any]:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        timestamp = now_iso()
        with self._connect() as conn:
            if deleted is None:
                conn.execute(
                    """
                    UPDATE entities
                    SET synced = 1, version = ?, remote_version = ?, conflict_json = NULL, updated_at = ?
                    WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                    """,
                    (remote_version, remote_version, timestamp, library_id, entity_type_value, entity_key),
                )
            else:
                conn.execute(
                    """
                    UPDATE entities
                    SET synced = 1, deleted = ?, version = ?, remote_version = ?, conflict_json = NULL, updated_at = ?
                    WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                    """,
                    (
                        int(deleted),
                        remote_version,
                        remote_version,
                        timestamp,
                        library_id,
                        entity_type_value,
                        entity_key,
                    ),
                )
        return self.get_entity(library_id, entity_type_value, entity_key) or {}

    def set_library_metadata(self, library_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        library = self.get_library(library_id)
        if not library:
            raise ValueError(f"Unknown library: {library_id}")
        merged = dict(library.get("metadata") or {})
        merged.update(metadata)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE libraries
                SET metadata_json = ?, updated_at = ?
                WHERE library_id = ?
                """,
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), now_iso(), library_id),
            )
        return self.get_library(library_id) or {}

    def mark_missing_deleted(
        self,
        library_id: str,
        entity_type: EntityType | str,
        remote_keys: set[str],
    ) -> int:
        entity_type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT entity_key
                FROM entities
                WHERE library_id = ? AND entity_type = ? AND deleted = 0 AND synced = 1
                """,
                (library_id, entity_type_value),
            ).fetchall()
            local_keys = {row["entity_key"] for row in rows}
            missing = sorted(local_keys - remote_keys)
            if not missing:
                return 0
            conn.executemany(
                """
                UPDATE entities
                SET deleted = 1, synced = 1, conflict_json = NULL, updated_at = ?
                WHERE library_id = ? AND entity_type = ? AND entity_key = ?
                """,
                [(now_iso(), library_id, entity_type_value, key) for key in missing],
            )
            return len(missing)

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            library_count = conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0]
            entity_count = conn.execute("SELECT COUNT(*) FROM entities WHERE deleted = 0").fetchone()[0]
            change_count = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "libraries": library_count,
            "entities": entity_count,
            "changes": change_count,
        }

    def _library_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["editable"] = bool(result["editable"])
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    def _entity_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["synced"] = bool(result["synced"])
        result["deleted"] = bool(result["deleted"])
        result["conflict"] = json.loads(result.pop("conflict_json")) if result.get("conflict_json") else None
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def _change_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result
