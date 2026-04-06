from __future__ import annotations

import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from .utils import (
    annotation_display_title,
    detect_citation_aliases,
    detect_citation_key,
    normalize_annotation_type,
)


READONLY_PREFIXES = ("select", "pragma", "explain", "with")
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|replace|alter|drop|create|attach|detach|vacuum|reindex|analyze|pragma\s+journal_mode)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    candidate = sql.strip().rstrip(";")
    lowered = candidate.lower()
    if not candidate:
        raise ValueError("SQL query is empty")
    if ";" in candidate:
        raise ValueError("Multiple SQL statements are not allowed")
    if not lowered.startswith(READONLY_PREFIXES):
        raise ValueError("Only SELECT/PRAGMA/EXPLAIN/WITH queries are allowed")
    if FORBIDDEN_SQL.search(candidate):
        raise ValueError("Write SQL is not allowed")
    return candidate


class LocalZoteroDB:
    def __init__(self, sqlite_path: Path):
        self.sqlite_path = sqlite_path.expanduser()
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"Local Zotero DB not found: {self.sqlite_path}")

    @contextmanager
    def _connect(self):
        uri = f"file:{self.sqlite_path}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            yield conn

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        candidate = validate_readonly_sql(sql)
        with self._connect() as conn:
            rows = conn.execute(candidate, params).fetchall()
        return [dict(row) for row in rows]

    def _query_optional(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            return self.query(sql, params)
        except sqlite3.DatabaseError:
            return []

    def table_columns(self, table: str) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    def list_tables(self) -> list[str]:
        rows = self.query("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        return [row["name"] for row in rows]

    def has_table(self, table: str) -> bool:
        return table in self.list_tables()

    def list_libraries(self) -> list[dict[str, Any]]:
        library_columns = self.table_columns("libraries")
        group_columns = self.table_columns("groups") if "groups" in self.list_tables() else set()

        select_parts = ["l.libraryID AS libraryID"]
        if "version" in library_columns:
            select_parts.append("l.version AS version")
        if "lastSync" in library_columns:
            select_parts.append("l.lastSync AS lastSync")
        if group_columns:
            select_parts.extend(
                [
                    "CASE WHEN g.groupID IS NULL THEN 'user' ELSE 'group' END AS libraryType",
                    "g.groupID AS groupID",
                ]
            )
            if "name" in group_columns:
                select_parts.append("g.name AS name")
        else:
            select_parts.append("'user' AS libraryType")

        sql = f"SELECT {', '.join(select_parts)} FROM libraries l"
        if group_columns:
            sql += " LEFT JOIN groups g USING (libraryID)"
        sql += " ORDER BY l.libraryID"
        return self.query(sql)

    def list_collections(
        self,
        library_id: int | None = None,
        limit: int = 100,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        predicates: list[str] = []
        params: list[Any] = []
        if library_id is not None:
            predicates.append("libraryID = ?")
            params.append(library_id)
        if not include_deleted and self.has_table("deletedCollections"):
            predicates.append("collectionID NOT IN (SELECT collectionID FROM deletedCollections)")
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
        sql = (
            "SELECT collectionID, libraryID, key, collectionName, version, parentCollectionID "
            "FROM collections "
            f"{where} "
            "ORDER BY libraryID, collectionName LIMIT ?"
        )
        params.append(limit)
        return self._query_optional(sql, tuple(params))

    def get_collection_by_key(self, collection_key: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        where = "key = ?"
        if not include_deleted and self.has_table("deletedCollections"):
            where += " AND collectionID NOT IN (SELECT collectionID FROM deletedCollections)"
        rows = self._query_optional(
            f"""
            SELECT collectionID, libraryID, key, collectionName, version, parentCollectionID
            FROM collections
            WHERE {where}
            LIMIT 1
            """,
            (collection_key,),
        )
        return rows[0] if rows else None

    def list_items(
        self,
        library_id: int | None = None,
        limit: int = 100,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        predicates = ["1=1"]
        params: list[Any] = []
        if library_id is not None:
            predicates.append("i.libraryID = ?")
            params.append(library_id)
        if not include_deleted and self.has_table("deletedItems"):
            predicates.append("i.itemID NOT IN (SELECT itemID FROM deletedItems)")
        sql = f"""
            SELECT
              i.itemID,
              i.libraryID,
              i.key,
              i.version,
              i.synced,
              i.dateAdded,
              i.dateModified,
              it.typeName AS itemType,
              COALESCE(
                MAX(CASE WHEN fc.fieldName = 'title' THEN idv.value END),
                MAX(CASE WHEN fc.fieldName = 'shortTitle' THEN idv.value END),
                MAX(CASE WHEN fc.fieldName = 'caseName' THEN idv.value END),
                n.title,
                '[' || it.typeName || ']'
              ) AS title
            FROM items i
            LEFT JOIN itemTypesCombined it ON it.itemTypeID = i.itemTypeID
            LEFT JOIN itemData id ON id.itemID = i.itemID
            LEFT JOIN fieldsCombined fc ON fc.fieldID = id.fieldID
            LEFT JOIN itemDataValues idv ON idv.valueID = id.valueID
            LEFT JOIN itemNotes n ON n.itemID = i.itemID
            WHERE {" AND ".join(predicates)}
            GROUP BY i.itemID, i.libraryID, i.key, i.version, i.synced, i.dateAdded, i.dateModified, it.typeName, n.title
            ORDER BY i.dateModified DESC
            LIMIT ?
        """
        params.append(limit)
        return self._query_optional(sql, tuple(params))

    def get_item_row(self, item_key: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        where = "i.key = ?"
        if not include_deleted and self.has_table("deletedItems"):
            where += " AND i.itemID NOT IN (SELECT itemID FROM deletedItems)"
        rows = self._query_optional(
            f"""
            SELECT i.itemID, i.libraryID, i.key, i.version, i.synced, i.dateAdded, i.dateModified, it.typeName AS itemType
            FROM items i
            LEFT JOIN itemTypesCombined it ON it.itemTypeID = i.itemTypeID
            WHERE {where}
            LIMIT 1
            """,
            (item_key,),
        )
        return rows[0] if rows else None

    def get_item_type_id(self, item_type: str) -> int | None:
        rows = self._query_optional(
            """
            SELECT itemTypeID
            FROM itemTypesCombined
            WHERE typeName = ?
            LIMIT 1
            """,
            (item_type,),
        )
        if not rows:
            return None
        return int(rows[0]["itemTypeID"])

    def get_field_id(self, field_name: str) -> int | None:
        rows = self._query_optional(
            """
            SELECT fieldID
            FROM fieldsCombined
            WHERE fieldName = ?
            LIMIT 1
            """,
            (field_name,),
        )
        if not rows:
            return None
        return int(rows[0]["fieldID"])

    def get_creator_type_id(self, creator_type: str) -> int | None:
        rows = self._query_optional(
            """
            SELECT creatorTypeID
            FROM creatorTypes
            WHERE creatorType = ?
            LIMIT 1
            """,
            (creator_type,),
        )
        if not rows:
            return None
        return int(rows[0]["creatorTypeID"])

    def get_item_detail(self, item_key: str) -> dict[str, Any] | None:
        where = "i.key = ?"
        if self.has_table("deletedItems"):
            where += " AND i.itemID NOT IN (SELECT itemID FROM deletedItems)"
        item_rows = self._query_optional(
            f"""
            SELECT i.itemID, i.libraryID, i.key, i.version, i.synced, i.dateAdded, i.dateModified, it.typeName AS itemType
            FROM items i
            LEFT JOIN itemTypesCombined it ON it.itemTypeID = i.itemTypeID
            WHERE {where}
            LIMIT 1
            """,
            (item_key,),
        )
        if not item_rows:
            return None
        item = item_rows[0]
        item_id = item["itemID"]

        fields = self._query_optional(
            """
            SELECT fc.fieldName, idv.value
            FROM itemData id
            JOIN fieldsCombined fc ON fc.fieldID = id.fieldID
            JOIN itemDataValues idv ON idv.valueID = id.valueID
            WHERE id.itemID = ?
            ORDER BY fc.fieldName
            """,
            (item_id,),
        )
        creators = self._query_optional(
            """
            SELECT ct.creatorType, cd.firstName, cd.lastName, cd.name, ic.orderIndex
            FROM itemCreators ic
            JOIN creators c ON c.creatorID = ic.creatorID
            JOIN creatorData cd ON cd.creatorDataID = c.creatorDataID
            JOIN creatorTypes ct ON ct.creatorTypeID = ic.creatorTypeID
            WHERE ic.itemID = ?
            ORDER BY ic.orderIndex
            """,
            (item_id,),
        )
        tags = self._query_optional(
            """
            SELECT t.name, it.type
            FROM itemTags it
            JOIN tags t ON t.tagID = it.tagID
            WHERE it.itemID = ?
            ORDER BY t.name
            """,
            (item_id,),
        )
        collections = self._query_optional(
            """
            SELECT c.key, c.collectionName
            FROM collectionItems ci
            JOIN collections c ON c.collectionID = ci.collectionID
            WHERE ci.itemID = ?
            ORDER BY c.collectionName
            """,
            (item_id,),
        )
        note_rows = self._query_optional("SELECT note, title FROM itemNotes WHERE itemID = ?", (item_id,))
        if "parentItemID" in self.table_columns("itemNotes"):
            note_rows = self._query_optional(
                """
                SELECT n.note, n.title, n.parentItemID, parent.key AS parentItemKey
                FROM itemNotes n
                LEFT JOIN items parent ON parent.itemID = n.parentItemID
                WHERE n.itemID = ?
                """,
                (item_id,),
            )
        attachment_rows = self._query_optional(
            """
            SELECT ia.parentItemID, parent.key AS parentItemKey, ia.contentType, ia.path, ia.linkMode
            FROM itemAttachments ia
            LEFT JOIN items parent ON parent.itemID = ia.parentItemID
            WHERE ia.itemID = ?
            """,
            (item_id,),
        )
        annotation_rows = self._query_optional(
            """
            SELECT
              ia.parentItemID,
              parent.key AS parentItemKey,
              ia.type,
              ia.authorName,
              ia.text,
              ia.comment,
              ia.color,
              ia.pageLabel,
              ia.sortIndex,
              ia.position,
              ia.isExternal
            FROM itemAnnotations ia
            LEFT JOIN items parent ON parent.itemID = ia.parentItemID
            WHERE ia.itemID = ?
            """,
            (item_id,),
        ) if self.has_table("itemAnnotations") else []
        normalized_annotations: list[dict[str, Any]] = []
        for row in annotation_rows:
            annotation_type = normalize_annotation_type(row.get("type"))
            normalized_annotations.append(
                {
                    "parentItemID": row.get("parentItemID"),
                    "parentItemKey": row.get("parentItemKey"),
                    "annotationType": annotation_type[0] if annotation_type else row.get("type"),
                    "annotationTypeID": annotation_type[1] if annotation_type else row.get("type"),
                    "annotationAuthorName": row.get("authorName"),
                    "annotationText": row.get("text"),
                    "annotationComment": row.get("comment"),
                    "annotationColor": row.get("color"),
                    "annotationPageLabel": row.get("pageLabel"),
                    "annotationSortIndex": row.get("sortIndex"),
                    "annotationPosition": row.get("position"),
                    "annotationIsExternal": bool(row.get("isExternal")) if row.get("isExternal") is not None else False,
                }
            )

        fields_map = {row["fieldName"]: row["value"] for row in fields}
        payload = {
            **item,
            "fields": fields_map,
            "creators": creators,
            "tags": tags,
            "collections": collections,
            "notes": note_rows,
            "attachments": attachment_rows,
            "annotations": normalized_annotations,
        }
        if item.get("itemType") == "note" and note_rows:
            parent_item_key = note_rows[0].get("parentItemKey")
            if parent_item_key:
                payload["parentItemKey"] = parent_item_key
        if item.get("itemType") == "annotation" and normalized_annotations:
            annotation = normalized_annotations[0]
            payload.update(annotation)
            if not payload.get("title"):
                payload["title"] = annotation_display_title(annotation) or "[annotation]"
        citation_key = detect_citation_key(payload, fields_map)
        if citation_key:
            payload["citationKey"] = citation_key
        citation_aliases = detect_citation_aliases(payload, fields_map)
        if citation_aliases:
            payload["citationAliases"] = citation_aliases
        return payload


class LocalZoteroWriteDB(LocalZoteroDB):
    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self.sqlite_path)) as conn:
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def next_id(self, table: str, id_column: str) -> int:
        with self._connect() as conn:
            value = conn.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 FROM {table}").fetchone()[0]
        return int(value)
