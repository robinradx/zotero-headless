from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from ..core import CanonicalStore, ChangeRecord, ChangeType, EntityType
from ..local_db import LocalZoteroDB, LocalZoteroWriteDB
from ..qmd import QmdAutoIndexer
from ..utils import (
    annotation_display_title,
    detect_citation_aliases,
    detect_citation_key,
    format_library_id,
    normalize_annotation_type,
    now_iso,
    parse_library_id,
    set_pinned_citation_aliases_in_extra,
    set_pinned_citation_key_in_extra,
)


class LocalWriteStrategy(StrEnum):
    UNDECIDED = "undecided"
    ZOTERO_APPLY_LAYER = "zotero-apply-layer"
    ZOTERO_DAEMON = "zotero-daemon"


@dataclass(slots=True)
class LocalDesktopCapabilities:
    read_local: bool = True
    write_local: bool = False
    watches_local_changes: bool = False
    strategy: LocalWriteStrategy = LocalWriteStrategy.UNDECIDED


def local_write_strategy_note(strategy: LocalWriteStrategy = LocalWriteStrategy.UNDECIDED) -> str:
    if strategy == LocalWriteStrategy.ZOTERO_APPLY_LAYER:
        return (
            "Use a narrow extracted Zotero-compatible apply layer that only knows how to "
            "translate validated headless changes into local Zotero-compatible writes."
        )
    if strategy == LocalWriteStrategy.ZOTERO_DAEMON:
        return (
            "Use a tiny Zotero-backed daemon whose job is limited to reading and applying "
            "local desktop changes."
        )
    return (
        "The local desktop write path is intentionally undecided. Re-evaluate between a narrow "
        "apply layer and a tiny Zotero-backed daemon once the clean-room core and sync engine exist."
    )


