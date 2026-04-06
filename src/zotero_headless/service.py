from __future__ import annotations

from typing import Any

from .config import Settings
from .core import CanonicalStore, ChangeType, EntityType
from .library_routing import prefers_canonical_writes
from .store import MirrorStore
from .sync import SyncService
from .utils import (
    annotation_display_title,
    detect_citation_aliases,
    detect_citation_key,
    parse_library_id,
    set_pinned_citation_aliases_in_extra,
    set_pinned_citation_key_in_extra,
)
from .web_api import ZoteroWebClient


class LocalWriteRequiresDaemonError(RuntimeError):
    pass


class HeadlessService:
    def __init__(self, settings: Settings, store: MirrorStore, canonical: CanonicalStore):
        self.settings = settings
        self.store = store
        self.canonical = canonical
        self.sync = SyncService(settings, store)

    def _normalize_item_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if normalized.get("itemType") == "annotation" and not normalized.get("title"):
            derived_title = annotation_display_title(normalized)
            if derived_title:
                normalized["title"] = derived_title
        fields = dict(normalized.get("fields") or {})
        for field_name in (
            "title",
            "abstractNote",
            "url",
            "date",
            "publicationTitle",
            "websiteTitle",
            "extra",
            "accessDate",
            "shortTitle",
        ):
            if normalized.get(field_name) is not None:
                fields[field_name] = normalized[field_name]
        citation_key = detect_citation_key(normalized, fields)
        citation_aliases = detect_citation_aliases(normalized, fields)
        if citation_key:
            normalized["citationKey"] = citation_key
            fields["citationKey"] = citation_key
            extra = normalized.get("extra")
            if extra is None:
                extra = fields.get("extra")
            normalized["extra"] = set_pinned_citation_key_in_extra(str(extra or ""), citation_key)
            fields["extra"] = normalized["extra"]
        if citation_aliases:
            normalized["citationAliases"] = citation_aliases
            extra = normalized.get("extra")
            if extra is None:
                extra = fields.get("extra")
            normalized["extra"] = set_pinned_citation_aliases_in_extra(str(extra or ""), citation_aliases)
            fields["extra"] = normalized["extra"]
        if fields:
            normalized["fields"] = fields
        return normalized

    def _require_local_library_staged(self, library_id: str) -> None:
        if not self.canonical.get_library(library_id):
            raise LocalWriteRequiresDaemonError(
                "Local library is not staged in the headless store yet. "
                "Run `zotero-headless local import` first so local:* writes can be staged and later applied."
            )

    def _normalize_collection_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if normalized.get("name") is None and normalized.get("title") is not None:
            normalized["name"] = normalized["title"]
        if normalized.get("title") is None and normalized.get("name") is not None:
            normalized["title"] = normalized["name"]

        parent_collection = normalized.get("parentCollection")
        parent_collection_key = normalized.get("parentCollectionKey")
        if parent_collection is None and parent_collection_key:
            normalized["parentCollection"] = parent_collection_key
        if parent_collection_key is None and isinstance(parent_collection, str) and parent_collection:
            normalized["parentCollectionKey"] = parent_collection
        return normalized

    def create_item(self, library_id: str, item_data: dict[str, Any]) -> dict[str, Any]:
        library_type, _ = parse_library_id(library_id)
        if prefers_canonical_writes(self.canonical, library_id):
            payload = self._normalize_item_payload(item_data)
            return self.canonical.save_entity(
                library_id,
                EntityType.ITEM,
                payload,
                synced=False,
                change_type=ChangeType.CREATE,
            )
        if library_type == "local":
            self._require_local_library_staged(library_id)
            payload = self._normalize_item_payload(item_data)
            return self.canonical.save_entity(
                library_id,
                EntityType.ITEM,
                payload,
                synced=False,
                change_type=ChangeType.CREATE,
            )
        library = self.store.get_library(library_id) or {}
        client = ZoteroWebClient(self.settings)
        result = client.create_item(library_id, item_data, library_version=library.get("version"))
        self.sync.sync_remote_library(library_id)
        return result

    def update_item(self, library_id: str, item_key: str, item_data: dict[str, Any], *, replace: bool = False) -> dict[str, Any]:
        library_type, _ = parse_library_id(library_id)
        if prefers_canonical_writes(self.canonical, library_id):
            current = self.canonical.get_entity(library_id, EntityType.ITEM, item_key)
            if not current:
                raise KeyError(f"Item not found: {library_id}/{item_key}")
            base = {} if replace else dict(current["payload"])
            base.update(item_data)
            payload = self._normalize_item_payload(base)
            return self.canonical.save_entity(
                library_id,
                EntityType.ITEM,
                payload,
                entity_key=item_key,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=current["version"],
            )
        if library_type == "local":
            self._require_local_library_staged(library_id)
            current = self.canonical.get_entity(library_id, EntityType.ITEM, item_key)
            if not current:
                raise KeyError(f"Item not found: {library_id}/{item_key}")
            base = {} if replace else dict(current["payload"])
            base.update(item_data)
            payload = self._normalize_item_payload(base)
            return self.canonical.save_entity(
                library_id,
                EntityType.ITEM,
                payload,
                entity_key=item_key,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=current["version"],
            )
        current = self.store.get_object(library_id, "item", item_key)
        if not current:
            raise KeyError(f"Item not found: {library_id}/{item_key}")
        client = ZoteroWebClient(self.settings)
        version = client.update_item(
            library_id,
            item_key,
            item_data,
            item_version=current["version"],
            full=replace,
        )
        self.sync.sync_remote_library(library_id)
        refreshed = self.store.get_object(library_id, "item", item_key) or {}
        return {"version": version, "item": refreshed}

    def delete_item(self, library_id: str, item_key: str) -> dict[str, Any]:
        library_type, _ = parse_library_id(library_id)
        if prefers_canonical_writes(self.canonical, library_id):
            item = self.canonical.delete_entity(library_id, EntityType.ITEM, item_key)
            return {"deleted": True, "item": item}
        if library_type == "local":
            self._require_local_library_staged(library_id)
            item = self.canonical.delete_entity(library_id, EntityType.ITEM, item_key)
            return {"deleted": True, "item": item}
        current = self.store.get_object(library_id, "item", item_key)
        if not current:
            raise KeyError(f"Item not found: {library_id}/{item_key}")
        client = ZoteroWebClient(self.settings)
        version = client.delete_item(library_id, item_key, item_version=current["version"])
        self.sync.sync_remote_library(library_id)
        return {"version": version, "deleted": True}

    def create_collection(self, library_id: str, collection_data: dict[str, Any]) -> dict[str, Any]:
        library_type, _ = parse_library_id(library_id)
        payload = self._normalize_collection_payload(collection_data)
        if prefers_canonical_writes(self.canonical, library_id):
            return self.canonical.save_entity(
                library_id,
                EntityType.COLLECTION,
                payload,
                synced=False,
                change_type=ChangeType.CREATE,
            )
        if library_type == "local":
            self._require_local_library_staged(library_id)
            return self.canonical.save_entity(
                library_id,
                EntityType.COLLECTION,
                payload,
                synced=False,
                change_type=ChangeType.CREATE,
            )
        library = self.store.get_library(library_id) or {}
        client = ZoteroWebClient(self.settings)
        result = client.create_collection(library_id, payload, library_version=library.get("version"))
        self.sync.sync_remote_library(library_id)
        return result

    def update_collection(
        self,
        library_id: str,
        collection_key: str,
        collection_data: dict[str, Any],
        *,
        replace: bool = False,
    ) -> dict[str, Any]:
        library_type, _ = parse_library_id(library_id)
        if prefers_canonical_writes(self.canonical, library_id):
            current = self.canonical.get_entity(library_id, EntityType.COLLECTION, collection_key)
            if not current:
                raise KeyError(f"Collection not found: {library_id}/{collection_key}")
            base = {} if replace else dict(current["payload"])
            base.update(collection_data)
            payload = self._normalize_collection_payload(base)
            return self.canonical.save_entity(
                library_id,
                EntityType.COLLECTION,
                payload,
                entity_key=collection_key,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=current["version"],
            )
        if library_type == "local":
            self._require_local_library_staged(library_id)
            current = self.canonical.get_entity(library_id, EntityType.COLLECTION, collection_key)
            if not current:
                raise KeyError(f"Collection not found: {library_id}/{collection_key}")
            base = {} if replace else dict(current["payload"])
            base.update(collection_data)
            payload = self._normalize_collection_payload(base)
            return self.canonical.save_entity(
                library_id,
                EntityType.COLLECTION,
                payload,
                entity_key=collection_key,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=current["version"],
            )
        current = self.store.get_object(library_id, "collection", collection_key)
        if not current:
            raise KeyError(f"Collection not found: {library_id}/{collection_key}")
        base = {} if replace else dict(current["payload"])
        base.update(collection_data)
        payload = self._normalize_collection_payload(base)
        client = ZoteroWebClient(self.settings)
        version = client.update_collection(
            library_id,
            collection_key,
            payload,
            collection_version=current["version"],
        )
        self.sync.sync_remote_library(library_id)
        refreshed = self.store.get_object(library_id, "collection", collection_key) or {}
        return {"version": version, "collection": refreshed}

    def delete_collection(self, library_id: str, collection_key: str) -> dict[str, Any]:
        library_type, _ = parse_library_id(library_id)
        if prefers_canonical_writes(self.canonical, library_id):
            collection = self.canonical.delete_entity(library_id, EntityType.COLLECTION, collection_key)
            return {"deleted": True, "collection": collection}
        if library_type == "local":
            self._require_local_library_staged(library_id)
            collection = self.canonical.delete_entity(library_id, EntityType.COLLECTION, collection_key)
            return {"deleted": True, "collection": collection}
        current = self.store.get_object(library_id, "collection", collection_key)
        if not current:
            raise KeyError(f"Collection not found: {library_id}/{collection_key}")
        client = ZoteroWebClient(self.settings)
        version = client.delete_collection(library_id, collection_key, collection_version=current["version"])
        self.sync.sync_remote_library(library_id)
        return {"version": version, "deleted": True}
