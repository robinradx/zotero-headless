from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings
from .local_db import LocalZoteroDB
from .qmd import QmdAutoIndexer
from .store import MirrorStore
from .utils import format_library_id, parse_library_id
from .web_api import ZoteroWebClient


REMOTE_KIND_MAP = {
    "collection": "collections",
    "search": "searches",
    "item": "items",
}


@dataclass(slots=True)
class SyncResult:
    library_id: str
    updated: int = 0
    deleted: int = 0
    version: int = 0


class SyncService:
    def __init__(self, settings: Settings, store: MirrorStore, *, qmd_indexer: QmdAutoIndexer | None = None):
        self.settings = settings
        self.store = store
        self.qmd_indexer = qmd_indexer

    def _refresh_qmd_mirror(self, library_id: str) -> None:
        if not self.qmd_indexer:
            return
        try:
            self.qmd_indexer.refresh_mirror_library(self.store, library_id)
        except Exception:
            pass

    def discover_remote_libraries(self) -> list[dict[str, Any]]:
        client = ZoteroWebClient(self.settings)
        key_info = client.get_current_key()
        user_id = int(key_info["userID"])
        self.settings.user_id = user_id

        discovered: list[dict[str, Any]] = []
        user_access = (key_info.get("access") or {}).get("user") or {}
        if user_access.get("library"):
            library_id = format_library_id("user", user_id)
            self.store.upsert_library(
                library_id=library_id,
                library_type="user",
                remote_id=str(user_id),
                name=key_info.get("username") or f"user:{user_id}",
                source="remote",
                editable=bool(user_access.get("write")),
                files_editable=bool(user_access.get("files")),
            )
            discovered.append(self.store.get_library(library_id) or {})

        groups, _ = client.get_group_versions(user_id)
        group_access = ((key_info.get("access") or {}).get("groups") or {}).get("all") or {}
        for group_id, meta_version in groups.items():
            payload, _ = client.get_group(group_id)
            library_id = format_library_id("group", group_id)
            self.store.upsert_library(
                library_id=library_id,
                library_type="group",
                remote_id=str(group_id),
                name=payload.get("data", {}).get("name") or payload.get("name") or f"group:{group_id}",
                source="remote",
                meta_version=meta_version,
                editable=bool(group_access.get("write")),
                files_editable=bool(group_access.get("library")),
            )
            discovered.append(self.store.get_library(library_id) or {})
        return discovered

    def sync_remote_library(self, library_id: str, *, full: bool = True) -> SyncResult:
        library = self.store.get_library(library_id)
        if not library:
            library_type, remote_id = parse_library_id(library_id)
            self.store.upsert_library(
                library_id=library_id,
                library_type=library_type,
                remote_id=remote_id,
                name=library_id,
                source="remote",
            )
        client = ZoteroWebClient(self.settings)
        result = SyncResult(library_id=library_id)
        max_version = 0

        for singular_kind, remote_kind in REMOTE_KIND_MAP.items():
            since = 0 if full else int((library or {}).get("version") or 0)
            versions, last_modified = client.get_versions(library_id, remote_kind, since=since)
            max_version = max(max_version, last_modified)
            remote_keys = set(versions.keys())
            local_objects = self.store.list_objects(library_id, singular_kind, limit=100000, include_deleted=True)
            local_versions = {obj["object_key"]: obj["version"] for obj in local_objects}
            changed_keys = [key for key, version in versions.items() if local_versions.get(key) != version]

            for start in range(0, len(changed_keys), 50):
                batch = changed_keys[start : start + 50]
                for payload in client.get_objects_by_keys(library_id, remote_kind, batch):
                    self.store.upsert_object(
                        library_id,
                        singular_kind,
                        payload,
                        version=payload.get("version") or payload.get("data", {}).get("version"),
                        synced=True,
                        deleted=False,
                    )
                    result.updated += 1
            if full:
                result.deleted += self.store.mark_missing_deleted(library_id, singular_kind, remote_keys)

        if max_version:
            self.store.set_library_version(library_id, max_version)
            result.version = max_version
        self._refresh_qmd_mirror(library_id)
        return result

    def import_local_snapshot(self) -> dict[str, Any]:
        sqlite_path = self.settings.resolved_local_db()
        if not sqlite_path:
            raise ValueError("A local Zotero data_dir must be configured")
        local_db = LocalZoteroDB(sqlite_path)
        libraries = local_db.list_libraries()
        collections = local_db.list_collections(limit=100000)
        items = local_db.list_items(limit=100000)

        imported = {"libraries": 0, "collections": 0, "items": 0}
        for lib in libraries:
            remote_id = str(lib["libraryID"])
            library_type = lib.get("libraryType", "local")
            library_id = format_library_id("local", remote_id)
            name = lib.get("name") or f"{library_type}:{remote_id}"
            self.store.upsert_library(
                library_id=library_id,
                library_type="local",
                remote_id=remote_id,
                name=name,
                source="local",
                version=int(lib.get("version") or 0),
            )
            imported["libraries"] += 1

        for collection in collections:
            library_id = format_library_id("local", str(collection["libraryID"]))
            payload = {
                "key": collection["key"],
                "version": collection.get("version") or 0,
                "data": {
                    "key": collection["key"],
                    "version": collection.get("version") or 0,
                    "name": collection.get("collectionName"),
                    "parentCollection": collection.get("parentCollectionID"),
                },
            }
            self.store.upsert_object(library_id, "collection", payload, synced=True, deleted=False)
            imported["collections"] += 1

        for item in items:
            library_id = format_library_id("local", str(item["libraryID"]))
            detail = local_db.get_item_detail(item["key"]) or {}
            payload = {
                "key": item["key"],
                "version": item.get("version") or 0,
                "data": {
                    "key": item["key"],
                    "version": item.get("version") or 0,
                    "itemType": item.get("itemType"),
                    "title": item.get("title"),
                    "dateAdded": item.get("dateAdded"),
                    "dateModified": item.get("dateModified"),
                    "fields": detail.get("fields", {}),
                    "creators": detail.get("creators", []),
                    "tags": detail.get("tags", []),
                    "collections": [c["key"] for c in detail.get("collections", [])],
                    "notes": detail.get("notes", []),
                    "attachments": detail.get("attachments", []),
                },
            }
            self.store.upsert_object(library_id, "item", payload, synced=bool(item.get("synced", 1)), deleted=False)
            imported["items"] += 1
        return imported
