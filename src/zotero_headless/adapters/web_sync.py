from __future__ import annotations

from dataclasses import dataclass
import io
import mimetypes
import hashlib
from pathlib import Path
import zipfile

from ..core import CanonicalStore, ChangeRecord, EntityType
from ..qmd import QmdAutoIndexer
from ..recovery import RecoveryService
from ..utils import annotation_display_title, detect_citation_aliases, detect_citation_key, format_library_id, now_iso
from ..web_api import ZoteroApiError, ZoteroWebClient


@dataclass(slots=True)
class WebSyncCapabilities:
    read_remote: bool = True
    write_remote: bool = True
    file_sync: bool = False
    attachment_upload_experimental: bool = True
    follows_zotero_protocol: bool = True


@dataclass(slots=True)
class WebLibraryCursor:
    library_id: str
    library_version: int = 0
    last_full_sync: str | None = None


class WebSyncAdapter:
    """
    Boundary for the official Zotero web sync protocol.

    This adapter is a first-class part of the target architecture rather than a
    later bridge. Synced users must work from day one.
    """

    capabilities = WebSyncCapabilities()

    def pull_library(
        self,
        library_id: str,
        cursor: WebLibraryCursor | None = None,
        *,
        record_recovery_snapshot: bool = True,
    ) -> dict[str, object]:
        raise NotImplementedError

    def push_changes(self, library_id: str, changes: list[ChangeRecord]) -> dict[str, object]:
        raise NotImplementedError


