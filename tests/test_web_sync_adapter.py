import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from zotero_headless.adapters.web_sync import CanonicalWebSyncAdapter
from zotero_headless.config import Settings
from zotero_headless.core import CanonicalStore, ChangeType, EntityType
from zotero_headless.web_api import ZoteroApiError


class FakeWebClient:
    def __init__(self):
        self.settings = Settings(api_key="test-key", state_dir=tempfile.mkdtemp())
        self.created: list[tuple[str, dict]] = []
        self.create_versions: list[int | None] = []
        self.created_collections: list[tuple[str, dict]] = []
        self.create_collection_versions: list[int | None] = []
        self.updated: list[tuple[str, str, dict, int | None]] = []
        self.updated_collections: list[tuple[str, str, dict, int | None]] = []
        self.deleted: list[tuple[str, str, int]] = []
        self.deleted_collections: list[tuple[str, str, int]] = []
        self.uploads: list[dict[str, object]] = []
        self.downloads: list[tuple[str, str]] = []
        self.remote_items: dict[str, dict] = {}
        self.remote_collections: dict[str, dict] = {}
        self.fulltext_versions: dict[str, int] = {}
        self.fulltext_payloads: dict[str, dict] = {}
        self.download_payloads: dict[str, dict[str, object]] = {}

    def get_current_key(self):
        return {
            "userID": 123,
            "username": "demo-user",
            "access": {
                "user": {"library": True, "write": True},
                "groups": {"all": {"write": True}},
            },
        }

    def get_group_versions(self, user_id: int):
        return ({"456": 1}, 1)

    def get_group(self, group_id):
        return ({"data": {"name": "Demo Group"}}, 1)

    def get_versions(self, library_id: str, kind: str, *, since: int = 0):
        bucket = self.remote_items if kind == "items" else self.remote_collections
        versions = {
            key: value["version"]
            for key, value in bucket.items()
            if not since or value["version"] > since
        }
        max_version = max([0] + [value["version"] for value in bucket.values()])
        return versions, max_version

    def get_objects_by_keys(self, library_id: str, kind: str, keys: list[str]):
        bucket = self.remote_items if kind == "items" else self.remote_collections
        return [bucket[key] for key in keys if key in bucket]

    def create_item(self, library_id: str, item_data: dict, *, library_version=None):
        key = item_data.get("key") or f"REMOTE{len(self.remote_items) + 1}"
        payload = {"key": key, "version": 1, "data": {"key": key, "version": 1, **item_data}}
        self.remote_items[key] = payload
        self.created.append((library_id, item_data))
        self.create_versions.append(library_version)
        return {"result": {"successful": {"0": {"key": key}}}, "version": 1}

    def create_collection(self, library_id: str, collection_data: dict, *, library_version=None):
        key = collection_data.get("key") or f"COLL{len(self.remote_collections) + 1}"
        payload = {"key": key, "version": 1, "data": {"key": key, "version": 1, **collection_data}}
        self.remote_collections[key] = payload
        self.created_collections.append((library_id, collection_data))
        self.create_collection_versions.append(library_version)
        return {"result": {"successful": {"0": {"key": key}}}, "version": 1}

    def update_item(self, library_id: str, item_key: str, item_data: dict, *, item_version=None, full=False):
        payload = self.remote_items[item_key]
        next_version = int(payload["version"]) + 1
        payload["version"] = next_version
        payload["data"] = {"key": item_key, "version": next_version, **item_data}
        self.updated.append((library_id, item_key, item_data, item_version))
        return next_version

    def update_collection(self, library_id: str, collection_key: str, collection_data: dict, *, collection_version=None):
        payload = self.remote_collections[collection_key]
        next_version = int(payload["version"]) + 1
        payload["version"] = next_version
        payload["data"] = {"key": collection_key, "version": next_version, **collection_data}
        self.updated_collections.append((library_id, collection_key, collection_data, collection_version))
        return next_version

    def delete_item(self, library_id: str, item_key: str, *, item_version: int):
        self.deleted.append((library_id, item_key, item_version))
        self.remote_items.pop(item_key, None)
        return item_version + 1

    def delete_collection(self, library_id: str, collection_key: str, *, collection_version: int):
        self.deleted_collections.append((library_id, collection_key, collection_version))
        self.remote_collections.pop(collection_key, None)
        return collection_version + 1

    def upload_attachment_file(
        self,
        library_id: str,
        item_key: str,
        *,
        source_path: str,
        filename: str | None = None,
        content_type: str | None = None,
        previous_md5: str | None = None,
        upload_bytes: bytes | None = None,
        upload_filename: str | None = None,
        upload_content_type: str | None = None,
        md5: str | None = None,
        mtime: int | None = None,
    ):
        self.uploads.append(
            {
                "library_id": library_id,
                "item_key": item_key,
                "source_path": source_path,
                "filename": filename,
                "content_type": content_type,
                "previous_md5": previous_md5,
                "upload_bytes": upload_bytes,
                "upload_filename": upload_filename,
                "upload_content_type": upload_content_type,
                "md5": md5,
                "mtime": mtime,
            }
        )
        payload = self.remote_items[item_key]
        next_version = int(payload["version"]) + 1
        payload["version"] = next_version
        payload["data"] = {
            **payload["data"],
            "key": item_key,
            "version": next_version,
            "filename": filename or payload["data"].get("filename"),
            "contentType": content_type or payload["data"].get("contentType"),
            "md5": "uploaded-md5",
        }
        return {"uploaded": True, "exists": False, "filename": filename, "contentType": content_type, "md5": "uploaded-md5"}

    def download_attachment_file(self, library_id: str, item_key: str):
        self.downloads.append((library_id, item_key))
        if item_key in self.download_payloads:
            return self.download_payloads[item_key]
        payload = self.remote_items[item_key]
        filename = payload["data"].get("filename", f"{item_key}.bin")
        md5 = payload["data"].get("md5", "downloaded-md5")
        return {
            "status": 200,
            "headers": {"ETag": f'"{md5}"'},
            "body": f"download:{filename}".encode("utf-8"),
        }

    def get_fulltext_versions(self, library_id: str, *, since: int = 0):
        versions = {key: version for key, version in self.fulltext_versions.items() if not since or version > since}
        max_version = max([since] + list(versions.values())) if versions else since
        return versions, max_version

    def get_item_fulltext(self, library_id: str, item_key: str):
        return self.fulltext_payloads[item_key]