class LocalDesktopAdapter:
    """
    Thin boundary for interoperability with a local Zotero desktop profile.

    The clean-room core should depend on this interface rather than directly on
    Zotero's SQLite schema or vendored runtime details.
    """

    capabilities = LocalDesktopCapabilities()
    EMBEDDED_IMAGE_EXTENSIONS = {
        "image/apng": "apng",
        "image/avif": "avif",
        "image/gif": "gif",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/svg+xml": "svg",
        "image/webp": "webp",
        "image/bmp": "bmp",
    }

    def __init__(self, canonical: CanonicalStore, *, qmd_indexer: QmdAutoIndexer | None = None):
        self.canonical = canonical
        self.qmd_indexer = qmd_indexer

    def _refresh_qmd(self, library_id: str) -> None:
        if not self.qmd_indexer:
            return
        try:
            self.qmd_indexer.refresh_canonical_library(self.canonical, library_id)
        except Exception:
            pass

    def _db(self, data_dir: str) -> LocalZoteroDB:
        sqlite_path = Path(data_dir).expanduser() / "zotero.sqlite"
        return LocalZoteroDB(sqlite_path)

    def _write_db(self, data_dir: str) -> LocalZoteroWriteDB:
        sqlite_path = Path(data_dir).expanduser() / "zotero.sqlite"
        return LocalZoteroWriteDB(sqlite_path)

    def _storage_root(self, data_dir: str) -> Path:
        return Path(data_dir).expanduser() / "storage"

    def _library_id(self, library_row: dict[str, object]) -> str:
        return format_library_id("local", library_row["libraryID"])

    def _collection_payload(self, collection: dict[str, object]) -> dict[str, object]:
        return {
            "key": collection["key"],
            "version": int(collection.get("version") or 0),
            "name": collection.get("collectionName"),
            "parentCollectionID": collection.get("parentCollectionID"),
        }

    def _item_payload(self, detail: dict[str, object]) -> dict[str, object]:
        payload = {
            "key": detail["key"],
            "version": int(detail.get("version") or 0),
            "itemType": detail.get("itemType"),
            "title": detail.get("fields", {}).get("title") or detail.get("title"),
            "dateAdded": detail.get("dateAdded"),
            "dateModified": detail.get("dateModified"),
            "fields": detail.get("fields", {}),
            "creators": detail.get("creators", []),
            "tags": detail.get("tags", []),
            "collections": [collection["key"] for collection in detail.get("collections", [])],
            "notes": detail.get("notes", []),
            "attachments": detail.get("attachments", []),
            "annotations": detail.get("annotations", []),
        }
        if detail.get("itemType") == "note":
            notes = detail.get("notes") or []
            if notes:
                parent_item_key = notes[0].get("parentItemKey")
                if parent_item_key:
                    payload["parentItemKey"] = parent_item_key
        if detail.get("itemType") == "annotation":
            annotations = detail.get("annotations") or []
            if annotations:
                annotation = annotations[0]
                payload.update(annotation)
                payload["title"] = payload.get("title") or annotation_display_title(annotation) or "[annotation]"
        citation_key = detect_citation_key(payload, dict(payload.get("fields") or {}))
        if citation_key:
            payload["citationKey"] = citation_key
        citation_aliases = detect_citation_aliases(payload, dict(payload.get("fields") or {}))
        if citation_aliases:
            payload["citationAliases"] = citation_aliases
        return payload

    def import_snapshot(self, data_dir: str) -> dict[str, object]:
        db = self._db(data_dir)
        summaries: list[dict[str, object]] = []
        totals = {
            "libraries": 0,
            "collections": 0,
            "items": 0,
            "deleted_collections": 0,
            "deleted_items": 0,
        }

        for library in db.list_libraries():
            library_id = self._library_id(library)
            library_version = int(library.get("version") or 0)
            collection_rows = db.list_collections(int(library["libraryID"]), limit=100000)
            item_rows = db.list_items(int(library["libraryID"]), limit=100000)
            self.canonical.upsert_library(
                library_id,
                name=str(library.get("name") or f"local:{library['libraryID']}"),
                source="local-desktop",
                editable=False,
                metadata={
                    "local_library_type": library.get("libraryType"),
                    "group_id": library.get("groupID"),
                    "local_library_version": library_version,
                    "local_last_sync": library.get("lastSync"),
                    "last_local_snapshot": now_iso(),
                },
            )

            collection_keys: set[str] = set()
            for collection in collection_rows:
                payload = self._collection_payload(collection)
                self.canonical.save_entity(
                    library_id,
                    EntityType.COLLECTION,
                    payload,
                    entity_key=str(collection["key"]),
                    version=int(collection.get("version") or 0),
                    remote_version=int(collection.get("version") or 0),
                    synced=True,
                    deleted=False,
                )
                collection_keys.add(str(collection["key"]))

            item_keys: set[str] = set()
            for item in item_rows:
                detail = db.get_item_detail(str(item["key"]))
                if not detail:
                    continue
                payload = self._item_payload(detail)
                self.canonical.save_entity(
                    library_id,
                    EntityType.ITEM,
                    payload,
                    entity_key=str(item["key"]),
                    version=int(item.get("version") or 0),
                    remote_version=int(item.get("version") or 0),
                    synced=True,
                    deleted=False,
                )
                item_keys.add(str(item["key"]))

            deleted_collections = self.canonical.mark_missing_deleted(library_id, EntityType.COLLECTION, collection_keys)
            deleted_items = self.canonical.mark_missing_deleted(library_id, EntityType.ITEM, item_keys)
            self.canonical.set_library_metadata(
                library_id,
                {
                    "local_library_type": library.get("libraryType"),
                    "group_id": library.get("groupID"),
                    "local_library_version": library_version,
                    "local_last_sync": library.get("lastSync"),
                    "last_local_snapshot": now_iso(),
                    "local_collection_count": len(collection_keys),
                    "local_item_count": len(item_keys),
                },
            )

            summary = {
                "library_id": library_id,
                "collections": len(collection_keys),
                "items": len(item_keys),
                "deleted_collections": deleted_collections,
                "deleted_items": deleted_items,
            }
            self._refresh_qmd(library_id)
            summaries.append(summary)
            totals["libraries"] += 1
            totals["collections"] += len(collection_keys)
            totals["items"] += len(item_keys)
            totals["deleted_collections"] += deleted_collections
            totals["deleted_items"] += deleted_items

        return {
            **totals,
            "data_dir": str(Path(data_dir).expanduser()),
            "libraries_detail": summaries,
        }

    def poll_changes(self, data_dir: str, *, since_version: int | None = None) -> list[ChangeRecord]:
        db = self._db(data_dir)
        changes: list[ChangeRecord] = []

        for library in db.list_libraries():
            library_id = self._library_id(library)
            current_collections = {
                str(collection["key"]): collection
                for collection in db.list_collections(int(library["libraryID"]), limit=100000)
            }
            canonical_collections = {
                entity["entity_key"]: entity
                for entity in self.canonical.list_entities(
                    library_id,
                    EntityType.COLLECTION,
                    limit=100000,
                    include_deleted=True,
                )
            }
            changes.extend(
                self._detect_collection_changes(
                    library_id,
                    current_collections,
                    canonical_collections,
                    since_version=since_version,
                )
            )

            current_items = {
                str(item["key"]): item
                for item in db.list_items(int(library["libraryID"]), limit=100000)
            }
            canonical_items = {
                entity["entity_key"]: entity
                for entity in self.canonical.list_entities(
                    library_id,
                    EntityType.ITEM,
                    limit=100000,
                    include_deleted=True,
                )
            }
            changes.extend(
                self._detect_item_changes(
                    db,
                    library_id,
                    current_items,
                    canonical_items,
                    since_version=since_version,
                )
            )

        return changes

    def _detect_collection_changes(
        self,
        library_id: str,
        current_collections: dict[str, dict[str, object]],
        canonical_collections: dict[str, dict[str, object]],
        *,
        since_version: int | None = None,
    ) -> list[ChangeRecord]:
        changes: list[ChangeRecord] = []
        for key, collection in current_collections.items():
            payload = self._collection_payload(collection)
            version = int(collection.get("version") or 0)
            existing = canonical_collections.get(key)
            if not existing:
                changes.append(
                    ChangeRecord(
                        library_id=library_id,
                        entity_type=EntityType.COLLECTION,
                        entity_key=key,
                        change_type=ChangeType.CREATE,
                        payload=payload,
                    )
                )
                continue
            if since_version is not None and version <= since_version:
                continue
            if existing.get("deleted") or int(existing["version"]) != version or existing["payload"] != payload:
                changes.append(
                    ChangeRecord(
                        library_id=library_id,
                        entity_type=EntityType.COLLECTION,
                        entity_key=key,
                        change_type=ChangeType.UPDATE,
                        payload=payload,
                        base_version=int(existing["version"]),
                    )
                )
        for key, existing in canonical_collections.items():
            if key not in current_collections and not existing.get("deleted"):
                changes.append(
                    ChangeRecord(
                        library_id=library_id,
                        entity_type=EntityType.COLLECTION,
                        entity_key=key,
                        change_type=ChangeType.DELETE,
                        payload={"key": key},
                        base_version=int(existing["version"]),
                    )
                )
        return changes

    def _detect_item_changes(
        self,
        db: LocalZoteroDB,
        library_id: str,
        current_items: dict[str, dict[str, object]],
        canonical_items: dict[str, dict[str, object]],
        *,
        since_version: int | None = None,
    ) -> list[ChangeRecord]:
        changes: list[ChangeRecord] = []
        for key, item in current_items.items():
            detail = db.get_item_detail(key)
            if not detail:
                continue
            payload = self._item_payload(detail)
            version = int(item.get("version") or 0)
            existing = canonical_items.get(key)
            if not existing:
                changes.append(
                    ChangeRecord(
                        library_id=library_id,
                        entity_type=EntityType.ITEM,
                        entity_key=key,
                        change_type=ChangeType.CREATE,
                        payload=payload,
                    )
                )
                continue
            if since_version is not None and version <= since_version:
                continue
            if existing.get("deleted") or int(existing["version"]) != version or existing["payload"] != payload:
                changes.append(
                    ChangeRecord(
                        library_id=library_id,
                        entity_type=EntityType.ITEM,
                        entity_key=key,
                        change_type=ChangeType.UPDATE,
                        payload=payload,
                        base_version=int(existing["version"]),
                    )
                )
        for key, existing in canonical_items.items():
            if key not in current_items and not existing.get("deleted"):
                changes.append(
                    ChangeRecord(
                        library_id=library_id,
                        entity_type=EntityType.ITEM,
                        entity_key=key,
                        change_type=ChangeType.DELETE,
                        payload={"key": key},
                        base_version=int(existing["version"]),
                    )
                )
        return changes

    def apply_changes(self, data_dir: str, changes: list[ChangeRecord]) -> dict[str, object]:
        raise NotImplementedError(local_write_strategy_note(self.capabilities.strategy))

    def apply_pending_writes(
        self,
        data_dir: str,
        *,
        library_id: str | None = None,
        limit: int = 1000,
    ) -> dict[str, object]:
        plan = self.plan_pending_writes(data_dir, library_id=library_id, limit=limit)
        writer = self._write_db(data_dir)
        applied: list[dict[str, object]] = []
        blocked: list[dict[str, object]] = []
        failed: list[dict[str, object]] = []

        for operation in plan["operations"]:
            if operation["status"] != "plannable":
                blocked.append(operation)
                continue
            try:
                self._apply_planned_operation(writer, operation, data_dir=data_dir)
                applied.append(operation)
            except Exception as exc:
                failed.append({**operation, "error": str(exc)})

        snapshot = self.import_snapshot(data_dir)
        return {
            "data_dir": str(Path(data_dir).expanduser()),
            "libraries": plan["libraries"],
            "applied": len(applied),
            "blocked": len(blocked),
            "failed": len(failed),
            "applied_operations": applied,
            "blocked_operations": blocked,
            "failed_operations": failed,
            "snapshot": snapshot,
        }

    def plan_pending_writes(
        self,
        data_dir: str,
        *,
        library_id: str | None = None,
        limit: int = 1000,
    ) -> dict[str, object]:
        db = self._db(data_dir)
        libraries = [library_id] if library_id else [
            library["library_id"]
            for library in self.canonical.list_libraries()
            if library["library_id"].startswith("local:")
        ]

        operations: list[dict[str, object]] = []
        for current_library_id in libraries:
            operations.extend(self._plan_library_pending_writes(db, current_library_id, limit=limit))

        plannable = sum(1 for operation in operations if operation["status"] == "plannable")
        blocked = len(operations) - plannable
        return {
            "data_dir": str(Path(data_dir).expanduser()),
            "libraries": libraries,
            "operations": operations,
            "summary": {
                "total": len(operations),
                "plannable": plannable,
                "blocked": blocked,
            },
            "strategy": self.capabilities.strategy.value,
            "note": local_write_strategy_note(self.capabilities.strategy),
        }

    def _plan_library_pending_writes(
        self,
        db: LocalZoteroDB,
        library_id: str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        operations: list[dict[str, object]] = []
        collection_entities = self.canonical.list_unsynced_entities(library_id, EntityType.COLLECTION, limit=limit)
        item_entities = self.canonical.list_unsynced_entities(library_id, EntityType.ITEM, limit=limit)
        pending_collection_keys = {
            entity["entity_key"]
            for entity in collection_entities
            if not entity["deleted"]
        }
        pending_item_keys = {
            entity["entity_key"]
            for entity in item_entities
            if not entity["deleted"]
        }
        for entity in collection_entities:
            operations.append(
                self._plan_collection_write(
                    db,
                    library_id,
                    entity,
                    pending_collection_keys=pending_collection_keys,
                )
            )
        for entity in item_entities:
            operations.append(
                self._plan_item_write(
                    db,
                    library_id,
                    entity,
                    pending_collection_keys=pending_collection_keys,
                    pending_item_keys=pending_item_keys,
                )
            )
        return self._order_planned_operations(operations)

    def _order_planned_operations(self, operations: list[dict[str, object]]) -> list[dict[str, object]]:
        if not operations:
            return operations
        by_key = {
            (str(operation["entity_type"]), str(operation["entity_key"])): operation
            for operation in operations
        }

        def dependency_keys(operation: dict[str, object]) -> list[tuple[str, str]]:
            details = dict(operation.get("details") or {})
            deps: list[tuple[str, str]] = []
            if operation["entity_type"] == "collection":
                parent_key = details.get("parentCollectionKey")
                if isinstance(parent_key, str) and parent_key:
                    deps.append(("collection", parent_key))
            elif operation["entity_type"] == "item":
                note = details.get("note")
                if isinstance(note, dict):
                    parent_item_key = note.get("parentItemKey")
                    if isinstance(parent_item_key, str) and parent_item_key:
                        deps.append(("item", parent_item_key))
                annotation = details.get("annotation")
                if isinstance(annotation, dict):
                    parent_item_key = annotation.get("parentItemKey")
                    if isinstance(parent_item_key, str) and parent_item_key:
                        deps.append(("item", parent_item_key))
                attachment = details.get("attachment")
                if isinstance(attachment, dict):
                    parent_item_key = attachment.get("parentItemKey")
                    if isinstance(parent_item_key, str) and parent_item_key:
                        deps.append(("item", parent_item_key))
                for collection_key in details.get("collections") or []:
                    if isinstance(collection_key, str) and collection_key:
                        deps.append(("collection", collection_key))
            return deps

        def action_rank(operation: dict[str, object]) -> int:
            action = str(operation.get("action") or "")
            if action.startswith("create-"):
                return 0
            if action.startswith("update-"):
                return 1
            if action.startswith("trash-"):
                return 2
            return 3

        active = [operation for operation in operations if not str(operation.get("action") or "").startswith("trash-")]
        deleted = [operation for operation in operations if str(operation.get("action") or "").startswith("trash-")]

        def topo(items: list[dict[str, object]], *, reverse: bool = False) -> list[dict[str, object]]:
            ordered: list[dict[str, object]] = []
            visiting: set[tuple[str, str]] = set()
            visited: set[tuple[str, str]] = set()

            def visit(operation: dict[str, object]) -> None:
                key = (str(operation["entity_type"]), str(operation["entity_key"]))
                if key in visited:
                    return
                if key in visiting:
                    ordered.append(operation)
                    visited.add(key)
                    return
                visiting.add(key)
                for dep in dependency_keys(operation):
                    dep_operation = by_key.get(dep)
                    if dep_operation and dep_operation in items:
                        visit(dep_operation)
                visiting.remove(key)
                visited.add(key)
                ordered.append(operation)

            for operation in sorted(items, key=lambda op: (action_rank(op), str(op["entity_type"]), str(op["entity_key"]))):
                visit(operation)
            return list(reversed(ordered)) if reverse else ordered

        return topo(active) + topo(deleted, reverse=True)

    def _plan_collection_write(
        self,
        db: LocalZoteroDB,
        library_id: str,
        entity: dict[str, object],
        *,
        pending_collection_keys: set[str] | None = None,
    ) -> dict[str, object]:
        payload = dict(entity["payload"])
        local = db.get_collection_by_key(str(entity["entity_key"]))
        blocked: list[str] = []
        warnings: list[str] = []
        details: dict[str, object] = {"name": payload.get("name")}
        tables = ["collections"]
        pending_collection_keys = pending_collection_keys or set()

        parent_key = payload.get("parentCollectionKey")
        if parent_key:
            parent = db.get_collection_by_key(str(parent_key))
            if not parent:
                if parent_key not in pending_collection_keys:
                    blocked.append(f"Parent collection {parent_key} does not exist locally")
            else:
                details["parentCollectionID"] = int(parent["collectionID"])
            details["parentCollectionKey"] = str(parent_key)
        elif payload.get("parentCollectionID"):
            warnings.append("Planner ignores raw parentCollectionID and expects parentCollectionKey for moves")

        if entity["deleted"]:
            action = "trash-collection"
            tables = ["deletedCollections"]
            if not local:
                blocked.append("Collection does not exist locally")
        elif not local:
            action = "create-collection"
        else:
            action = "update-collection"

        status = "blocked" if blocked else "plannable"
        return {
            "library_id": library_id,
            "entity_type": "collection",
            "entity_key": entity["entity_key"],
            "action": action,
            "status": status,
            "tables": tables,
            "blocked": blocked,
            "warnings": warnings,
            "details": details,
        }

    def _plan_item_write(
        self,
        db: LocalZoteroDB,
        library_id: str,
        entity: dict[str, object],
        *,
        pending_collection_keys: set[str] | None = None,
        pending_item_keys: set[str] | None = None,
    ) -> dict[str, object]:
        payload = dict(entity["payload"])
        local = db.get_item_detail(str(entity["entity_key"]))
        blocked: list[str] = []
        warnings: list[str] = []
        tables = ["items", "itemData", "itemDataValues"]
        details: dict[str, object] = {}
        pending_collection_keys = pending_collection_keys or set()
        pending_item_keys = pending_item_keys or set()

        if entity["deleted"]:
            action = "trash-item"
            tables = ["deletedItems"]
            if not local:
                blocked.append("Item does not exist locally")
            status = "blocked" if blocked else "plannable"
            return {
                "library_id": library_id,
                "entity_type": "item",
                "entity_key": entity["entity_key"],
                "action": action,
                "status": status,
                "tables": tables,
                "blocked": blocked,
                "warnings": warnings,
                "details": details,
            }

        item_type = payload.get("itemType")
        if not item_type:
            blocked.append("Missing itemType")
        elif db.get_item_type_id(str(item_type)) is None:
            blocked.append(f"Unknown Zotero item type: {item_type}")
        details["itemType"] = item_type

        field_ops: list[dict[str, object]] = []
        if item_type != "annotation":
            supported_fields = self._canonical_item_fields(payload)
            citation_key = supported_fields.get("citationKey")
            if citation_key is not None and db.get_field_id("citationKey") is None:
                if db.get_field_id("extra") is not None:
                    supported_fields["extra"] = set_pinned_citation_key_in_extra(
                        str(supported_fields.get("extra") or payload.get("extra") or ""),
                        str(citation_key),
                    )
                    del supported_fields["citationKey"]
                else:
                    blocked.append("Citation key writeback requires either citationKey or extra field support locally")
            for field_name, field_value in supported_fields.items():
                if db.get_field_id(field_name) is None:
                    blocked.append(f"Unknown Zotero field: {field_name}")
                else:
                    field_ops.append({"field": field_name, "value": field_value})
        details["fields"] = field_ops

        creators = payload.get("creators") or []
        if creators:
            required_creator_tables = ["itemCreators", "creators", "creatorData", "creatorTypes"]
            tables.extend(required_creator_tables[:-1])
            missing_creator_tables = [table for table in required_creator_tables if not db.has_table(table)]
            if missing_creator_tables:
                blocked.append(f"Missing local creator tables: {', '.join(missing_creator_tables)}")
            creator_ops: list[dict[str, object]] = []
            for creator in creators:
                normalized_creator = self._normalize_creator(creator)
                if not normalized_creator:
                    blocked.append(f"Invalid creator payload: {creator!r}")
                    continue
                creator_type = str(normalized_creator["creatorType"])
                if db.get_creator_type_id(creator_type) is None:
                    blocked.append(f"Unknown Zotero creator type: {creator_type}")
                    continue
                creator_ops.append(normalized_creator)
            if creator_ops:
                details["creators"] = creator_ops

        tags = payload.get("tags") or []
        if tags:
            required_tag_tables = ["itemTags", "tags"]
            tables.extend(required_tag_tables)
            missing_tag_tables = [table for table in required_tag_tables if not db.has_table(table)]
            if missing_tag_tables:
                blocked.append(f"Missing local tag tables: {', '.join(missing_tag_tables)}")
            tag_ops: list[dict[str, object]] = []
            for tag in tags:
                normalized_tag = self._normalize_tag(tag)
                if not normalized_tag:
                    blocked.append(f"Invalid tag payload: {tag!r}")
                    continue
                tag_ops.append(normalized_tag)
            if tag_ops:
                details["tags"] = tag_ops
        normalized_note = self._normalize_item_note(payload)
        if normalized_note is not None:
            if normalized_note.get("__blocked__"):
                blocked.append(str(normalized_note.get("reason") or "Unsupported note payload"))
            else:
                tables.append("itemNotes")
                if not db.has_table("itemNotes"):
                    blocked.append("Missing local itemNotes table")
                else:
                    parent_item_key = normalized_note.get("parentItemKey")
                    if parent_item_key and not db.get_item_row(str(parent_item_key)):
                        if parent_item_key not in pending_item_keys:
                            blocked.append(f"Referenced parent item does not exist locally: {parent_item_key}")
                    details["note"] = normalized_note
        normalized_annotation = self._normalize_item_annotation(payload)
        if normalized_annotation is not None:
            if normalized_annotation.get("__blocked__"):
                blocked.append(str(normalized_annotation.get("reason") or "Unsupported annotation payload"))
            else:
                tables.append("itemAnnotations")
                if not db.has_table("itemAnnotations"):
                    blocked.append("Missing local itemAnnotations table")
                else:
                    parent_item_key = normalized_annotation.get("parentItemKey")
                    parent_item = db.get_item_row(str(parent_item_key)) if parent_item_key else None
                    if parent_item_key and not parent_item:
                        if parent_item_key not in pending_item_keys:
                            blocked.append(f"Referenced parent item does not exist locally: {parent_item_key}")
                    elif parent_item and parent_item.get("itemType") != "attachment":
                        blocked.append(f"Annotation parent must be an attachment item: {parent_item_key}")
                    details["annotation"] = normalized_annotation
        normalized_attachment = self._normalize_attachment_payload(payload, local)
        if normalized_attachment is not None:
            if normalized_attachment.get("__blocked__"):
                blocked.append(str(normalized_attachment.get("reason") or "Unsupported attachment payload"))
            else:
                tables.append("itemAttachments")
                if not db.has_table("itemAttachments"):
                    blocked.append("Missing local itemAttachments table")
                else:
                    attachment_blocked, attachment_warnings = self._validate_attachment_payload(normalized_attachment)
                    blocked.extend(attachment_blocked)
                    warnings.extend(attachment_warnings)
                    parent_item_key = normalized_attachment.get("parentItemKey")
                    if parent_item_key and not db.get_item_row(str(parent_item_key)):
                        if parent_item_key not in pending_item_keys:
                            blocked.append(f"Referenced parent item does not exist locally: {parent_item_key}")
                    if not attachment_blocked and (
                        not parent_item_key
                        or db.get_item_row(str(parent_item_key))
                        or parent_item_key in pending_item_keys
                    ):
                        details["attachment"] = normalized_attachment
        attachments = payload.get("attachments") or []
        if attachments and not details.get("attachment"):
            blocked.append("Attachment writeback is not implemented yet")

        collections = payload.get("collections") or []
        if collections:
            tables.append("collectionItems")
            if not db.has_table("collectionItems"):
                blocked.append("Missing local collectionItems table")
            missing = [
                key
                for key in collections
                if not db.get_collection_by_key(str(key)) and str(key) not in pending_collection_keys
            ]
            if missing:
                blocked.append(f"Referenced collections do not exist locally: {', '.join(map(str, missing))}")
            else:
                details["collections"] = list(collections)

        if local:
            action = "update-item"
            details["local_version"] = int(local.get("version") or 0)
        else:
            action = "create-item"

        status = "blocked" if blocked else "plannable"
        return {
            "library_id": library_id,
            "entity_type": "item",
            "entity_key": entity["entity_key"],
            "action": action,
            "status": status,
            "tables": tables,
            "blocked": blocked,
            "warnings": warnings,
            "details": details,
        }

    def _canonical_item_fields(self, payload: dict[str, object]) -> dict[str, object]:
        fields = dict(payload.get("fields") or {})
        if payload.get("title") is not None:
            fields["title"] = payload["title"]
        citation_key = detect_citation_key(dict(payload), fields)
        citation_aliases = detect_citation_aliases(dict(payload), fields)
        if citation_key:
            fields["citationKey"] = citation_key
            existing_extra = payload.get("extra")
            if existing_extra is None:
                existing_extra = fields.get("extra")
            fields["extra"] = set_pinned_citation_key_in_extra(str(existing_extra or ""), citation_key)
        if citation_aliases:
            existing_extra = payload.get("extra")
            if existing_extra is None:
                existing_extra = fields.get("extra")
            fields["extra"] = set_pinned_citation_aliases_in_extra(str(existing_extra or ""), citation_aliases)
        for key in ("abstractNote", "url", "date", "publicationTitle", "websiteTitle", "extra", "accessDate", "shortTitle"):
            if payload.get(key) is not None:
                if key == "extra" and "extra" in fields:
                    continue
                fields[key] = payload[key]
        return fields

    def _supports_field(self, fields: dict[str, object], field_name: str, payload: dict[str, object]) -> bool:
        return field_name in fields or payload.get(field_name) is not None

    def _normalize_tag(self, tag: object) -> dict[str, object] | None:
        if isinstance(tag, str):
            name = tag.strip()
            if not name:
                return None
            return {"name": name, "type": 0}
        if not isinstance(tag, dict):
            return None
        name = str(tag.get("name") or "").strip()
        if not name:
            return None
        try:
            tag_type = int(tag.get("type", 0))
        except (TypeError, ValueError):
            return None
        return {"name": name, "type": tag_type}

    def _normalize_creator(self, creator: object) -> dict[str, object] | None:
        if not isinstance(creator, dict):
            return None
        creator_type = str(creator.get("creatorType") or "").strip()
        if not creator_type:
            return None
        normalized: dict[str, object] = {"creatorType": creator_type}
        name = str(creator.get("name") or "").strip()
        first_name = str(creator.get("firstName") or "").strip()
        last_name = str(creator.get("lastName") or "").strip()
        if name:
            normalized["name"] = name
            return normalized
        if first_name or last_name:
            normalized["firstName"] = first_name
            normalized["lastName"] = last_name
            return normalized
        return None

    def _normalize_item_note(self, payload: dict[str, object]) -> dict[str, object] | None:
        if payload.get("note") is not None:
            return {
                "note": str(payload.get("note") or ""),
                "title": str(payload.get("title") or ""),
                "parentItemKey": str(payload.get("parentItemKey") or "") or None,
            }
        notes = payload.get("notes") or []
        if not notes:
            return None
        if len(notes) != 1:
            return {
                "__blocked__": True,
                "reason": "Only single-note writeback is implemented for itemNotes-backed local notes",
            }
        note = notes[0]
        if isinstance(note, str):
            return {
                "note": note,
                "title": str(payload.get("title") or ""),
                "parentItemKey": str(payload.get("parentItemKey") or "") or None,
            }
        if isinstance(note, dict):
            return {
                "note": str(note.get("note") or ""),
                "title": str(note.get("title") or payload.get("title") or ""),
                "parentItemKey": str(note.get("parentItemKey") or payload.get("parentItemKey") or "") or None,
            }
        return {
            "__blocked__": True,
            "reason": f"Invalid note payload: {note!r}",
        }

    def _normalize_item_annotation(self, payload: dict[str, object]) -> dict[str, object] | None:
        if payload.get("itemType") != "annotation" and not payload.get("annotationType") and not payload.get("annotations"):
            return None
        annotation_source: dict[str, object]
        annotations = payload.get("annotations") or []
        if isinstance(annotations, list) and len(annotations) == 1 and isinstance(annotations[0], dict):
            annotation_source = {**annotations[0], **payload}
        else:
            annotation_source = dict(payload)

        normalized_type = normalize_annotation_type(
            annotation_source.get("annotationType") or annotation_source.get("annotationTypeID") or annotation_source.get("type")
        )
        if normalized_type is None:
            return {
                "__blocked__": True,
                "reason": f"Invalid annotation type: {annotation_source.get('annotationType') or annotation_source.get('annotationTypeID') or annotation_source.get('type')!r}",
            }
        sort_index = annotation_source.get("annotationSortIndex")
        is_external = annotation_source.get("annotationIsExternal")
        normalized: dict[str, object] = {
            "annotationType": normalized_type[0],
            "annotationTypeID": normalized_type[1],
            "parentItemKey": str(annotation_source.get("parentItemKey") or "") or None,
            "annotationAuthorName": str(annotation_source.get("annotationAuthorName") or annotation_source.get("authorName") or "") or None,
            "annotationText": str(annotation_source.get("annotationText") or annotation_source.get("text") or ""),
            "annotationComment": str(annotation_source.get("annotationComment") or annotation_source.get("comment") or ""),
            "annotationColor": str(annotation_source.get("annotationColor") or annotation_source.get("color") or "") or None,
            "annotationPageLabel": str(annotation_source.get("annotationPageLabel") or annotation_source.get("pageLabel") or "") or None,
            "annotationSortIndex": str(sort_index) if sort_index is not None else None,
            "annotationPosition": annotation_source.get("annotationPosition") or annotation_source.get("position"),
            "annotationIsExternal": bool(is_external) if is_external is not None else False,
        }
        if not normalized["parentItemKey"]:
            return {
                "__blocked__": True,
                "reason": "Annotation writeback requires parentItemKey",
            }
        if normalized["annotationPosition"] is not None:
            normalized["annotationPosition"] = str(normalized["annotationPosition"])
        return normalized

    def _normalize_attachment_payload(
        self,
        payload: dict[str, object],
        local: dict[str, object] | None,
    ) -> dict[str, object] | None:
        attachment_rows = list(payload.get("attachments") or [])
        source: dict[str, object] = {}
        if payload.get("itemType") == "attachment":
            source = {
                "path": payload.get("path"),
                "contentType": payload.get("contentType"),
                "linkMode": payload.get("linkMode"),
                "parentItemKey": payload.get("parentItemKey"),
                "sourcePath": payload.get("sourcePath"),
                "filename": payload.get("filename"),
                "url": payload.get("url"),
            }
            if not any(value is not None for value in source.values()) and len(attachment_rows) == 1 and isinstance(attachment_rows[0], dict):
                source = dict(attachment_rows[0])
        else:
            return None

        if not source and local and len(local.get("attachments") or []) == 1:
            source = dict((local.get("attachments") or [])[0])

        if not source:
            return {
                "__blocked__": True,
                "reason": "Attachment payload is missing path/link metadata",
            }

        link_mode = source.get("linkMode")
        if isinstance(link_mode, str):
            normalized = link_mode.strip().lower()
            if normalized == "imported_file":
                link_mode = 0
            elif normalized == "imported_url":
                link_mode = 1
            elif normalized == "linked_file":
                link_mode = 2
            elif normalized == "linked_url":
                link_mode = 3
            elif normalized == "embedded_image":
                link_mode = 4
            else:
                return {
                    "__blocked__": True,
                    "reason": f"Invalid attachment linkMode: {link_mode!r}",
                }
        elif link_mode is not None:
            try:
                link_mode = int(link_mode)
            except (TypeError, ValueError):
                return {
                    "__blocked__": True,
                    "reason": f"Invalid attachment linkMode: {link_mode!r}",
                }
        source_path = source.get("sourcePath")
        path_value = source.get("path")
        if link_mode is None:
            if source_path:
                link_mode = 1 if self._looks_like_url(source.get("url")) else 0
            elif isinstance(path_value, str) and path_value.startswith("storage:"):
                link_mode = 1 if self._looks_like_url(source.get("url")) else 0
            elif self._looks_like_url(path_value):
                link_mode = 3
            elif isinstance(path_value, str) and path_value:
                link_mode = 2
        if self._looks_like_url(source.get("url")) and not path_value and link_mode == 3:
            path_value = source.get("url")
        return {
            "path": path_value,
            "contentType": source.get("contentType"),
            "linkMode": link_mode,
            "parentItemKey": source.get("parentItemKey"),
            "sourcePath": source_path,
            "filename": source.get("filename"),
        }

    def _validate_attachment_payload(self, attachment_payload: dict[str, object]) -> tuple[list[str], list[str]]:
        blocked: list[str] = []
        warnings: list[str] = []
        link_mode = attachment_payload.get("linkMode")
        path_value = attachment_payload.get("path")
        source_path = attachment_payload.get("sourcePath")

        if link_mode not in {0, 1, 2, 3, 4}:
            blocked.append(
                "Only imported_file, imported_url, linked_file, linked_url, and embedded_image attachment writeback are implemented locally"
            )
            return blocked, warnings

        if link_mode == 0:
            if source_path:
                source_file = Path(str(source_path)).expanduser()
                if not source_file.exists():
                    blocked.append(f"Attachment source file not found: {source_file}")
            elif not (isinstance(path_value, str) and path_value.startswith("storage:")):
                blocked.append("Imported-file attachments require sourcePath or a storage: path")
            return blocked, warnings

        if link_mode == 1:
            if source_path:
                source_file = Path(str(source_path)).expanduser()
                if not source_file.exists():
                    blocked.append(f"Attachment source file not found: {source_file}")
            elif not (isinstance(path_value, str) and path_value.startswith("storage:")):
                blocked.append("Imported-url attachments require sourcePath or a storage: path")
            return blocked, warnings

        if link_mode == 4:
            content_type = str(attachment_payload.get("contentType") or "").strip().lower()
            if content_type not in self.EMBEDDED_IMAGE_EXTENSIONS:
                blocked.append(
                    f"Unsupported embedded image content type: {attachment_payload.get('contentType')!r}"
                )
            if source_path:
                source_file = Path(str(source_path)).expanduser()
                if not source_file.exists():
                    blocked.append(f"Embedded image source file not found: {source_file}")
                elif source_file.is_dir():
                    blocked.append("Embedded-image attachments require a single source file, not a directory")
            elif not (isinstance(path_value, str) and path_value.startswith("storage:")):
                blocked.append("Embedded-image attachments require sourcePath or a storage: path")
            return blocked, warnings

        if link_mode == 2 and source_path:
            source_file = Path(str(source_path)).expanduser()
            if not source_file.exists():
                blocked.append(f"Attachment source file not found: {source_file}")
        elif link_mode == 2 and isinstance(path_value, str):
            linked_path = Path(path_value).expanduser()
            if not linked_path.is_absolute():
                blocked.append("Linked-file attachments require an absolute path or sourcePath")
            elif not linked_path.exists():
                warnings.append(f"Linked file path does not exist yet: {linked_path}")
        elif link_mode == 2:
            blocked.append("Linked-file attachments require an absolute path or sourcePath")
        elif not self._looks_like_url(path_value):
            blocked.append("Linked-url attachments require an absolute http(s) URL")
        return blocked, warnings

    def _looks_like_url(self, value: object) -> bool:
        if not isinstance(value, str) or not value:
            return False
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _resolve_attachment_lead_file(self, source_path: Path, filename: str | None) -> Path:
        if source_path.is_file():
            return source_path
        if filename:
            candidate = source_path / filename
            if candidate.exists() and candidate.is_file():
                return candidate
            raise ValueError(f"Attachment source directory does not contain lead file {filename!r}: {source_path}")
        html_files = sorted(
            path for path in source_path.rglob("*") if path.is_file() and path.suffix.lower() in {".html", ".htm"}
        )
        if html_files:
            return html_files[0]
        files = sorted(path for path in source_path.rglob("*") if path.is_file())
        if files:
            return files[0]
        raise ValueError(f"Attachment source directory has no files: {source_path}")

    def _copy_attachment_source(
        self,
        source_path: Path,
        dest_dir: Path,
        *,
        filename: str | None,
    ) -> tuple[Path, str]:
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        if source_path.is_dir():
            shutil.copytree(source_path, dest_dir)
            lead_source = self._resolve_attachment_lead_file(source_path, filename)
            lead_dest = dest_dir / lead_source.relative_to(source_path)
            relative_path = lead_dest.relative_to(dest_dir).as_posix()
            return lead_dest, relative_path

        dest_dir.mkdir(parents=True, exist_ok=True)
        target_name = Path(filename).name if filename else source_path.name
        lead_dest = dest_dir / target_name
        shutil.copy2(source_path, lead_dest)
        return lead_dest, lead_dest.name

    def _embedded_image_filename(self, attachment_payload: dict[str, object]) -> str:
        filename = attachment_payload.get("filename")
        if isinstance(filename, str) and filename.strip():
            return Path(filename).name
        content_type = str(attachment_payload.get("contentType") or "").strip().lower()
        extension = self.EMBEDDED_IMAGE_EXTENSIONS.get(content_type)
        if not extension:
            raise ValueError(f"Unsupported embedded image content type: {attachment_payload.get('contentType')!r}")
        return f"image.{extension}"

    def _apply_planned_operation(
        self,
        writer: LocalZoteroWriteDB,
        operation: dict[str, object],
        *,
        data_dir: str,
    ) -> None:
        if operation["entity_type"] == "collection":
            self._apply_collection_operation(writer, operation)
            return
        if operation["entity_type"] == "item":
            self._apply_item_operation(writer, operation, data_dir=data_dir)
            return
        raise ValueError(f"Unsupported local apply entity type: {operation['entity_type']}")

    def _apply_collection_operation(self, writer: LocalZoteroWriteDB, operation: dict[str, object]) -> None:
        library_id, _ = parse_library_id(str(operation["library_id"]))
        if library_id != "local":
            raise ValueError("Local apply only supports local:* libraries")
        _, local_library_key = parse_library_id(str(operation["library_id"]))
        entity = self.canonical.get_entity(str(operation["library_id"]), EntityType.COLLECTION, str(operation["entity_key"]))
        if not entity:
            raise ValueError(f"Unknown canonical collection: {operation['library_id']}/{operation['entity_key']}")
        local = writer.get_collection_by_key(str(operation["entity_key"]), include_deleted=True)
        details = dict(operation.get("details") or {})
        now = now_iso()
        columns = writer.table_columns("collections")

        if operation["action"] == "create-collection":
            parent_collection_id = details.get("parentCollectionID")
            parent_collection_key = details.get("parentCollectionKey")
            if parent_collection_id is None and isinstance(parent_collection_key, str) and parent_collection_key:
                parent = writer.get_collection_by_key(parent_collection_key)
                if not parent:
                    raise ValueError(f"Missing local parent collection: {parent_collection_key}")
                parent_collection_id = int(parent["collectionID"])
            collection_id = writer.next_id("collections", "collectionID")
            data = {
                "collectionID": collection_id,
                "collectionName": details.get("name") or entity["payload"].get("name") or entity["title"],
                "parentCollectionID": parent_collection_id,
                "libraryID": int(local_library_key),
                "key": str(operation["entity_key"]),
            }
            if "clientDateModified" in columns:
                data["clientDateModified"] = now
            if "version" in columns:
                data["version"] = int(entity["version"])
            if "synced" in columns:
                data["synced"] = 0
            self._insert_row(writer, "collections", data)
            self._clear_deleted_flag(writer, "deletedCollections", "collectionID", collection_id)
            return

        if not local:
            raise ValueError(f"Local collection not found: {operation['entity_key']}")
        collection_id = int(local["collectionID"])
        if operation["action"] == "update-collection":
            parent_collection_id = details.get("parentCollectionID")
            parent_collection_key = details.get("parentCollectionKey")
            if parent_collection_id is None and isinstance(parent_collection_key, str) and parent_collection_key:
                parent = writer.get_collection_by_key(parent_collection_key)
                if not parent:
                    raise ValueError(f"Missing local parent collection: {parent_collection_key}")
                parent_collection_id = int(parent["collectionID"])
            updates = {
                "collectionName": details.get("name") or entity["payload"].get("name") or entity["title"],
                "parentCollectionID": parent_collection_id,
            }
            if "clientDateModified" in columns:
                updates["clientDateModified"] = now
            if "version" in columns:
                updates["version"] = max(int(local.get("version") or 0) + 1, int(entity["version"]))
            if "synced" in columns:
                updates["synced"] = 0
            self._update_row(writer, "collections", "collectionID", collection_id, updates)
            self._clear_deleted_flag(writer, "deletedCollections", "collectionID", collection_id)
            return
        if operation["action"] == "trash-collection":
            updates = {}
            if "clientDateModified" in columns:
                updates["clientDateModified"] = now
            if "version" in columns:
                updates["version"] = int(local.get("version") or 0) + 1
            if "synced" in columns:
                updates["synced"] = 0
            if updates:
                self._update_row(writer, "collections", "collectionID", collection_id, updates)
            self._mark_deleted(writer, "deletedCollections", "collectionID", collection_id)
            return
        raise ValueError(f"Unsupported collection action: {operation['action']}")

    def _apply_item_operation(
        self,
        writer: LocalZoteroWriteDB,
        operation: dict[str, object],
        *,
        data_dir: str,
    ) -> None:
        library_type, local_library_key = parse_library_id(str(operation["library_id"]))
        if library_type != "local":
            raise ValueError("Local apply only supports local:* libraries")
        entity = self.canonical.get_entity(str(operation["library_id"]), EntityType.ITEM, str(operation["entity_key"]))
        if not entity:
            raise ValueError(f"Unknown canonical item: {operation['library_id']}/{operation['entity_key']}")
        local = writer.get_item_row(str(operation["entity_key"]), include_deleted=True)
        details = dict(operation.get("details") or {})
        now = now_iso()
        columns = writer.table_columns("items")

        if operation["action"] == "create-item":
            item_id = writer.next_id("items", "itemID")
            item_type_id = writer.get_item_type_id(str(details["itemType"]))
            if item_type_id is None:
                raise ValueError(f"Unknown item type: {details['itemType']}")
            data = {
                "itemID": item_id,
                "itemTypeID": item_type_id,
                "libraryID": int(local_library_key),
                "key": str(operation["entity_key"]),
            }
            if "dateAdded" in columns:
                data["dateAdded"] = now
            if "dateModified" in columns:
                data["dateModified"] = now
            if "clientDateModified" in columns:
                data["clientDateModified"] = now
            if "version" in columns:
                data["version"] = int(entity["version"])
            if "synced" in columns:
                data["synced"] = 0
            self._insert_row(writer, "items", data)
            self._apply_item_fields(writer, item_id, list(details.get("fields") or []))
            if "note" in details:
                self._sync_item_note(writer, item_id, dict(details["note"]))
            if "annotation" in details:
                self._sync_item_annotation(writer, item_id, dict(details["annotation"]))
            if "attachment" in details:
                self._sync_item_attachment(
                    writer,
                    item_id,
                    dict(details["attachment"]),
                    attachment_key=str(operation["entity_key"]),
                    data_dir=data_dir,
                )
            if details.get("creators"):
                self._sync_item_creators(writer, item_id, list(details["creators"]))
            if details.get("tags"):
                self._sync_item_tags(writer, item_id, list(details["tags"]))
            if details.get("collections"):
                self._sync_item_collections(writer, item_id, list(details["collections"]))
            self._clear_deleted_flag(writer, "deletedItems", "itemID", item_id)
            return

        if not local:
            raise ValueError(f"Local item not found: {operation['entity_key']}")
        item_id = int(local["itemID"])
        if operation["action"] == "update-item":
            updates = {}
            if "itemTypeID" in columns and details.get("itemType"):
                item_type_id = writer.get_item_type_id(str(details["itemType"]))
                if item_type_id is None:
                    raise ValueError(f"Unknown item type: {details['itemType']}")
                updates["itemTypeID"] = item_type_id
            if "dateModified" in columns:
                updates["dateModified"] = now
            if "clientDateModified" in columns:
                updates["clientDateModified"] = now
            if "version" in columns:
                updates["version"] = max(int(local.get("version") or 0) + 1, int(entity["version"]))
            if "synced" in columns:
                updates["synced"] = 0
            if updates:
                self._update_row(writer, "items", "itemID", item_id, updates)
            self._apply_item_fields(writer, item_id, list(details.get("fields") or []))
            if "note" in details:
                self._sync_item_note(writer, item_id, dict(details.get("note") or {}))
            if "annotation" in details:
                self._sync_item_annotation(writer, item_id, dict(details.get("annotation") or {}))
            if "attachment" in details:
                self._sync_item_attachment(
                    writer,
                    item_id,
                    dict(details.get("attachment") or {}),
                    attachment_key=str(operation["entity_key"]),
                    data_dir=data_dir,
                )
            if "creators" in details:
                self._sync_item_creators(writer, item_id, list(details.get("creators") or []))
            if "tags" in details:
                self._sync_item_tags(writer, item_id, list(details.get("tags") or []))
            if "collections" in details:
                self._sync_item_collections(writer, item_id, list(details.get("collections") or []))
            self._clear_deleted_flag(writer, "deletedItems", "itemID", item_id)
            return
        if operation["action"] == "trash-item":
            updates = {}
            if "dateModified" in columns:
                updates["dateModified"] = now
            if "clientDateModified" in columns:
                updates["clientDateModified"] = now
            if "version" in columns:
                updates["version"] = int(local.get("version") or 0) + 1
            if "synced" in columns:
                updates["synced"] = 0
            if updates:
                self._update_row(writer, "items", "itemID", item_id, updates)
            self._mark_deleted(writer, "deletedItems", "itemID", item_id)
            return
        raise ValueError(f"Unsupported item action: {operation['action']}")

    def _insert_row(self, writer: LocalZoteroWriteDB, table: str, data: dict[str, object]) -> None:
        columns = list(data.keys())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        with writer._connect() as conn:
            conn.execute(sql, tuple(data[column] for column in columns))

    def _update_row(
        self,
        writer: LocalZoteroWriteDB,
        table: str,
        id_column: str,
        id_value: int,
        updates: dict[str, object],
    ) -> None:
        if not updates:
            return
        columns = list(updates.keys())
        sql = f"UPDATE {table} SET {', '.join(f'{column}=?' for column in columns)} WHERE {id_column}=?"
        with writer._connect() as conn:
            conn.execute(sql, tuple(updates[column] for column in columns) + (id_value,))

    def _mark_deleted(self, writer: LocalZoteroWriteDB, table: str, id_column: str, id_value: int) -> None:
        if not writer.has_table(table):
            return
        with writer._connect() as conn:
            conn.execute(f"INSERT OR IGNORE INTO {table} ({id_column}) VALUES (?)", (id_value,))

    def _clear_deleted_flag(self, writer: LocalZoteroWriteDB, table: str, id_column: str, id_value: int) -> None:
        if not writer.has_table(table):
            return
        with writer._connect() as conn:
            conn.execute(f"DELETE FROM {table} WHERE {id_column} = ?", (id_value,))

    def _apply_item_fields(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        field_ops: list[dict[str, object]],
    ) -> None:
        if not field_ops:
            return
        with writer._connect() as conn:
            for field_op in field_ops:
                field_name = str(field_op["field"])
                field_id = writer.get_field_id(field_name)
                if field_id is None:
                    raise ValueError(f"Unknown field: {field_name}")
                value = "" if field_op["value"] is None else str(field_op["value"])
                if value == "":
                    conn.execute("DELETE FROM itemData WHERE itemID = ? AND fieldID = ?", (item_id, field_id))
                    continue
                row = conn.execute("SELECT valueID FROM itemDataValues WHERE value = ? LIMIT 1", (value,)).fetchone()
                if row:
                    value_id = int(row["valueID"])
                else:
                    value_id = self._next_id_in_tx(conn, "itemDataValues", "valueID")
                    conn.execute("INSERT INTO itemDataValues (valueID, value) VALUES (?, ?)", (value_id, value))
                conn.execute("DELETE FROM itemData WHERE itemID = ? AND fieldID = ?", (item_id, field_id))
                conn.execute(
                    "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
                    (item_id, field_id, value_id),
                )

    def _next_id_in_tx(self, conn, table: str, id_column: str) -> int:
        row = conn.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 AS nextID FROM {table}").fetchone()
        return int(row["nextID"] if row else 1)

    def _sync_item_collections(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        desired_collection_keys: list[str],
    ) -> None:
        desired_ids: list[int] = []
        for key in desired_collection_keys:
            collection = writer.get_collection_by_key(str(key))
            if not collection:
                raise ValueError(f"Missing local collection: {key}")
            desired_ids.append(int(collection["collectionID"]))

        with writer._connect() as conn:
            columns = writer.table_columns("collectionItems")
            rows = conn.execute(
                "SELECT collectionID FROM collectionItems WHERE itemID = ?",
                (item_id,),
            ).fetchall()
            existing_ids = {int(row["collectionID"]) for row in rows}
            target_ids = set(desired_ids)

            to_remove = existing_ids - target_ids
            if to_remove:
                placeholders = ", ".join(["?"] * len(to_remove))
                conn.execute(
                    f"DELETE FROM collectionItems WHERE itemID = ? AND collectionID IN ({placeholders})",
                    (item_id, *sorted(to_remove)),
                )

            for collection_id in desired_ids:
                if collection_id in existing_ids:
                    continue
                if "orderIndex" in columns:
                    order_index_row = conn.execute(
                        "SELECT COALESCE(MAX(orderIndex) + 1, 0) AS nextOrder FROM collectionItems WHERE collectionID = ?",
                        (collection_id,),
                    ).fetchone()
                    order_index = int(order_index_row["nextOrder"] if order_index_row else 0)
                    conn.execute(
                        "INSERT OR IGNORE INTO collectionItems (collectionID, itemID, orderIndex) VALUES (?, ?, ?)",
                        (collection_id, item_id, order_index),
                    )
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO collectionItems (collectionID, itemID) VALUES (?, ?)",
                        (collection_id, item_id),
                    )

    def _sync_item_tags(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        desired_tags: list[dict[str, object]],
    ) -> None:
        with writer._connect() as conn:
            conn.execute("DELETE FROM itemTags WHERE itemID = ?", (item_id,))
            for tag in desired_tags:
                name = str(tag["name"])
                tag_type = int(tag.get("type", 0))
                row = conn.execute("SELECT tagID FROM tags WHERE name = ? LIMIT 1", (name,)).fetchone()
                if row:
                    tag_id = int(row["tagID"])
                else:
                    tag_id = self._next_id_in_tx(conn, "tags", "tagID")
                    conn.execute("INSERT INTO tags (tagID, name) VALUES (?, ?)", (tag_id, name))
                conn.execute(
                    "INSERT INTO itemTags (itemID, tagID, type) VALUES (?, ?, ?)",
                    (item_id, tag_id, tag_type),
                )

    def _sync_item_note(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        note_payload: dict[str, object],
    ) -> None:
        note = str(note_payload.get("note") or "")
        title = str(note_payload.get("title") or "")
        parent_item_key = note_payload.get("parentItemKey")
        parent_item_id = None
        if parent_item_key:
            parent = writer.get_item_row(str(parent_item_key))
            if not parent:
                raise ValueError(f"Missing local parent item: {parent_item_key}")
            parent_item_id = int(parent["itemID"])
        with writer._connect() as conn:
            if note == "" and title == "":
                conn.execute("DELETE FROM itemNotes WHERE itemID = ?", (item_id,))
                return
            row = conn.execute("SELECT itemID FROM itemNotes WHERE itemID = ? LIMIT 1", (item_id,)).fetchone()
            columns = writer.table_columns("itemNotes")
            if row:
                if "parentItemID" in columns:
                    conn.execute(
                        "UPDATE itemNotes SET parentItemID = ?, note = ?, title = ? WHERE itemID = ?",
                        (parent_item_id, note, title, item_id),
                    )
                else:
                    conn.execute(
                        "UPDATE itemNotes SET note = ?, title = ? WHERE itemID = ?",
                        (note, title, item_id),
                    )
            else:
                if "parentItemID" in columns:
                    conn.execute(
                        "INSERT INTO itemNotes (itemID, parentItemID, note, title) VALUES (?, ?, ?, ?)",
                        (item_id, parent_item_id, note, title),
                    )
                else:
                    conn.execute(
                        "INSERT INTO itemNotes (itemID, note, title) VALUES (?, ?, ?)",
                        (item_id, note, title),
                    )

    def _sync_item_annotation(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        annotation_payload: dict[str, object],
    ) -> None:
        parent_item_key = annotation_payload.get("parentItemKey")
        if not parent_item_key:
            raise ValueError("Annotation writeback requires parentItemKey")
        parent = writer.get_item_row(str(parent_item_key))
        if not parent:
            raise ValueError(f"Missing local parent item: {parent_item_key}")
        if parent.get("itemType") != "attachment":
            raise ValueError(f"Annotation parent must be an attachment item: {parent_item_key}")
        if writer.has_table("itemAttachments"):
            parent_attachment = writer.query(
                "SELECT itemID FROM itemAttachments WHERE itemID = ? LIMIT 1",
                (int(parent["itemID"]),),
            )
            if not parent_attachment:
                raise ValueError(f"Annotation parent attachment metadata is missing locally: {parent_item_key}")
        annotation_type = normalize_annotation_type(
            annotation_payload.get("annotationType") or annotation_payload.get("annotationTypeID")
        )
        if annotation_type is None:
            raise ValueError(f"Invalid annotation type: {annotation_payload.get('annotationType')!r}")
        columns = writer.table_columns("itemAnnotations")
        values: dict[str, object] = {
            "itemID": item_id,
        }
        column_map = {
            "parentItemID": int(parent["itemID"]),
            "type": annotation_type[1],
            "authorName": annotation_payload.get("annotationAuthorName"),
            "text": annotation_payload.get("annotationText"),
            "comment": annotation_payload.get("annotationComment"),
            "color": annotation_payload.get("annotationColor"),
            "pageLabel": annotation_payload.get("annotationPageLabel"),
            "sortIndex": annotation_payload.get("annotationSortIndex"),
            "position": annotation_payload.get("annotationPosition"),
            "isExternal": int(bool(annotation_payload.get("annotationIsExternal"))),
        }
        for column, value in column_map.items():
            if column in columns:
                values[column] = value
        with writer._connect() as conn:
            row = conn.execute("SELECT itemID FROM itemAnnotations WHERE itemID = ? LIMIT 1", (item_id,)).fetchone()
            if row:
                assignments = ", ".join(f"{column} = ?" for column in values if column != "itemID")
                conn.execute(
                    f"UPDATE itemAnnotations SET {assignments} WHERE itemID = ?",
                    tuple(values[column] for column in values if column != "itemID") + (item_id,),
                )
            else:
                insert_columns = list(values.keys())
                placeholders = ", ".join(["?"] * len(insert_columns))
                conn.execute(
                    f"INSERT INTO itemAnnotations ({', '.join(insert_columns)}) VALUES ({placeholders})",
                    tuple(values[column] for column in insert_columns),
                )

    def _sync_item_attachment(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        attachment_payload: dict[str, object],
        *,
        attachment_key: str,
        data_dir: str,
    ) -> None:
        parent_item_key = attachment_payload.get("parentItemKey")
        parent_item_id = None
        if parent_item_key:
            parent = writer.get_item_row(str(parent_item_key))
            if not parent:
                raise ValueError(f"Missing local parent item: {parent_item_key}")
            parent_item_id = int(parent["itemID"])

        link_mode = attachment_payload.get("linkMode")
        path_value = attachment_payload.get("path")
        source_path = attachment_payload.get("sourcePath")
        filename = attachment_payload.get("filename")
        storage_mod_time = None
        storage_hash = None

        if link_mode == 0 and source_path:
            source_file = Path(str(source_path)).expanduser()
            if not source_file.exists():
                raise ValueError(f"Attachment source file not found: {source_file}")
            if not filename:
                filename = source_file.name
            dest_dir = self._storage_root(data_dir) / attachment_key
            dest_file, relative_path = self._copy_attachment_source(source_file, dest_dir, filename=str(filename))
            path_value = f"storage:{relative_path}"
            stat = dest_file.stat()
            storage_mod_time = int(stat.st_mtime * 1000)
            storage_hash = self._file_md5(dest_file)
        elif link_mode == 0 and isinstance(path_value, str) and path_value.startswith("storage:"):
            dest_file = self._storage_root(data_dir) / attachment_key / path_value.removeprefix("storage:")
            if dest_file.exists():
                stat = dest_file.stat()
                storage_mod_time = int(stat.st_mtime * 1000)
                storage_hash = self._file_md5(dest_file)
        elif link_mode == 1 and source_path:
            source_file = Path(str(source_path)).expanduser()
            if not source_file.exists():
                raise ValueError(f"Attachment source file not found: {source_file}")
            dest_dir = self._storage_root(data_dir) / attachment_key
            dest_file, relative_path = self._copy_attachment_source(
                source_file,
                dest_dir,
                filename=str(filename) if filename else None,
            )
            path_value = f"storage:{relative_path}"
            stat = dest_file.stat()
            storage_mod_time = int(stat.st_mtime * 1000)
            storage_hash = self._file_md5(dest_file)
        elif link_mode == 1 and isinstance(path_value, str) and path_value.startswith("storage:"):
            dest_file = self._storage_root(data_dir) / attachment_key / path_value.removeprefix("storage:")
            if dest_file.exists():
                stat = dest_file.stat()
                storage_mod_time = int(stat.st_mtime * 1000)
                storage_hash = self._file_md5(dest_file)
        elif link_mode == 4 and source_path:
            source_file = Path(str(source_path)).expanduser()
            if not source_file.exists():
                raise ValueError(f"Embedded image source file not found: {source_file}")
            if source_file.is_dir():
                raise ValueError("Embedded-image attachments require a single source file, not a directory")
            embedded_filename = self._embedded_image_filename(attachment_payload)
            dest_dir = self._storage_root(data_dir) / attachment_key
            dest_file, relative_path = self._copy_attachment_source(source_file, dest_dir, filename=embedded_filename)
            path_value = f"storage:{relative_path}"
            stat = dest_file.stat()
            storage_mod_time = int(stat.st_mtime * 1000)
            storage_hash = self._file_md5(dest_file)
        elif link_mode == 4 and isinstance(path_value, str) and path_value.startswith("storage:"):
            dest_file = self._storage_root(data_dir) / attachment_key / path_value.removeprefix("storage:")
            if dest_file.exists():
                stat = dest_file.stat()
                storage_mod_time = int(stat.st_mtime * 1000)
                storage_hash = self._file_md5(dest_file)
        elif link_mode == 2 and source_path and not path_value:
            linked_path = Path(str(source_path)).expanduser()
            if not linked_path.exists():
                raise ValueError(f"Attachment source file not found: {linked_path}")
            path_value = str(linked_path.resolve())
        elif link_mode == 2 and path_value:
            linked_path = Path(str(path_value)).expanduser()
            if not linked_path.is_absolute():
                raise ValueError("Linked-file attachments require an absolute path")
            path_value = str(linked_path.resolve())
        elif link_mode == 3 and not self._looks_like_url(path_value):
            raise ValueError("Linked-url attachments require an absolute http(s) URL")

        with writer._connect() as conn:
            row = conn.execute("SELECT itemID FROM itemAttachments WHERE itemID = ? LIMIT 1", (item_id,)).fetchone()
            columns = writer.table_columns("itemAttachments")
            values: dict[str, object] = {}
            if "parentItemID" in columns:
                values["parentItemID"] = parent_item_id
            if "contentType" in columns:
                values["contentType"] = attachment_payload.get("contentType")
            if "path" in columns:
                values["path"] = path_value
            if "linkMode" in columns:
                values["linkMode"] = link_mode
            if "storageModTime" in columns:
                values["storageModTime"] = storage_mod_time
            if "storageHash" in columns:
                values["storageHash"] = storage_hash
            if "syncState" in columns and link_mode in {0, 1, 4}:
                values["syncState"] = 0
            if row:
                assignments = ", ".join(f"{column} = ?" for column in values)
                conn.execute(
                    f"UPDATE itemAttachments SET {assignments} WHERE itemID = ?",
                    tuple(values[column] for column in values) + (item_id,),
                )
            else:
                payload = {"itemID": item_id, **values}
                columns_sql = ", ".join(payload.keys())
                placeholders = ", ".join(["?"] * len(payload))
                conn.execute(
                    f"INSERT INTO itemAttachments ({columns_sql}) VALUES ({placeholders})",
                    tuple(payload.values()),
                )

    def _file_md5(self, path: Path) -> str:
        digest = hashlib.md5()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _sync_item_creators(
        self,
        writer: LocalZoteroWriteDB,
        item_id: int,
        desired_creators: list[dict[str, object]],
    ) -> None:
        with writer._connect() as conn:
            conn.execute("DELETE FROM itemCreators WHERE itemID = ?", (item_id,))
            for order_index, creator in enumerate(desired_creators):
                creator_type = str(creator["creatorType"])
                creator_type_id = writer.get_creator_type_id(creator_type)
                if creator_type_id is None:
                    raise ValueError(f"Unknown creator type: {creator_type}")
                first_name = str(creator.get("firstName") or "")
                last_name = str(creator.get("lastName") or "")
                name = str(creator.get("name") or "")
                if name:
                    row = conn.execute(
                        """
                        SELECT creatorDataID
                        FROM creatorData
                        WHERE COALESCE(name, '') = ?
                          AND COALESCE(firstName, '') = ''
                          AND COALESCE(lastName, '') = ''
                        LIMIT 1
                        """,
                        (name,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT creatorDataID
                        FROM creatorData
                        WHERE COALESCE(firstName, '') = ?
                          AND COALESCE(lastName, '') = ?
                          AND COALESCE(name, '') = ''
                        LIMIT 1
                        """,
                        (first_name, last_name),
                    ).fetchone()
                if row:
                    creator_data_id = int(row["creatorDataID"])
                else:
                    creator_data_id = self._next_id_in_tx(conn, "creatorData", "creatorDataID")
                    conn.execute(
                        "INSERT INTO creatorData (creatorDataID, firstName, lastName, name) VALUES (?, ?, ?, ?)",
                        (creator_data_id, first_name or None, last_name or None, name or None),
                    )

                creator_row = conn.execute(
                    "SELECT creatorID FROM creators WHERE creatorDataID = ? LIMIT 1",
                    (creator_data_id,),
                ).fetchone()
                if creator_row:
                    creator_id = int(creator_row["creatorID"])
                else:
                    creator_id = self._next_id_in_tx(conn, "creators", "creatorID")
                    conn.execute(
                        "INSERT INTO creators (creatorID, creatorDataID) VALUES (?, ?)",
                        (creator_id, creator_data_id),
                    )

                conn.execute(
                    """
                    INSERT INTO itemCreators (itemID, creatorID, creatorTypeID, orderIndex)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item_id, creator_id, creator_type_id, order_index),
                )