class CanonicalWebSyncAdapter(WebSyncAdapter):
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

    def __init__(self, store: CanonicalStore, client: ZoteroWebClient, *, qmd_indexer: QmdAutoIndexer | None = None):
        self.store = store
        self.client = client
        self.file_cache_dir = self.client.settings.resolved_file_cache_dir()
        self.qmd_indexer = qmd_indexer

    def _refresh_qmd(self, library_id: str) -> None:
        if not self.qmd_indexer:
            return
        try:
            self.qmd_indexer.refresh_canonical_library(self.store, library_id)
        except Exception:
            pass

    def discover_libraries(self) -> list[dict[str, object]]:
        key_info = self.client.get_current_key()
        user_id = int(key_info["userID"])
        discovered: list[dict[str, object]] = []
        user_access = (key_info.get("access") or {}).get("user") or {}
        if user_access.get("library"):
            library_id = format_library_id("user", user_id)
            existing = self.store.get_library(library_id) or {}
            discovered.append(
                self.store.upsert_library(
                    library_id,
                    name=key_info.get("username") or f"user:{user_id}",
                    source="remote-sync",
                    editable=bool(user_access.get("write")),
                    metadata=(existing.get("metadata") or {"library_version": 0, "last_full_sync": None}),
                )
            )

        groups, _ = self.client.get_group_versions(user_id)
        group_access = ((key_info.get("access") or {}).get("groups") or {}).get("all") or {}
        for group_id, _meta_version in groups.items():
            payload, _ = self.client.get_group(group_id)
            library_id = format_library_id("group", group_id)
            existing = self.store.get_library(library_id) or {}
            discovered.append(
                self.store.upsert_library(
                    library_id,
                    name=payload.get("data", {}).get("name") or payload.get("name") or f"group:{group_id}",
                    source="remote-sync",
                    editable=bool(group_access.get("write")),
                    metadata=(existing.get("metadata") or {"library_version": 0, "last_full_sync": None}),
                )
            )
        return discovered

    def pull_library(self, library_id: str, cursor: WebLibraryCursor | None = None, *, record_recovery_snapshot: bool = True) -> dict[str, object]:
        library = self.store.get_library(library_id)
        if not library:
            raise ValueError(f"Unknown canonical library: {library_id}")
        metadata = library.get("metadata") or {}
        since = cursor.library_version if cursor else int(metadata.get("library_version") or 0)
        collection_result = self._pull_kind(library_id, EntityType.COLLECTION, "collections", since=since)
        item_result = self._pull_kind(library_id, EntityType.ITEM, "items", since=since)
        last_modified = max(collection_result["library_version"], item_result["library_version"])
        updated = collection_result["updated"] + item_result["updated"]
        deleted = collection_result["deleted"] + item_result["deleted"]
        self.store.set_library_metadata(
            library_id,
            {
                "library_version": last_modified,
                "last_full_sync": now_iso() if since == 0 else metadata.get("last_full_sync"),
            },
        )
        file_result = self._sync_attachment_files(library_id)
        fulltext_result = self._pull_fulltext(library_id, since=int((self.store.get_library(library_id) or {}).get("metadata", {}).get("fulltext_version") or 0))
        pruned = self._prune_deleted_attachment_files(library_id)
        result = {
            "library_id": library_id,
            "updated": updated,
            "deleted": deleted,
            "library_version": last_modified,
            "files_downloaded": file_result["downloaded"],
            "files_skipped": file_result["skipped"],
            "files_pruned": pruned,
            "fulltext_updated": fulltext_result["updated"],
            "fulltext_version": fulltext_result["fulltext_version"],
        }
        self._refresh_qmd(library_id)
        if record_recovery_snapshot and self.client.settings.recovery_auto_snapshots:
            result["recovery_snapshot"] = RecoveryService(
                self.client.settings,
                canonical=self.store,
                qmd_indexer=self.qmd_indexer,
            ).create_snapshot(reason=f"post-pull:{library_id}")
        return result

    def list_conflicts(self, library_id: str, *, entity_type: EntityType | None = None) -> list[dict[str, object]]:
        return self.store.list_conflicted_entities(library_id, entity_type, limit=1000)

    def rebase_conflict_keep_local(
        self,
        library_id: str,
        entity_type: EntityType,
        entity_key: str,
    ) -> dict[str, object]:
        result = self.store.rebase_conflict_keep_local(library_id, entity_type, entity_key)
        self._refresh_qmd(library_id)
        return result

    def accept_remote_conflict(
        self,
        library_id: str,
        entity_type: EntityType,
        entity_key: str,
    ) -> dict[str, object]:
        result = self.store.accept_remote_conflict(library_id, entity_type, entity_key)
        self._refresh_qmd(library_id)
        return result

    def _pull_kind(
        self,
        library_id: str,
        entity_type: EntityType,
        remote_kind: str,
        *,
        since: int,
    ) -> dict[str, int]:
        versions, last_modified = self.client.get_versions(library_id, remote_kind, since=since)
        remote_keys = set(versions.keys())
        updated = 0
        changed_keys = list(versions.keys())
        if changed_keys:
            for start in range(0, len(changed_keys), 50):
                batch = changed_keys[start : start + 50]
                for payload in self.client.get_objects_by_keys(library_id, remote_kind, batch):
                    data = payload.get("data", payload)
                    if entity_type == EntityType.ITEM:
                        data = self._enrich_bbt_payload(data)
                    version = int(payload.get("version") or data.get("version") or 0)
                    entity_key = data.get("key") or payload.get("key")
                    existing = self.store.get_entity(library_id, entity_type, entity_key)
                    if existing and not existing["synced"]:
                        current_remote_version = int(existing.get("remote_version") or 0)
                        if version <= current_remote_version and not existing.get("conflict"):
                            continue
                        remote = {
                            "key": entity_key,
                            "version": version,
                            "data": data,
                        }
                        self.store.set_entity_conflict(
                            library_id,
                            entity_type,
                            entity_key,
                            self._conflict_payload(
                                library_id,
                                entity_type,
                                existing,
                                remote,
                                status=None,
                                message="Remote entity changed while local unsynced edits exist",
                                source="pull",
                            ),
                        )
                        updated += 1
                        continue
                    self.store.save_entity(
                        library_id,
                        entity_type,
                        data,
                        entity_key=entity_key,
                        version=version,
                        remote_version=version,
                        synced=True,
                        deleted=False,
                    )
                    updated += 1
        deleted = self.store.mark_missing_deleted(library_id, entity_type, remote_keys) if since == 0 else 0
        return {
            "updated": updated,
            "deleted": deleted,
            "library_version": last_modified,
        }

    def push_changes(self, library_id: str, changes: list[ChangeRecord] | None = None) -> dict[str, object]:
        recovery_snapshot = None
        if self.client.settings.recovery_auto_snapshots:
            recovery_snapshot = RecoveryService(
                self.client.settings,
                canonical=self.store,
                qmd_indexer=self.qmd_indexer,
            ).create_snapshot(reason=f"pre-push:{library_id}")
        collection_result = self._push_kind(library_id, EntityType.COLLECTION)
        item_result = self._push_kind(library_id, EntityType.ITEM)
        conflicts = collection_result["conflicts"] + item_result["conflicts"]
        failures = collection_result["failures"] + item_result["failures"]
        if conflicts or failures:
            pull_result = {
                "skipped": True,
                "reason": "push had conflicts or failures; final pull skipped to avoid overwriting unsynced local state",
            }
        else:
            pull_result = self.pull_library(library_id, record_recovery_snapshot=False)
        result = {
            "library_id": library_id,
            "pushed": collection_result["pushed"] + item_result["pushed"],
            "deleted": collection_result["deleted"] + item_result["deleted"],
            "conflicts": conflicts,
            "failures": failures,
            "pull_result": pull_result,
        }
        if recovery_snapshot:
            result["recovery_snapshot"] = recovery_snapshot
        if self.client.settings.recovery_auto_snapshots and not conflicts and not failures:
            result["post_recovery_snapshot"] = RecoveryService(
                self.client.settings,
                canonical=self.store,
                qmd_indexer=self.qmd_indexer,
            ).create_snapshot(reason=f"post-push:{library_id}")
        return result

    def _push_kind(self, library_id: str, entity_type: EntityType) -> dict[str, object]:
        pending = self.store.list_unsynced_entities(library_id, entity_type, limit=1000)
        pending = self._ordered_pending_entities(pending, entity_type)
        pushed = 0
        deleted = 0
        conflicts: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        library = self.store.get_library(library_id) or {}
        metadata = dict(library.get("metadata") or {})
        library_version = int(metadata.get("library_version") or 0)
        for entity in pending:
            payload = dict(entity["payload"])
            try:
                if entity["deleted"]:
                    payload.pop("key", None)
                    if entity.get("remote_version"):
                        if entity_type == EntityType.ITEM:
                            version = self.client.delete_item(
                                library_id,
                                entity["entity_key"],
                                item_version=int(entity["remote_version"]),
                            )
                        else:
                            version = self.client.delete_collection(
                                library_id,
                                entity["entity_key"],
                                collection_version=int(entity["remote_version"]),
                            )
                        self.store.mark_entity_synced(
                            library_id,
                            entity_type,
                            entity["entity_key"],
                            remote_version=version,
                            deleted=True,
                        )
                        if entity_type == EntityType.ITEM:
                            self._prune_cached_file_payload(payload)
                        library_version = max(library_version, int(version))
                        self.store.set_library_metadata(library_id, {"library_version": library_version})
                        deleted += 1
                    continue
                prepared_payload = self._prepare_remote_item_payload(payload) if entity_type == EntityType.ITEM else payload
                upload_request = (
                    self._attachment_upload_request(entity, prepared_payload)
                    if entity_type == EntityType.ITEM
                    else None
                )
                synced_payload = prepared_payload
                if entity.get("remote_version"):
                    prepared_payload.pop("key", None)
                    if entity_type == EntityType.ITEM:
                        version = self.client.update_item(
                            library_id,
                            entity["entity_key"],
                            prepared_payload,
                            item_version=int(entity["remote_version"]),
                        )
                    else:
                        version = self.client.update_collection(
                            library_id,
                            entity["entity_key"],
                            prepared_payload,
                            collection_version=int(entity["remote_version"]),
                        )
                    self._finalize_item_file_upload(
                        library_id,
                        entity,
                        synced_payload,
                        remote_version=version,
                        upload_request=upload_request,
                    ) if entity_type == EntityType.ITEM else self.store.mark_entity_synced(
                        library_id,
                        entity_type,
                        entity["entity_key"],
                        remote_version=version,
                    )
                    library_version = max(library_version, int(version))
                    self.store.set_library_metadata(library_id, {"library_version": library_version})
                    pushed += 1
                else:
                    prepared_payload.setdefault("key", entity["entity_key"])
                    if entity_type == EntityType.ITEM:
                        result = self.client.create_item(
                            library_id,
                            prepared_payload,
                            library_version=library_version or None,
                        )
                    else:
                        result = self.client.create_collection(
                            library_id,
                            prepared_payload,
                            library_version=library_version or None,
                        )
                    created_version = int(result.get("version") or 0)
                    refreshed = self._refresh_created_entity(library_id, entity_type, entity["entity_key"])
                    if refreshed:
                        created_version = max(created_version, int(refreshed["version"]))
                        if entity_type == EntityType.ITEM:
                            created_version = self._finalize_item_file_upload(
                                library_id,
                                entity,
                                synced_payload,
                                remote_version=created_version,
                                upload_request=upload_request,
                            )
                    elif created_version:
                        if entity_type == EntityType.ITEM:
                            created_version = self._finalize_item_file_upload(
                                library_id,
                                entity,
                                synced_payload,
                                remote_version=created_version,
                                upload_request=upload_request,
                            )
                        else:
                            self.store.mark_entity_synced(
                                library_id,
                                entity_type,
                                entity["entity_key"],
                                remote_version=created_version,
                            )
                    if created_version:
                        library_version = max(library_version, created_version)
                        self.store.set_library_metadata(library_id, {"library_version": library_version})
                    pushed += 1
            except ZoteroApiError as exc:
                remote = self._fetch_remote_entity(library_id, entity_type, entity["entity_key"])
                if exc.status == 412:
                    if entity["deleted"] and remote is None:
                        resolved_version = int(entity.get("remote_version") or library_version or entity["version"] or 0)
                        self.store.mark_entity_synced(
                            library_id,
                            entity_type,
                            entity["entity_key"],
                            remote_version=resolved_version,
                            deleted=True,
                        )
                        if entity_type == EntityType.ITEM:
                            self._prune_cached_file_payload(payload)
                        deleted += 1
                        continue
                    conflict = self._conflict_payload(
                        library_id,
                        entity_type,
                        entity,
                        remote,
                        status=exc.status,
                        message=str(exc),
                        source="push",
                    )
                    self.store.set_entity_conflict(
                        library_id,
                        entity_type,
                        entity["entity_key"],
                        conflict,
                    )
                    conflicts.append(
                        conflict
                    )
                else:
                    failures.append(
                        {
                            "library_id": library_id,
                            "entity_type": entity_type.value,
                            "entity_key": entity["entity_key"],
                            "status": exc.status,
                            "message": str(exc),
                            "body": exc.body,
                        }
                    )
            except Exception as exc:
                failures.append(
                    {
                        "library_id": library_id,
                        "entity_type": entity_type.value,
                        "entity_key": entity["entity_key"],
                        "status": None,
                        "message": str(exc),
                    }
                )
        return {"pushed": pushed, "deleted": deleted, "conflicts": conflicts, "failures": failures}

    def _conflict_payload(
        self,
        library_id: str,
        entity_type: EntityType,
        local_entity: dict[str, object],
        remote: dict[str, object] | None,
        *,
        status: int | None,
        message: str,
        source: str,
    ) -> dict[str, object]:
        return {
            "library_id": library_id,
            "entity_type": entity_type.value,
            "entity_key": local_entity["entity_key"],
            "status": status,
            "message": message,
            "source": source,
            "detected_at": now_iso(),
            "base_version": local_entity.get("remote_version"),
            "local_version": local_entity.get("version"),
            "remote": remote,
        }

    def _prepare_remote_item_payload(self, payload: dict[str, object]) -> dict[str, object]:
        prepared = dict(payload)
        if prepared.get("itemType") != "attachment":
            return prepared
        source_path = prepared.get("sourcePath")
        filename = prepared.get("filename")
        if not filename and isinstance(source_path, str) and source_path:
            if prepared.get("linkMode") == "embedded_image":
                prepared["filename"] = self._embedded_image_filename(prepared)
            else:
                prepared["filename"] = Path(source_path).name
            filename = prepared["filename"]
        if not prepared.get("contentType") and isinstance(filename, str) and filename:
            prepared["contentType"] = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return prepared

    def _enrich_bbt_payload(self, payload: dict[str, object]) -> dict[str, object]:
        enriched = dict(payload)
        fields = dict(enriched.get("fields") or {})
        citation_key = detect_citation_key(enriched, fields)
        citation_aliases = detect_citation_aliases(enriched, fields)
        if enriched.get("itemType") == "annotation" and not enriched.get("title"):
            derived_title = annotation_display_title(enriched)
            if derived_title:
                enriched["title"] = derived_title
        if citation_key:
            enriched["citationKey"] = citation_key
        if citation_aliases:
            enriched["citationAliases"] = citation_aliases
        return enriched

    def _embedded_image_filename(self, payload: dict[str, object]) -> str:
        content_type = str(payload.get("contentType") or "").strip().lower()
        extension = self.EMBEDDED_IMAGE_EXTENSIONS.get(content_type)
        if not extension:
            raise ValueError(f"Unsupported embedded image content type: {payload.get('contentType')!r}")
        return f"image.{extension}"

    def _attachment_upload_request(
        self,
        entity: dict[str, object],
        payload: dict[str, object],
    ) -> dict[str, object] | None:
        if payload.get("itemType") != "attachment":
            return None
        if payload.get("linkMode") not in {"imported_file", "imported_url", "embedded_image"}:
            return None
        source_path = payload.get("sourcePath")
        if not isinstance(source_path, str) or not source_path:
            return None
        source = Path(source_path)
        requested_filename = payload.get("filename")
        filename = str(requested_filename) if isinstance(requested_filename, str) and requested_filename else None
        if payload.get("linkMode") == "imported_url" and self._should_zip_snapshot_transport(source, payload):
            lead_file = self._resolve_snapshot_lead_file(source, filename)
            filename = lead_file.name
        request: dict[str, object] = {
            "sourcePath": source_path,
            "filename": filename or source.name,
        }
        content_type = payload.get("contentType")
        if isinstance(content_type, str) and content_type:
            request["contentType"] = content_type
        previous_md5 = payload.get("md5")
        if isinstance(previous_md5, str) and previous_md5:
            request["previousMd5"] = previous_md5
        if payload.get("linkMode") == "imported_url" and self._should_zip_snapshot_transport(source, payload):
            request.update(self._build_snapshot_upload_transport(str(entity["entity_key"]), source, request))
        return request

    def _should_zip_snapshot_transport(self, source_path: Path, payload: dict[str, object]) -> bool:
        if source_path.is_dir():
            return True
        content_type = str(payload.get("contentType") or "").lower()
        if content_type.startswith("text/html"):
            return True
        filename = str(payload.get("filename") or source_path.name).lower()
        return filename.endswith(".html") or filename.endswith(".htm")

    def _resolve_snapshot_lead_file(self, source_path: Path, filename: str | None) -> Path:
        if source_path.is_file():
            return source_path
        if filename:
            candidate = source_path / filename
            if candidate.exists() and candidate.is_file():
                return candidate
        html_candidates = sorted(
            child for child in source_path.rglob("*") if child.is_file() and child.suffix.lower() in {".html", ".htm"}
        )
        if html_candidates:
            return html_candidates[0]
        file_candidates = sorted(child for child in source_path.rglob("*") if child.is_file())
        if file_candidates:
            return file_candidates[0]
        if filename:
            raise FileNotFoundError(f"Snapshot directory does not contain lead file {filename!r}: {source_path}")
        raise FileNotFoundError(f"Snapshot directory contains no files: {source_path}")

    def _build_snapshot_upload_transport(
        self,
        item_key: str,
        source_path: Path,
        request: dict[str, object],
    ) -> dict[str, object]:
        filename = str(request["filename"])
        lead_file = self._resolve_snapshot_lead_file(source_path, filename if source_path.is_dir() else None)
        if source_path.is_dir():
            request["filename"] = lead_file.name
            filename = lead_file.name
            zip_bytes = self._zip_directory(source_path)
        else:
            lead_file = source_path
            zip_bytes = self._zip_single_file(source_path, filename)
        request["uploadBytes"] = zip_bytes
        request["uploadFilename"] = f"{item_key}.zip"
        request["uploadContentType"] = "application/zip"
        request["md5"] = hashlib.md5(lead_file.read_bytes()).hexdigest()
        request["mtime"] = int(lead_file.stat().st_mtime * 1000)
        return request

    def _zip_single_file(self, path: Path, arcname: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(arcname, path.read_bytes())
        return buffer.getvalue()

    def _zip_directory(self, directory: Path) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for child in sorted(directory.rglob("*")):
                if child.is_dir():
                    continue
                zf.write(child, child.relative_to(directory).as_posix())
        return buffer.getvalue()

    def _finalize_item_file_upload(
        self,
        library_id: str,
        entity: dict[str, object],
        synced_payload: dict[str, object],
        *,
        remote_version: int,
        upload_request: dict[str, str] | None,
    ) -> int:
        if not upload_request:
            self.store.mark_entity_synced(
                library_id,
                EntityType.ITEM,
                entity["entity_key"],
                remote_version=remote_version,
            )
            return remote_version

        try:
            self.client.upload_attachment_file(
                library_id,
                str(entity["entity_key"]),
                source_path=upload_request["sourcePath"],
                filename=upload_request.get("filename") if isinstance(upload_request.get("filename"), str) else None,
                content_type=upload_request.get("contentType") if isinstance(upload_request.get("contentType"), str) else None,
                previous_md5=upload_request.get("previousMd5") if isinstance(upload_request.get("previousMd5"), str) else None,
                upload_bytes=upload_request.get("uploadBytes") if isinstance(upload_request.get("uploadBytes"), bytes) else None,
                upload_filename=upload_request.get("uploadFilename") if isinstance(upload_request.get("uploadFilename"), str) else None,
                upload_content_type=upload_request.get("uploadContentType") if isinstance(upload_request.get("uploadContentType"), str) else None,
                md5=upload_request.get("md5") if isinstance(upload_request.get("md5"), str) else None,
                mtime=upload_request.get("mtime") if isinstance(upload_request.get("mtime"), int) else None,
            )
            refreshed = self._refresh_created_entity(library_id, EntityType.ITEM, str(entity["entity_key"]))
            if refreshed:
                return int(refreshed["version"])
            self.store.mark_entity_synced(
                library_id,
                EntityType.ITEM,
                entity["entity_key"],
                remote_version=remote_version,
            )
            return remote_version
        except Exception:
            self.store.save_entity(
                library_id,
                EntityType.ITEM,
                synced_payload,
                entity_key=str(entity["entity_key"]),
                version=int(entity["version"]),
                remote_version=remote_version,
                synced=False,
                deleted=False,
            )
            raise

    def _ordered_pending_entities(
        self,
        pending: list[dict[str, object]],
        entity_type: EntityType,
    ) -> list[dict[str, object]]:
        if entity_type not in {EntityType.COLLECTION, EntityType.ITEM} or not pending:
            return pending

        by_key = {str(entity["entity_key"]): entity for entity in pending}

        def parent_key(entity: dict[str, object]) -> str | None:
            payload = dict(entity.get("payload") or {})
            parent_field = "parentCollection" if entity_type == EntityType.COLLECTION else "parentItem"
            parent_key_field = "parentCollectionKey" if entity_type == EntityType.COLLECTION else "parentItemKey"
            parent = payload.get(parent_field)
            if isinstance(parent, str) and parent:
                return parent
            parent = payload.get(parent_key_field)
            if isinstance(parent, str) and parent:
                return parent
            return None

        def topo(entities: list[dict[str, object]], *, include_deleted_parents: bool) -> list[dict[str, object]]:
            ordered: list[dict[str, object]] = []
            visiting: set[str] = set()
            visited: set[str] = set()

            def visit(entity: dict[str, object]) -> None:
                key = str(entity["entity_key"])
                if key in visited:
                    return
                if key in visiting:
                    ordered.append(entity)
                    visited.add(key)
                    return
                visiting.add(key)
                parent = parent_key(entity)
                if parent and parent in by_key and (include_deleted_parents or not by_key[parent]["deleted"]):
                    visit(by_key[parent])
                visiting.remove(key)
                visited.add(key)
                ordered.append(entity)

            for entity in entities:
                visit(entity)
            return ordered

        active = [entity for entity in pending if not entity["deleted"]]
        deleted = [entity for entity in pending if entity["deleted"]]
        ordered_active = topo(active, include_deleted_parents=False)
        ordered_deleted = list(reversed(topo(deleted, include_deleted_parents=True)))
        return ordered_active + ordered_deleted

    def _file_cache_path(self, library_id: str, item_key: str, filename: str) -> Path:
        safe_name = Path(filename).name or item_key
        return self.file_cache_dir / library_id.replace(":", "_") / item_key / safe_name

    def _prune_cached_file_payload(self, payload: dict[str, object]) -> bool:
        file_dir = payload.get("headlessFileDir")
        if isinstance(file_dir, str) and file_dir:
            path = Path(file_dir)
            if path.exists():
                for nested in sorted(path.rglob("*"), reverse=True):
                    if nested.is_file():
                        nested.unlink()
                    elif nested.is_dir():
                        nested.rmdir()
                path.rmdir()
            parent = path.parent
            while parent != self.file_cache_dir and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            return True
        file_path = payload.get("headlessFilePath")
        if not isinstance(file_path, str) or not file_path:
            return False
        path = Path(file_path)
        if path.exists():
            path.unlink()
        parent = path.parent
        while parent != self.file_cache_dir and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return True

    def _prune_deleted_attachment_files(self, library_id: str) -> int:
        pruned = 0
        for entity in self.store.list_entities(library_id, EntityType.ITEM, limit=100000, include_deleted=True):
            if not entity["deleted"]:
                continue
            payload = dict(entity["payload"])
            if payload.get("itemType") != "attachment":
                continue
            if self._prune_cached_file_payload(payload):
                pruned += 1
        return pruned

    def _sync_attachment_files(self, library_id: str) -> dict[str, int]:
        downloaded = 0
        skipped = 0
        for entity in self.store.list_entities(library_id, EntityType.ITEM, limit=100000):
            payload = dict(entity["payload"])
            if not entity["synced"]:
                skipped += 1
                continue
            if payload.get("itemType") != "attachment":
                continue
            if payload.get("linkMode") not in {"imported_file", "imported_url", "embedded_image"}:
                continue
            filename = payload.get("filename")
            remote_md5 = payload.get("md5")
            if not isinstance(filename, str) or not filename:
                skipped += 1
                continue
            cache_path = self._file_cache_path(library_id, str(entity["entity_key"]), filename)
            cached_md5 = payload.get("headlessFileMd5")
            if (
                cache_path.exists()
                and isinstance(remote_md5, str)
                and remote_md5
                and cached_md5 == remote_md5
            ):
                skipped += 1
                continue
            download = self.client.download_attachment_file(library_id, str(entity["entity_key"]))
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            downloaded_path, cache_dir = self._materialize_attachment_download(
                cache_path.parent,
                filename,
                download,
            )
            etag = str((download.get("headers") or {}).get("ETag") or "").strip('"')
            effective_md5 = str(remote_md5 or etag or hashlib.md5(download["body"]).hexdigest())
            enriched = dict(payload)
            enriched["headlessFilePath"] = str(downloaded_path)
            enriched["headlessFileDir"] = str(cache_dir)
            enriched["headlessFileMd5"] = effective_md5
            enriched["headlessFileETag"] = etag or None
            self.store.save_entity(
                library_id,
                EntityType.ITEM,
                enriched,
                entity_key=str(entity["entity_key"]),
                version=int(entity["version"]),
                remote_version=int(entity.get("remote_version") or entity["version"]),
                synced=True,
                deleted=False,
            )
            downloaded += 1
        return {"downloaded": downloaded, "skipped": skipped}

    def _materialize_attachment_download(
        self,
        cache_dir: Path,
        filename: str,
        download: dict[str, object],
    ) -> tuple[Path, Path]:
        headers = {str(k): str(v) for k, v in (download.get("headers") or {}).items()}
        body = download["body"]
        if not isinstance(body, bytes):
            raise TypeError("download body must be bytes")
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        is_zip = content_type == "application/zip" or body.startswith(b"PK\x03\x04")
        if not is_zip:
            path = cache_dir / filename
            path.write_bytes(body)
            return path, cache_dir

        for child in list(cache_dir.iterdir()):
            if child.is_dir():
                for nested in sorted(child.rglob("*"), reverse=True):
                    if nested.is_file():
                        nested.unlink()
                    elif nested.is_dir():
                        nested.rmdir()
                child.rmdir()
            else:
                child.unlink()
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            extracted_paths: list[Path] = []
            for member in zf.infolist():
                if member.is_dir():
                    continue
                dest = (cache_dir / member.filename).resolve()
                cache_root = cache_dir.resolve()
                if cache_root not in dest.parents and dest != cache_root:
                    raise ValueError(f"Refusing to extract ZIP member outside cache dir: {member.filename}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as out:
                    out.write(src.read())
                extracted_paths.append(dest)
        preferred = cache_dir / filename
        if preferred.exists():
            return preferred, cache_dir
        if len(extracted_paths) == 1:
            return extracted_paths[0], cache_dir
        html_files = [path for path in extracted_paths if path.suffix.lower() in {".html", ".htm"}]
        if len(html_files) == 1:
            return html_files[0], cache_dir
        if extracted_paths:
            return extracted_paths[0], cache_dir
        raise ValueError("ZIP download contained no files")

    def _pull_fulltext(self, library_id: str, *, since: int) -> dict[str, int]:
        try:
            versions, last_modified = self.client.get_fulltext_versions(library_id, since=since)
        except ZoteroApiError:
            return {"updated": 0, "fulltext_version": since}
        updated = 0
        for item_key in versions:
            entity = self.store.get_entity(library_id, EntityType.ITEM, item_key)
            if not entity:
                continue
            if not entity["synced"]:
                continue
            try:
                fulltext = self.client.get_item_fulltext(library_id, item_key)
            except ZoteroApiError as exc:
                if exc.status == 404:
                    continue
                raise
            payload = dict(entity["payload"])
            payload["fulltext"] = fulltext
            self.store.save_entity(
                library_id,
                EntityType.ITEM,
                payload,
                entity_key=item_key,
                version=int(entity["version"]),
                remote_version=int(entity.get("remote_version") or entity["version"]),
                synced=True,
                deleted=False,
            )
            updated += 1
        library = self.store.get_library(library_id) or {}
        metadata = dict(library.get("metadata") or {})
        if last_modified:
            metadata["fulltext_version"] = last_modified
            self.store.set_library_metadata(library_id, metadata)
        return {"updated": updated, "fulltext_version": int(metadata.get("fulltext_version") or since)}

    def _refresh_created_entity(
        self,
        library_id: str,
        entity_type: EntityType,
        entity_key: str,
    ) -> dict[str, object] | None:
        remote_kind = "items" if entity_type == EntityType.ITEM else "collections"
        objects = self.client.get_objects_by_keys(library_id, remote_kind, [entity_key])
        if not objects:
            return None
        payload = objects[0]
        data = payload.get("data", payload)
        if entity_type == EntityType.ITEM:
            data = self._enrich_bbt_payload(data)
        version = int(payload.get("version") or data.get("version") or 0)
        self.store.save_entity(
            library_id,
            entity_type,
            data,
            entity_key=data.get("key") or payload.get("key") or entity_key,
            version=version,
            remote_version=version,
            synced=True,
            deleted=False,
        )
        return {"version": version, "payload": data}

    def _fetch_remote_entity(
        self,
        library_id: str,
        entity_type: EntityType,
        entity_key: str,
    ) -> dict[str, object] | None:
        remote_kind = "items" if entity_type == EntityType.ITEM else "collections"
        objects = self.client.get_objects_by_keys(library_id, remote_kind, [entity_key])
        if not objects:
            return None
        payload = objects[0]
        data = payload.get("data", payload)
        return {
            "key": data.get("key") or payload.get("key"),
            "version": int(payload.get("version") or data.get("version") or 0),
            "data": data,
        }