class FakeQmdIndexer:
    def __init__(self):
        self.refreshes: list[str] = []

    def refresh_canonical_library(self, store, library_id: str):
        self.refreshes.append(library_id)
        return {"enabled": True, "library_id": library_id}


class CanonicalWebSyncAdapterTests(unittest.TestCase):
    def test_discover_libraries_populates_canonical_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = CanonicalWebSyncAdapter(store, FakeWebClient())
            libraries = adapter.discover_libraries()
            self.assertEqual(len(libraries), 2)
            self.assertIsNotNone(store.get_library("user:123"))
            self.assertIsNotNone(store.get_library("group:456"))

    def test_discover_libraries_preserves_existing_sync_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 88, "last_full_sync": "2026-04-06T17:00:00Z"},
            )
            adapter = CanonicalWebSyncAdapter(store, FakeWebClient())

            libraries = adapter.discover_libraries()

            user = next(entry for entry in libraries if entry["library_id"] == "user:123")
            self.assertEqual(user["metadata"]["library_version"], 88)
            self.assertEqual(user["metadata"]["last_full_sync"], "2026-04-06T17:00:00Z")

    def test_pull_library_imports_remote_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            client = FakeWebClient()
            client.remote_items["ABCD1234"] = {
                "key": "ABCD1234",
                "version": 5,
                "data": {"key": "ABCD1234", "version": 5, "itemType": "book", "title": "Remote"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)
            result = adapter.pull_library("user:123")
            self.assertEqual(result["updated"], 1)
            entity = store.get_entity("user:123", EntityType.ITEM, "ABCD1234")
            self.assertEqual(entity["remote_version"], 5)
            self.assertTrue(entity["synced"])

    def test_pull_library_triggers_qmd_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            client = FakeWebClient()
            client.remote_items["ABCD1234"] = {
                "key": "ABCD1234",
                "version": 5,
                "data": {"key": "ABCD1234", "version": 5, "itemType": "book", "title": "Remote"},
            }
            qmd_indexer = FakeQmdIndexer()
            adapter = CanonicalWebSyncAdapter(store, client, qmd_indexer=qmd_indexer)

            adapter.pull_library("user:123")

            self.assertEqual(qmd_indexer.refreshes, ["user:123"])

    def test_pull_library_enriches_better_bibtex_metadata_from_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            client = FakeWebClient()
            client.remote_items["ABCD1234"] = {
                "key": "ABCD1234",
                "version": 5,
                "data": {
                    "key": "ABCD1234",
                    "version": 5,
                    "itemType": "book",
                    "title": "Remote",
                    "extra": "Citation Key: doe2026alpha\ntex.ids: doe2026alpha, doe2026book",
                },
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            adapter.pull_library("user:123")

            entity = store.get_entity("user:123", EntityType.ITEM, "ABCD1234")
            self.assertEqual(entity["payload"]["citationKey"], "doe2026alpha")
            self.assertEqual(entity["payload"]["citationAliases"], ["doe2026alpha", "doe2026book"])

    def test_pull_library_derives_annotation_title_from_remote_annotation_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            client = FakeWebClient()
            client.remote_items["ANNO1234"] = {
                "key": "ANNO1234",
                "version": 6,
                "data": {
                    "key": "ANNO1234",
                    "version": 6,
                    "itemType": "annotation",
                    "annotationType": "highlight",
                    "annotationText": "Important passage that should become the derived title",
                    "annotationPageLabel": "4",
                    "parentItem": "ATTACH01",
                },
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            adapter.pull_library("user:123")

            entity = store.get_entity("user:123", EntityType.ITEM, "ANNO1234")
            self.assertEqual(
                entity["payload"]["title"],
                "highlight@4: Important passage that should become the derived title",
            )
            self.assertEqual(entity["payload"]["parentItem"], "ATTACH01")

    def test_pull_library_imports_remote_collections_and_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            client = FakeWebClient()
            client.remote_collections["COLL1234"] = {
                "key": "COLL1234",
                "version": 4,
                "data": {"key": "COLL1234", "version": 4, "name": "Reading"},
            }
            client.remote_items["ABCD1234"] = {
                "key": "ABCD1234",
                "version": 5,
                "data": {"key": "ABCD1234", "version": 5, "itemType": "book", "title": "Remote"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)
            result = adapter.pull_library("user:123")
            self.assertEqual(result["updated"], 2)
            collection = store.get_entity("user:123", EntityType.COLLECTION, "COLL1234")
            item = store.get_entity("user:123", EntityType.ITEM, "ABCD1234")
            self.assertEqual(collection["payload"]["name"], "Reading")
            self.assertEqual(collection["remote_version"], 4)
            self.assertTrue(collection["synced"])
            self.assertEqual(item["remote_version"], 5)
            self.assertEqual(result["library_version"], 5)

    def test_pull_library_downloads_attachment_files_and_fulltext(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"fulltext_version": 0},
            )
            client = FakeWebClient()
            client.settings = Settings(api_key="test-key", state_dir=tmp)
            client.remote_items["ATTACH01"] = {
                "key": "ATTACH01",
                "version": 5,
                "data": {
                    "key": "ATTACH01",
                    "version": 5,
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper.pdf",
                    "md5": "remote-md5",
                    "contentType": "application/pdf",
                    "title": "Paper PDF",
                },
            }
            client.fulltext_versions["ATTACH01"] = 7
            client.fulltext_payloads["ATTACH01"] = {"content": "Extracted PDF text", "indexedChars": 18, "totalChars": 18}
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.pull_library("user:123")

            self.assertEqual(result["updated"], 1)
            self.assertEqual(result["files_downloaded"], 1)
            self.assertEqual(result["fulltext_updated"], 1)
            self.assertEqual(client.downloads, [("user:123", "ATTACH01")])
            entity = store.get_entity("user:123", EntityType.ITEM, "ATTACH01")
            self.assertEqual(entity["payload"]["fulltext"]["content"], "Extracted PDF text")
            cached_path = Path(entity["payload"]["headlessFilePath"])
            self.assertTrue(cached_path.exists())
            self.assertEqual(cached_path.read_bytes(), b"download:paper.pdf")
            self.assertEqual(entity["payload"]["headlessFileMd5"], "remote-md5")
            library = store.get_library("user:123")
            self.assertEqual(library["metadata"]["fulltext_version"], 7)

    def test_pull_library_prunes_cached_file_for_remote_deleted_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            cached_dir = Path(tmp) / "files" / "user_123" / "ATTACH01"
            cached_dir.mkdir(parents=True)
            cached_file = cached_dir / "paper.pdf"
            cached_file.write_bytes(b"cached")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper.pdf",
                    "headlessFilePath": str(cached_file),
                },
                entity_key="ATTACH01",
                version=5,
                remote_version=5,
                synced=True,
            )
            client = FakeWebClient()
            client.settings = Settings(api_key="test-key", state_dir=tmp)
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.pull_library("user:123")

            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["files_pruned"], 1)
            self.assertFalse(cached_file.exists())

    def test_pull_library_extracts_zip_snapshot_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"fulltext_version": 0},
            )
            client = FakeWebClient()
            client.settings = Settings(api_key="test-key", state_dir=tmp)
            client.remote_items["SNAPZIP1"] = {
                "key": "SNAPZIP1",
                "version": 5,
                "data": {
                    "key": "SNAPZIP1",
                    "version": 5,
                    "itemType": "attachment",
                    "linkMode": "imported_url",
                    "filename": "index.html",
                    "md5": "remote-md5",
                    "contentType": "text/html",
                    "title": "Snapshot",
                },
            }
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("index.html", "<html>snapshot</html>")
                zf.writestr("image.png", b"png-bytes")
            client.download_payloads["SNAPZIP1"] = {
                "status": 200,
                "headers": {"Content-Type": "application/zip", "ETag": '"remote-md5"'},
                "body": zip_buffer.getvalue(),
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.pull_library("user:123")

            self.assertEqual(result["files_downloaded"], 1)
            entity = store.get_entity("user:123", EntityType.ITEM, "SNAPZIP1")
            self.assertEqual(Path(entity["payload"]["headlessFilePath"]).name, "index.html")
            self.assertTrue(Path(entity["payload"]["headlessFilePath"]).exists())
            self.assertTrue((Path(entity["payload"]["headlessFileDir"]) / "image.png").exists())

    def test_push_changes_creates_remote_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local Draft"},
                entity_key="LOCAL123",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)
            result = adapter.push_changes("user:123")
            self.assertEqual(result["pushed"], 1)
            entities = store.list_entities("user:123", EntityType.ITEM)
            self.assertEqual(len(entities), 1)
            self.assertTrue(entities[0]["synced"])
            self.assertEqual(entities[0]["entity_key"], "LOCAL123")
            self.assertEqual(client.created[0][1]["key"], "LOCAL123")
            self.assertIsNone(client.create_versions[0])

    def test_push_changes_creates_remote_collections_before_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.COLLECTION,
                {"name": "Reading"},
                entity_key="COLL1234",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local Draft", "collections": ["COLL1234"]},
                entity_key="LOCAL123",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)
            result = adapter.push_changes("user:123")
            self.assertEqual(result["pushed"], 2)
            self.assertEqual(client.created_collections[0][1]["key"], "COLL1234")
            self.assertEqual(client.created_collections[0][1]["name"], "Reading")
            self.assertEqual(client.created[0][1]["collections"], ["COLL1234"])
            self.assertIsNone(client.create_collection_versions[0])
            collection = store.get_entity("user:123", EntityType.COLLECTION, "COLL1234")
            self.assertTrue(collection["synced"])

    def test_push_changes_orders_parent_collections_before_child_collections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.COLLECTION,
                {"name": "Child", "parentCollection": "PARENT01"},
                entity_key="CHILD001",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            store.save_entity(
                "user:123",
                EntityType.COLLECTION,
                {"name": "Parent"},
                entity_key="PARENT01",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 2)
            self.assertEqual([entry[1]["key"] for entry in client.created_collections], ["PARENT01", "CHILD001"])
            self.assertEqual(client.created_collections[1][1]["parentCollection"], "PARENT01")

    def test_push_changes_orders_child_collection_delete_before_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.COLLECTION,
                {"key": "PARENT01", "name": "Parent"},
                entity_key="PARENT01",
                version=10,
                remote_version=10,
                synced=True,
            )
            store.save_entity(
                "user:123",
                EntityType.COLLECTION,
                {"key": "CHILD001", "name": "Child", "parentCollection": "PARENT01"},
                entity_key="CHILD001",
                version=11,
                remote_version=11,
                synced=True,
            )
            store.delete_entity("user:123", EntityType.COLLECTION, "PARENT01")
            store.delete_entity("user:123", EntityType.COLLECTION, "CHILD001")
            client = FakeWebClient()
            client.remote_collections["PARENT01"] = {
                "key": "PARENT01",
                "version": 10,
                "data": {"key": "PARENT01", "version": 10, "name": "Parent"},
            }
            client.remote_collections["CHILD001"] = {
                "key": "CHILD001",
                "version": 11,
                "data": {"key": "CHILD001", "version": 11, "name": "Child", "parentCollection": "PARENT01"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["deleted"], 2)
            self.assertEqual([entry[1] for entry in client.deleted_collections], ["CHILD001", "PARENT01"])

    def test_push_changes_orders_parent_items_before_child_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "note", "note": "<p>Child</p>", "parentItemKey": "PARENT01"},
                entity_key="CHILD001",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Parent"},
                entity_key="PARENT01",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 2)
            self.assertEqual([entry[1]["key"] for entry in client.created], ["PARENT01", "CHILD001"])
            self.assertEqual(client.created[1][1]["parentItemKey"], "PARENT01")

    def test_push_changes_orders_parent_attachments_before_child_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "annotation",
                    "annotationType": "highlight",
                    "annotationText": "Annotated text",
                    "parentItemKey": "ATTACH01",
                },
                entity_key="ANNO0001",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "linked_url",
                    "url": "https://example.test/paper.pdf",
                    "title": "Attachment parent",
                },
                entity_key="ATTACH01",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 2)
            self.assertEqual([entry[1]["key"] for entry in client.created], ["ATTACH01", "ANNO0001"])
            self.assertEqual(client.created[1][1]["parentItemKey"], "ATTACH01")

    def test_push_changes_orders_child_item_delete_before_parent_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"key": "PARENT01", "itemType": "book", "title": "Parent"},
                entity_key="PARENT01",
                version=10,
                remote_version=10,
                synced=True,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"key": "CHILD001", "itemType": "note", "note": "<p>Child</p>", "parentItem": "PARENT01"},
                entity_key="CHILD001",
                version=11,
                remote_version=11,
                synced=True,
            )
            store.delete_entity("user:123", EntityType.ITEM, "PARENT01")
            store.delete_entity("user:123", EntityType.ITEM, "CHILD001")
            client = FakeWebClient()
            client.remote_items["PARENT01"] = {
                "key": "PARENT01",
                "version": 10,
                "data": {"key": "PARENT01", "version": 10, "itemType": "book", "title": "Parent"},
            }
            client.remote_items["CHILD001"] = {
                "key": "CHILD001",
                "version": 11,
                "data": {"key": "CHILD001", "version": 11, "itemType": "note", "note": "<p>Child</p>", "parentItem": "PARENT01"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["deleted"], 2)
            self.assertEqual([entry[1] for entry in client.deleted], ["CHILD001", "PARENT01"])

    def test_push_changes_uses_library_version_for_creates_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.COLLECTION,
                {"name": "Reading"},
                entity_key="COLL1234",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local Draft"},
                entity_key="LOCAL123",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)
            adapter.push_changes("user:123")
            self.assertEqual(client.create_collection_versions[0], 77)
            self.assertEqual(client.create_versions[0], 77)

    def test_push_changes_refreshes_created_item_to_actual_remote_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local Draft"},
                entity_key="LOCAL123",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()

            def create_item_with_higher_object_version(library_id, item_data, *, library_version=None):
                key = item_data.get("key") or "LOCAL123"
                client.remote_items[key] = {
                    "key": key,
                    "version": 79,
                    "data": {"key": key, "version": 79, **item_data},
                }
                client.created.append((library_id, item_data))
                client.create_versions.append(library_version)
                return {"result": {"successful": {"0": {"key": key}}}, "version": 78}

            client.create_item = create_item_with_higher_object_version
            adapter = CanonicalWebSyncAdapter(store, client)

            adapter.push_changes("user:123")

            entity = store.get_entity("user:123", EntityType.ITEM, "LOCAL123")
            self.assertTrue(entity["synced"])
            self.assertEqual(entity["remote_version"], 79)
            self.assertEqual(entity["version"], 79)

    def test_push_changes_uploads_imported_file_attachments_after_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "paper.pdf"
            source_file.write_bytes(b"%PDF-1.4 test")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "sourcePath": str(source_file),
                    "parentItemKey": "PARENT01",
                },
                entity_key="ATTACH01",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            self.assertEqual(len(client.uploads), 1)
            upload = client.uploads[0]
            self.assertEqual(upload["library_id"], "user:123")
            self.assertEqual(upload["item_key"], "ATTACH01")
            self.assertEqual(upload["source_path"], str(source_file))
            self.assertEqual(upload["filename"], "paper.pdf")
            self.assertEqual(upload["content_type"], "application/pdf")
            created_body = client.created[0][1]
            self.assertEqual(created_body["filename"], "paper.pdf")
            self.assertEqual(created_body["contentType"], "application/pdf")
            entity = store.get_entity("user:123", EntityType.ITEM, "ATTACH01")
            self.assertTrue(entity["synced"])
            self.assertEqual(entity["remote_version"], 2)
            self.assertEqual(entity["payload"]["md5"], "uploaded-md5")

    def test_push_changes_preserves_unsynced_attachment_when_upload_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "paper.pdf"
            source_file.write_bytes(b"%PDF-1.4 test")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "sourcePath": str(source_file),
                },
                entity_key="ATTACH01",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()

            def fail_upload(*args, **kwargs):
                raise RuntimeError("upload failed")

            client.upload_attachment_file = fail_upload
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 0)
            self.assertEqual(len(result["failures"]), 1)
            self.assertIn("upload failed", result["failures"][0]["message"])
            self.assertTrue(result["pull_result"]["skipped"])
            entity = store.get_entity("user:123", EntityType.ITEM, "ATTACH01")
            self.assertFalse(entity["synced"])
            self.assertEqual(entity["remote_version"], 1)
            self.assertEqual(entity["payload"]["sourcePath"], str(source_file))

    def test_push_changes_uploads_imported_file_attachments_after_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "paper-v2.pdf"
            source_file.write_bytes(b"%PDF-1.4 updated")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper-v1.pdf",
                    "contentType": "application/pdf",
                    "md5": "old-md5",
                },
                entity_key="ATTACH01",
                version=4,
                remote_version=4,
                synced=True,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper-v2.pdf",
                    "contentType": "application/pdf",
                    "sourcePath": str(source_file),
                    "md5": "old-md5",
                },
                entity_key="ATTACH01",
                change_type=ChangeType.UPDATE,
                base_version=4,
                synced=False,
            )
            client = FakeWebClient()
            client.remote_items["ATTACH01"] = {
                "key": "ATTACH01",
                "version": 4,
                "data": {
                    "key": "ATTACH01",
                    "version": 4,
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper-v1.pdf",
                    "contentType": "application/pdf",
                    "md5": "old-md5",
                },
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            self.assertEqual(client.updated[0][1], "ATTACH01")
            self.assertEqual(client.updated[0][2]["filename"], "paper-v2.pdf")
            upload = client.uploads[0]
            self.assertEqual(upload["item_key"], "ATTACH01")
            self.assertEqual(upload["filename"], "paper-v2.pdf")
            self.assertEqual(upload["previous_md5"], "old-md5")
            entity = store.get_entity("user:123", EntityType.ITEM, "ATTACH01")
            self.assertTrue(entity["synced"])
            self.assertEqual(entity["remote_version"], 6)
            self.assertEqual(entity["payload"]["md5"], "uploaded-md5")

    def test_push_changes_uploads_imported_url_attachments_after_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "paper.html"
            source_file.write_text("<html><body>snapshot</body></html>", encoding="utf-8")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "imported_url",
                    "sourcePath": str(source_file),
                    "url": "https://example.com/article",
                    "title": "Example Snapshot",
                    "contentType": "text/html",
                },
                entity_key="ATTACH99",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            self.assertEqual(len(client.uploads), 1)
            upload = client.uploads[0]
            self.assertEqual(upload["item_key"], "ATTACH99")
            self.assertEqual(upload["source_path"], str(source_file))
            self.assertEqual(upload["filename"], "paper.html")
            self.assertEqual(upload["content_type"], "text/html")
            self.assertEqual(upload["upload_filename"], "ATTACH99.zip")
            self.assertEqual(upload["upload_content_type"], "application/zip")
            self.assertIsInstance(upload["upload_bytes"], bytes)
            created_body = client.created[0][1]
            self.assertEqual(created_body["linkMode"], "imported_url")
            self.assertEqual(created_body["url"], "https://example.com/article")
            entity = store.get_entity("user:123", EntityType.ITEM, "ATTACH99")
            self.assertTrue(entity["synced"])
            self.assertEqual(entity["remote_version"], 2)
            self.assertEqual(entity["payload"]["md5"], "uploaded-md5")

    def test_push_changes_uploads_embedded_image_attachments_after_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "inline.png"
            source_file.write_bytes(b"\x89PNG\r\n")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "embedded_image",
                    "sourcePath": str(source_file),
                    "title": "Inline image",
                    "contentType": "image/png",
                },
                entity_key="EMBED001",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            self.assertEqual(len(client.uploads), 1)
            upload = client.uploads[0]
            self.assertEqual(upload["item_key"], "EMBED001")
            self.assertEqual(upload["filename"], "image.png")
            self.assertEqual(upload["content_type"], "image/png")
            self.assertIsNone(upload["upload_filename"])
            created_body = client.created[0][1]
            self.assertEqual(created_body["linkMode"], "embedded_image")
            self.assertEqual(created_body["filename"], "image.png")
            entity = store.get_entity("user:123", EntityType.ITEM, "EMBED001")
            self.assertTrue(entity["synced"])
            self.assertEqual(entity["remote_version"], 2)
            self.assertEqual(entity["payload"]["md5"], "uploaded-md5")

    def test_push_changes_uploads_directory_snapshot_as_zip_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snapshot"
            snapshot_dir.mkdir()
            (snapshot_dir / "index.html").write_text("<html><img src='image.png'></html>", encoding="utf-8")
            (snapshot_dir / "image.png").write_bytes(b"png-bytes")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "imported_url",
                    "sourcePath": str(snapshot_dir),
                    "filename": "index.html",
                    "url": "https://example.com/snapshot",
                    "title": "Snapshot",
                    "contentType": "text/html",
                },
                entity_key="SNAPZIP1",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            upload = client.uploads[0]
            self.assertEqual(upload["upload_filename"], "SNAPZIP1.zip")
            with zipfile.ZipFile(io.BytesIO(upload["upload_bytes"])) as zf:
                self.assertEqual(sorted(zf.namelist()), ["image.png", "index.html"])

    def test_push_changes_uploads_nested_snapshot_directory_without_explicit_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp) / "snapshot"
            nested_dir = snapshot_dir / "nested"
            nested_dir.mkdir(parents=True)
            (nested_dir / "index.html").write_text("<html><img src='../image.png'></html>", encoding="utf-8")
            (snapshot_dir / "image.png").write_bytes(b"png-bytes")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "imported_url",
                    "sourcePath": str(snapshot_dir),
                    "url": "https://example.com/nested-snapshot",
                    "title": "Nested Snapshot",
                    "contentType": "text/html",
                },
                entity_key="SNAPZIP2",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            upload = client.uploads[0]
            self.assertEqual(upload["filename"], "index.html")
            self.assertEqual(upload["upload_filename"], "SNAPZIP2.zip")
            with zipfile.ZipFile(io.BytesIO(upload["upload_bytes"])) as zf:
                self.assertEqual(sorted(zf.namelist()), ["image.png", "nested/index.html"])

    def test_push_changes_records_attachment_upload_conflict_and_preserves_unsynced_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "paper-v2.pdf"
            source_file.write_bytes(b"%PDF-1.4 updated")
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper-v1.pdf",
                    "contentType": "application/pdf",
                    "md5": "old-md5",
                },
                entity_key="ATTACH01",
                version=4,
                remote_version=4,
                synced=True,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper-v2.pdf",
                    "contentType": "application/pdf",
                    "sourcePath": str(source_file),
                    "md5": "old-md5",
                },
                entity_key="ATTACH01",
                change_type=ChangeType.UPDATE,
                base_version=4,
                synced=False,
            )
            client = FakeWebClient()
            client.remote_items["ATTACH01"] = {
                "key": "ATTACH01",
                "version": 4,
                "data": {
                    "key": "ATTACH01",
                    "version": 4,
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "filename": "paper-v1.pdf",
                    "contentType": "application/pdf",
                    "md5": "old-md5",
                },
            }

            def conflict_upload(*args, **kwargs):
                raise ZoteroApiError(412, "Precondition Failed", "attachment conflict")

            client.upload_attachment_file = conflict_upload
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 0)
            self.assertEqual(len(result["conflicts"]), 1)
            self.assertTrue(result["pull_result"]["skipped"])
            conflict = result["conflicts"][0]
            self.assertEqual(conflict["entity_key"], "ATTACH01")
            self.assertEqual(conflict["remote"]["version"], 5)
            entity = store.get_entity("user:123", EntityType.ITEM, "ATTACH01")
            self.assertFalse(entity["synced"])
            self.assertEqual(entity["remote_version"], 5)
            self.assertEqual(entity["payload"]["sourcePath"], str(source_file))
            self.assertEqual(entity["conflict"]["remote"]["version"], 5)

    def test_push_changes_does_not_upload_linked_url_attachments(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 77},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "linkMode": "linked_url",
                    "url": "https://example.com/article",
                    "title": "Linked URL",
                },
                entity_key="LINKURL1",
                change_type=ChangeType.CREATE,
                synced=False,
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            self.assertEqual(client.uploads, [])
            created_body = client.created[0][1]
            self.assertEqual(created_body["linkMode"], "linked_url")
            self.assertEqual(created_body["url"], "https://example.com/article")
            entity = store.get_entity("user:123", EntityType.ITEM, "LINKURL1")
            self.assertTrue(entity["synced"])

    def test_push_changes_reports_conflict_and_preserves_unsynced_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 80},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Remote title"},
                entity_key="ITEM1234",
                version=81,
                remote_version=81,
                synced=True,
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local title"},
                entity_key="ITEM1234",
                version=82,
                remote_version=81,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=81,
            )
            client = FakeWebClient()
            client.remote_items["ITEM1234"] = {
                "key": "ITEM1234",
                "version": 83,
                "data": {"key": "ITEM1234", "version": 83, "itemType": "book", "title": "Remote changed"},
            }

            def fail_update(*args, **kwargs):
                raise ZoteroApiError(412, "Precondition Failed", "conflict")

            client.update_item = fail_update
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 0)
            self.assertEqual(len(result["conflicts"]), 1)
            self.assertEqual(result["conflicts"][0]["entity_key"], "ITEM1234")
            self.assertEqual(result["conflicts"][0]["remote"]["version"], 83)
            self.assertTrue(result["pull_result"]["skipped"])
            entity = store.get_entity("user:123", EntityType.ITEM, "ITEM1234")
            self.assertFalse(entity["synced"])
            self.assertEqual(entity["payload"]["title"], "Local title")
            self.assertEqual(entity["conflict"]["remote"]["version"], 83)
            self.assertEqual(adapter.list_conflicts("user:123")[0]["entity_key"], "ITEM1234")

    def test_pull_library_records_conflict_instead_of_overwriting_unsynced_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local title"},
                entity_key="ITEM1234",
                version=82,
                remote_version=81,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=81,
            )
            client = FakeWebClient()
            client.remote_items["ITEM1234"] = {
                "key": "ITEM1234",
                "version": 83,
                "data": {"key": "ITEM1234", "version": 83, "itemType": "book", "title": "Remote changed"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.pull_library("user:123")

            self.assertEqual(result["updated"], 1)
            entity = store.get_entity("user:123", EntityType.ITEM, "ITEM1234")
            self.assertFalse(entity["synced"])
            self.assertEqual(entity["payload"]["title"], "Local title")
            self.assertEqual(entity["conflict"]["source"], "pull")
            self.assertEqual(entity["conflict"]["remote"]["version"], 83)

    def test_conflict_rebase_keep_local_makes_entity_pushable_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local title"},
                entity_key="ITEM1234",
                version=82,
                remote_version=81,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=81,
            )
            store.set_entity_conflict(
                "user:123",
                EntityType.ITEM,
                "ITEM1234",
                {
                    "message": "conflict",
                    "remote": {
                        "version": 83,
                        "data": {"key": "ITEM1234", "version": 83, "itemType": "book", "title": "Remote changed"},
                    },
                },
            )
            client = FakeWebClient()
            client.remote_items["ITEM1234"] = {
                "key": "ITEM1234",
                "version": 83,
                "data": {"key": "ITEM1234", "version": 83, "itemType": "book", "title": "Remote changed"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            rebased = adapter.rebase_conflict_keep_local("user:123", EntityType.ITEM, "ITEM1234")
            self.assertIsNone(rebased["conflict"])
            self.assertEqual(rebased["remote_version"], 83)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["pushed"], 1)
            updated_call = client.updated[0]
            self.assertEqual(updated_call[3], 83)
            entity = store.get_entity("user:123", EntityType.ITEM, "ITEM1234")
            self.assertTrue(entity["synced"])

    def test_conflict_accept_remote_replaces_local_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="demo-user", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local title"},
                entity_key="ITEM1234",
                version=82,
                remote_version=81,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=81,
            )
            store.set_entity_conflict(
                "user:123",
                EntityType.ITEM,
                "ITEM1234",
                {
                    "message": "conflict",
                    "remote": {
                        "version": 83,
                        "data": {"key": "ITEM1234", "version": 83, "itemType": "book", "title": "Remote changed"},
                    },
                },
            )
            client = FakeWebClient()
            adapter = CanonicalWebSyncAdapter(store, client)

            accepted = adapter.accept_remote_conflict("user:123", EntityType.ITEM, "ITEM1234")

            self.assertTrue(accepted["synced"])
            self.assertIsNone(accepted["conflict"])
            self.assertEqual(accepted["payload"]["title"], "Remote changed")

    def test_push_changes_treats_delete_conflict_with_missing_remote_as_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 80},
            )
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local title"},
                entity_key="ITEM1234",
                version=82,
                remote_version=81,
                synced=False,
                deleted=True,
                change_type=ChangeType.DELETE,
                base_version=81,
            )
            client = FakeWebClient()

            def fail_delete(*args, **kwargs):
                raise ZoteroApiError(412, "Precondition Failed", "conflict")

            client.delete_item = fail_delete
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["conflicts"], [])
            entity = store.get_entity("user:123", EntityType.ITEM, "ITEM1234")
            self.assertTrue(entity["deleted"])
            self.assertTrue(entity["synced"])

    def test_push_changes_prunes_cached_file_when_attachment_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 80},
            )
            cached_dir = Path(tmp) / "files" / "user_123" / "ATTACH01"
            cached_dir.mkdir(parents=True)
            cached_file = cached_dir / "paper.pdf"
            cached_file.write_bytes(b"cached")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "ATTACH01",
                    "itemType": "attachment",
                    "filename": "paper.pdf",
                    "headlessFilePath": str(cached_file),
                },
                entity_key="ATTACH01",
                version=4,
                remote_version=4,
                synced=True,
            )
            store.delete_entity("user:123", EntityType.ITEM, "ATTACH01")
            client = FakeWebClient()
            client.remote_items["ATTACH01"] = {
                "key": "ATTACH01",
                "version": 4,
                "data": {"key": "ATTACH01", "version": 4, "itemType": "attachment", "filename": "paper.pdf"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["deleted"], 1)
            self.assertFalse(cached_file.exists())

    def test_push_changes_prunes_cached_snapshot_directory_when_attachment_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                "user:123",
                name="demo-user",
                source="remote-sync",
                metadata={"library_version": 80},
            )
            cached_dir = Path(tmp) / "files" / "user_123" / "SNAPZIP1"
            cached_dir.mkdir(parents=True)
            (cached_dir / "index.html").write_text("<html></html>", encoding="utf-8")
            image_file = cached_dir / "image.png"
            image_file.write_bytes(b"cached")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "key": "SNAPZIP1",
                    "itemType": "attachment",
                    "filename": "index.html",
                    "headlessFilePath": str(cached_dir / "index.html"),
                    "headlessFileDir": str(cached_dir),
                },
                entity_key="SNAPZIP1",
                version=4,
                remote_version=4,
                synced=True,
            )
            store.delete_entity("user:123", EntityType.ITEM, "SNAPZIP1")
            client = FakeWebClient()
            client.remote_items["SNAPZIP1"] = {
                "key": "SNAPZIP1",
                "version": 4,
                "data": {"key": "SNAPZIP1", "version": 4, "itemType": "attachment", "filename": "index.html"},
            }
            adapter = CanonicalWebSyncAdapter(store, client)

            result = adapter.push_changes("user:123")

            self.assertEqual(result["deleted"], 1)
            self.assertFalse(image_file.exists())
            self.assertFalse(cached_dir.exists())


if __name__ == "__main__":
    unittest.main()
