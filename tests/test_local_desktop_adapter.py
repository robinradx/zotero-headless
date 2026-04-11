from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from zotero_headless.local_db import LocalZoteroDB
from zotero_headless.adapters.local_desktop import LocalDesktopAdapter
from zotero_headless.core import CanonicalStore, ChangeType, EntityType


class FakeQmdIndexer:
    def __init__(self):
        self.refreshes: list[str] = []

    def refresh_canonical_library(self, canonical, library_id: str):
        self.refreshes.append(library_id)
        return {"enabled": True, "library_id": library_id}


def create_local_zotero_fixture(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = data_dir / "zotero.sqlite"
    conn = sqlite3.connect(sqlite_path)
    conn.executescript(
        """
        CREATE TABLE libraries (
            libraryID INTEGER PRIMARY KEY,
            version INTEGER,
            lastSync INTEGER
        );
        CREATE TABLE collections (
            collectionID INTEGER PRIMARY KEY,
            libraryID INTEGER,
            key TEXT,
            collectionName TEXT,
            version INTEGER,
            parentCollectionID INTEGER
        );
        CREATE TABLE itemTypesCombined (
            itemTypeID INTEGER PRIMARY KEY,
            typeName TEXT
        );
        CREATE TABLE items (
            itemID INTEGER PRIMARY KEY,
            libraryID INTEGER,
            key TEXT,
            version INTEGER,
            synced INTEGER,
            dateAdded TEXT,
            dateModified TEXT,
            itemTypeID INTEGER
        );
        CREATE TABLE itemData (
            itemID INTEGER,
            fieldID INTEGER,
            valueID INTEGER
        );
        CREATE TABLE fieldsCombined (
            fieldID INTEGER PRIMARY KEY,
            fieldName TEXT
        );
        CREATE TABLE itemDataValues (
            valueID INTEGER PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE itemNotes (
            itemID INTEGER PRIMARY KEY,
            parentItemID INTEGER,
            note TEXT,
            title TEXT
        );
        CREATE TABLE itemCreators (
            itemID INTEGER,
            creatorID INTEGER,
            creatorTypeID INTEGER,
            orderIndex INTEGER
        );
        CREATE TABLE creators (
            creatorID INTEGER PRIMARY KEY,
            creatorDataID INTEGER
        );
        CREATE TABLE creatorData (
            creatorDataID INTEGER PRIMARY KEY,
            firstName TEXT,
            lastName TEXT,
            name TEXT
        );
        CREATE TABLE creatorTypes (
            creatorTypeID INTEGER PRIMARY KEY,
            creatorType TEXT
        );
        CREATE TABLE itemTags (
            itemID INTEGER,
            tagID INTEGER,
            type INTEGER
        );
        CREATE TABLE tags (
            tagID INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE collectionItems (
            collectionID INTEGER,
            itemID INTEGER
        );
        CREATE TABLE itemAttachments (
            itemID INTEGER PRIMARY KEY,
            parentItemID INTEGER,
            contentType TEXT,
            path TEXT,
            linkMode INTEGER,
            syncState INTEGER DEFAULT 0,
            storageModTime INTEGER,
            storageHash TEXT
        );
        CREATE TABLE itemAnnotations (
            itemID INTEGER PRIMARY KEY,
            parentItemID INTEGER,
            type INTEGER,
            authorName TEXT,
            text TEXT,
            comment TEXT,
            color TEXT,
            pageLabel TEXT,
            sortIndex TEXT,
            position TEXT,
            isExternal INTEGER DEFAULT 0
        );
        CREATE TABLE deletedItems (
            itemID INTEGER PRIMARY KEY,
            dateDeleted TEXT
        );
        CREATE TABLE deletedCollections (
            collectionID INTEGER PRIMARY KEY,
            dateDeleted TEXT
        );
        """
    )
    conn.execute("INSERT INTO libraries (libraryID, version, lastSync) VALUES (1, 7, 0)")
    conn.execute(
        "INSERT INTO collections (collectionID, libraryID, key, collectionName, version, parentCollectionID) VALUES (1, 1, 'COLL1234', 'Reading', 2, NULL)"
    )
    conn.execute("INSERT INTO itemTypesCombined (itemTypeID, typeName) VALUES (1, 'book')")
    conn.execute("INSERT INTO itemTypesCombined (itemTypeID, typeName) VALUES (2, 'note')")
    conn.execute("INSERT INTO itemTypesCombined (itemTypeID, typeName) VALUES (3, 'attachment')")
    conn.execute("INSERT INTO itemTypesCombined (itemTypeID, typeName) VALUES (4, 'annotation')")
    conn.execute("INSERT INTO creatorTypes (creatorTypeID, creatorType) VALUES (1, 'author')")
    conn.execute(
        "INSERT INTO items (itemID, libraryID, key, version, synced, dateAdded, dateModified, itemTypeID) VALUES (10, 1, 'ITEM1234', 3, 1, '2026-01-01', '2026-01-02', 1)"
    )
    conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (1, 'title')")
    conn.execute("INSERT INTO itemDataValues (valueID, value) VALUES (1, 'Alpha')")
    conn.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (10, 1, 1)")
    conn.execute("INSERT INTO collectionItems (collectionID, itemID) VALUES (1, 10)")
    conn.commit()
    conn.close()
    return sqlite_path


class LocalDesktopAdapterTests(unittest.TestCase):
    def test_import_snapshot_populates_canonical_local_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)

            result = adapter.import_snapshot(str(data_dir))

            self.assertEqual(result["libraries"], 1)
            self.assertEqual(result["collections"], 1)
            self.assertEqual(result["items"], 1)
            library = canonical.get_library("local:1")
            self.assertIsNotNone(library)
            self.assertEqual(library["source"], "local-desktop")
            item = canonical.get_entity("local:1", EntityType.ITEM, "ITEM1234")
            self.assertEqual(item["payload"]["title"], "Alpha")
            self.assertTrue(item["synced"])
            collection = canonical.get_entity("local:1", EntityType.COLLECTION, "COLL1234")
            self.assertEqual(collection["payload"]["name"], "Reading")

    def test_import_snapshot_triggers_qmd_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            qmd_indexer = FakeQmdIndexer()
            adapter = LocalDesktopAdapter(canonical, qmd_indexer=qmd_indexer)

            adapter.import_snapshot(str(data_dir))

            self.assertEqual(qmd_indexer.refreshes, ["local:1"])

    def test_poll_changes_detects_create_update_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            conn = sqlite3.connect(sqlite_path)
            conn.execute("UPDATE items SET version = 4, dateModified = '2026-01-03' WHERE itemID = 10")
            conn.execute("UPDATE itemDataValues SET value = 'Alpha Updated' WHERE valueID = 1")
            conn.execute(
                "INSERT INTO items (itemID, libraryID, key, version, synced, dateAdded, dateModified, itemTypeID) VALUES (11, 1, 'ITEM5678', 1, 1, '2026-01-04', '2026-01-04', 1)"
            )
            conn.execute("INSERT INTO itemDataValues (valueID, value) VALUES (2, 'Beta')")
            conn.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (11, 1, 2)")
            conn.execute("DELETE FROM collectionItems WHERE collectionID = 1")
            conn.execute("DELETE FROM collections WHERE collectionID = 1")
            conn.commit()
            conn.close()

            changes = adapter.poll_changes(str(data_dir))
            index = {(change.entity_type.value, change.entity_key): change for change in changes}

            self.assertEqual(index[("item", "ITEM1234")].change_type, ChangeType.UPDATE)
            self.assertEqual(index[("item", "ITEM1234")].payload["title"], "Alpha Updated")
            self.assertEqual(index[("item", "ITEM5678")].change_type, ChangeType.CREATE)
            self.assertEqual(index[("collection", "COLL1234")].change_type, ChangeType.DELETE)

    def test_plan_pending_writes_classifies_plannable_and_blocked_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {"itemType": "book", "title": "Alpha Planned", "fields": {"title": "Alpha Planned"}},
                entity_key="ITEM1234",
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=3,
            )
            canonical.delete_entity("local:1", EntityType.COLLECTION, "COLL1234")
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Blocked Draft",
                    "fields": {"title": "Blocked Draft"},
                    "attachments": [{"path": "storage:test/file.pdf"}],
                },
                entity_key="ITEM9999",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            index = {(op["entity_type"], op["entity_key"]): op for op in plan["operations"]}

            self.assertEqual(plan["summary"]["total"], 3)
            self.assertEqual(index[("item", "ITEM1234")]["status"], "plannable")
            self.assertEqual(index[("item", "ITEM1234")]["action"], "update-item")
            self.assertEqual(index[("collection", "COLL1234")]["status"], "plannable")
            self.assertEqual(index[("collection", "COLL1234")]["action"], "trash-collection")
            self.assertEqual(index[("item", "ITEM9999")]["status"], "blocked")
            self.assertIn("Attachment writeback is not implemented yet", index[("item", "ITEM9999")]["blocked"])

    def test_plan_pending_writes_accepts_creator_and_tag_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Alpha Planned",
                    "fields": {"title": "Alpha Planned"},
                    "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}],
                    "tags": ["math", {"name": "history", "type": 1}],
                },
                entity_key="ITEM1234",
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=3,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ITEM1234")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["creators"][0]["creatorType"], "author")
            self.assertEqual(op["details"]["tags"][0]["name"], "math")

    def test_plan_pending_writes_accepts_single_note_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "note",
                    "title": "Scratchpad",
                    "note": "<p>Hello from note</p>",
                },
                entity_key="NOTE1234",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "NOTE1234")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["note"]["title"], "Scratchpad")
            self.assertEqual(op["details"]["note"]["note"], "<p>Hello from note</p>")

    def test_plan_pending_writes_accepts_attachment_metadata_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "PDF",
                    "path": "storage:ABCDEF01/file.pdf",
                    "contentType": "application/pdf",
                    "linkMode": 0,
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTM1234",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ATTM1234")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["attachment"]["path"], "storage:ABCDEF01/file.pdf")
            self.assertEqual(op["details"]["attachment"]["parentItemKey"], "ITEM1234")

    def test_plan_pending_writes_accepts_linked_file_attachment_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            linked_file = Path(tmp) / "linked-paper.pdf"
            linked_file.write_bytes(b"%PDF-linked")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Linked PDF",
                    "sourcePath": str(linked_file),
                    "contentType": "application/pdf",
                    "linkMode": "linked_file",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTLINK1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ATTLINK1")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["attachment"]["linkMode"], 2)
            self.assertEqual(op["details"]["attachment"]["sourcePath"], str(linked_file))

    def test_plan_pending_writes_accepts_imported_url_attachment_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            html_file = Path(tmp) / "snapshot.html"
            html_file.write_text("<html><body>snapshot</body></html>", encoding="utf-8")
            sqlite_path = data_dir / "zotero.sqlite"
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (9, 'url')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Snapshot",
                    "sourcePath": str(html_file),
                    "contentType": "text/html",
                    "linkMode": "imported_url",
                    "parentItemKey": "ITEM1234",
                    "url": "https://example.com/snapshot",
                },
                entity_key="ATTIMPU1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ATTIMPU1")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["attachment"]["linkMode"], 1)
            self.assertEqual(op["details"]["attachment"]["sourcePath"], str(html_file))

    def test_plan_pending_writes_accepts_linked_url_attachment_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            sqlite_path = data_dir / "zotero.sqlite"
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (9, 'url')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Remote PDF",
                    "path": "https://example.com/paper.pdf",
                    "contentType": "application/pdf",
                    "linkMode": "linked_url",
                    "parentItemKey": "ITEM1234",
                    "url": "https://example.com/paper.pdf",
                },
                entity_key="ATTURL1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ATTURL1")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["attachment"]["linkMode"], 3)
            self.assertEqual(op["details"]["attachment"]["path"], "https://example.com/paper.pdf")

    def test_plan_pending_writes_blocks_unsupported_attachment_link_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Unsupported Attachment",
                    "contentType": "application/octet-stream",
                    "linkMode": "archive_bundle",
                },
                entity_key="ATTURL1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ATTURL1")

            self.assertEqual(op["status"], "blocked")
            self.assertIn(
                "Invalid attachment linkMode: 'archive_bundle'",
                op["blocked"],
            )

    def test_plan_pending_writes_accepts_embedded_image_attachment_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            image_file = Path(tmp) / "embedded.png"
            image_file.write_bytes(b"\x89PNG\r\n")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Inline image",
                    "sourcePath": str(image_file),
                    "contentType": "image/png",
                    "linkMode": "embedded_image",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTEMB01",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ATTEMB01")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["attachment"]["linkMode"], 4)
            self.assertEqual(op["details"]["attachment"]["sourcePath"], str(image_file))

    def test_plan_pending_writes_accepts_attachment_with_parent_item_created_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            source_file = Path(tmp) / "child.pdf"
            source_file.write_bytes(b"%PDF-child")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Batch Parent",
                    "fields": {"title": "Batch Parent"},
                },
                entity_key="PARENTB1",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Child Attachment",
                    "sourcePath": str(source_file),
                    "contentType": "application/pdf",
                    "linkMode": "imported_file",
                    "parentItemKey": "PARENTB1",
                },
                entity_key="CHILDB01",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "CHILDB01")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["attachment"]["parentItemKey"], "PARENTB1")

    def test_plan_pending_writes_accepts_child_note_with_parent_item_created_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Batch Parent",
                    "fields": {"title": "Batch Parent"},
                },
                entity_key="PARENTN1",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "note",
                    "title": "Child Note",
                    "note": "<p>Child note</p>",
                    "parentItemKey": "PARENTN1",
                },
                entity_key="CHILDN01",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "CHILDN01")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["note"]["parentItemKey"], "PARENTN1")

    def test_plan_pending_writes_accepts_annotation_with_parent_attachment_created_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            source_file = Path(tmp) / "annotated.pdf"
            source_file.write_bytes(b"%PDF-annotated")
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Annotated PDF",
                    "sourcePath": str(source_file),
                    "contentType": "application/pdf",
                    "linkMode": "imported_file",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTPDF01",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "annotation",
                    "parentItemKey": "ATTPDF01",
                    "annotationType": "highlight",
                    "annotationText": "Marked passage",
                    "annotationComment": "Important",
                    "annotationColor": "#ffd400",
                    "annotationPageLabel": "5",
                    "annotationSortIndex": "00001|000001|00000",
                    "annotationPosition": '{"pageIndex":0}',
                },
                entity_key="ANNOP001",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ANNOP001")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["annotation"]["parentItemKey"], "ATTPDF01")
            self.assertEqual(op["details"]["annotation"]["annotationType"], "highlight")

    def test_plan_pending_writes_blocks_annotation_with_non_attachment_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "annotation",
                    "parentItemKey": "ITEM1234",
                    "annotationType": "highlight",
                    "annotationText": "Marked passage",
                },
                entity_key="ANNOBLK1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "ANNOBLK1")

            self.assertEqual(op["status"], "blocked")
            self.assertIn("Annotation parent must be an attachment item: ITEM1234", op["blocked"])

    def test_plan_pending_writes_accepts_child_collection_with_parent_created_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.COLLECTION,
                {"name": "Parent Collection"},
                entity_key="COLLPAR1",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.COLLECTION,
                {"name": "Child Collection", "parentCollectionKey": "COLLPAR1"},
                entity_key="COLLCHD1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            plan = adapter.plan_pending_writes(str(data_dir), library_id="local:1")
            op = next(operation for operation in plan["operations"] if operation["entity_key"] == "COLLCHD1")

            self.assertEqual(op["status"], "plannable")
            self.assertEqual(op["details"]["parentCollectionKey"], "COLLPAR1")

    def test_apply_pending_writes_updates_local_db_and_refreshes_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Alpha Applied",
                    "fields": {"title": "Alpha Applied"},
                    "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}],
                    "tags": ["math", {"name": "history", "type": 1}],
                },
                entity_key="ITEM1234",
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=3,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {"itemType": "book", "title": "Beta", "fields": {"title": "Beta"}},
                entity_key="ITEM5678",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.delete_entity("local:1", EntityType.COLLECTION, "COLL1234")

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 3)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["blocked"], 0)

            db = LocalZoteroDB(sqlite_path)
            updated = db.get_item_detail("ITEM1234")
            created = db.get_item_detail("ITEM5678")
            self.assertEqual(updated["fields"]["title"], "Alpha Applied")
            self.assertEqual(updated["creators"][0]["lastName"], "Lovelace")
            self.assertEqual([tag["name"] for tag in updated["tags"]], ["history", "math"])
            self.assertEqual(created["fields"]["title"], "Beta")
            with closing(sqlite3.connect(sqlite_path)) as conn:
                title_field_rows = conn.execute(
                    "SELECT COUNT(*) FROM itemData WHERE itemID = 10 AND fieldID = 1"
                ).fetchone()[0]
            self.assertEqual(title_field_rows, 1)
            self.assertIsNone(db.get_collection_by_key("COLL1234"))

            with closing(sqlite3.connect(sqlite_path)) as conn:
                deleted_collection = conn.execute(
                    "SELECT COUNT(*) FROM deletedCollections WHERE collectionID = 1"
                ).fetchone()[0]
            self.assertEqual(deleted_collection, 1)

            updated_canonical = canonical.get_entity("local:1", EntityType.ITEM, "ITEM1234")
            created_canonical = canonical.get_entity("local:1", EntityType.ITEM, "ITEM5678")
            deleted_collection_canonical = canonical.get_entity("local:1", EntityType.COLLECTION, "COLL1234")
            self.assertTrue(updated_canonical["synced"])
            self.assertEqual(updated_canonical["payload"]["title"], "Alpha Applied")
            self.assertTrue(created_canonical["synced"])
            self.assertEqual(created_canonical["payload"]["title"], "Beta")
            self.assertTrue(deleted_collection_canonical["deleted"])

    def test_apply_pending_writes_creates_item_in_existing_collection_without_order_index_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Gamma",
                    "fields": {"title": "Gamma"},
                    "collections": ["COLL1234"],
                },
                entity_key="ITEM7777",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ITEM7777")
            self.assertEqual(created["fields"]["title"], "Gamma")
            self.assertEqual([collection["key"] for collection in created["collections"]], ["COLL1234"])

    def test_apply_pending_writes_creates_note_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "note",
                    "title": "Scratchpad",
                    "note": "<p>Hello from note</p>",
                },
                entity_key="NOTE1234",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("NOTE1234")
            self.assertEqual(created["itemType"], "note")
            self.assertEqual(created["notes"][0]["title"], "Scratchpad")
            self.assertEqual(created["notes"][0]["note"], "<p>Hello from note</p>")

    def test_apply_pending_writes_creates_attachment_item_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "PDF",
                    "path": "storage:ABCDEF01/file.pdf",
                    "contentType": "application/pdf",
                    "linkMode": 0,
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTM1234",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTM1234")
            self.assertEqual(created["itemType"], "attachment")
            self.assertEqual(created["attachments"][0]["path"], "storage:ABCDEF01/file.pdf")
            self.assertEqual(created["attachments"][0]["contentType"], "application/pdf")
            self.assertEqual(created["attachments"][0]["parentItemKey"], "ITEM1234")

    def test_apply_pending_writes_copies_imported_attachment_file_into_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            source_file = Path(tmp) / "paper.pdf"
            source_file.write_bytes(b"%PDF-test")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "PDF",
                    "sourcePath": str(source_file),
                    "contentType": "application/pdf",
                    "linkMode": "imported_file",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTMFILE",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            stored_file = data_dir / "storage" / "ATTMFILE" / "paper.pdf"
            self.assertTrue(stored_file.exists())
            self.assertEqual(stored_file.read_bytes(), b"%PDF-test")
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTMFILE")
            self.assertEqual(created["attachments"][0]["path"], "storage:paper.pdf")
            self.assertEqual(created["attachments"][0]["linkMode"], 0)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                row = conn.execute(
                    "SELECT storageHash, storageModTime FROM itemAttachments WHERE itemID = ?",
                    (created["itemID"],),
                ).fetchone()
            self.assertIsNotNone(row[0])
            self.assertIsNotNone(row[1])

    def test_apply_pending_writes_creates_linked_file_attachment_without_copying_into_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            source_file = Path(tmp) / "linked-paper.pdf"
            source_file.write_bytes(b"%PDF-linked")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Linked PDF",
                    "sourcePath": str(source_file),
                    "contentType": "application/pdf",
                    "linkMode": "linked_file",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTLINK2",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            self.assertFalse((data_dir / "storage" / "ATTLINK2").exists())
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTLINK2")
            self.assertEqual(created["attachments"][0]["path"], str(source_file.resolve()))
            self.assertEqual(created["attachments"][0]["linkMode"], 2)

    def test_apply_pending_writes_copies_imported_url_attachment_file_into_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            source_file = Path(tmp) / "snapshot.html"
            source_file.write_text("<html><body>snapshot</body></html>", encoding="utf-8")
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (9, 'url')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Snapshot",
                    "sourcePath": str(source_file),
                    "filename": "index.html",
                    "contentType": "text/html",
                    "linkMode": "imported_url",
                    "parentItemKey": "ITEM1234",
                    "url": "https://example.com/snapshot",
                },
                entity_key="ATTURL2",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            stored_file = data_dir / "storage" / "ATTURL2" / "index.html"
            self.assertTrue(stored_file.exists())
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTURL2")
            self.assertEqual(created["attachments"][0]["path"], "storage:index.html")
            self.assertEqual(created["attachments"][0]["linkMode"], 1)
            self.assertEqual(created["fields"]["url"], "https://example.com/snapshot")

    def test_apply_pending_writes_copies_imported_url_snapshot_directory_into_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            snapshot_dir = Path(tmp) / "snapshot"
            snapshot_dir.mkdir()
            (snapshot_dir / "index.html").write_text("<html><img src='image.png'></html>", encoding="utf-8")
            (snapshot_dir / "image.png").write_bytes(b"png")
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (9, 'url')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Snapshot Bundle",
                    "sourcePath": str(snapshot_dir),
                    "filename": "index.html",
                    "contentType": "text/html",
                    "linkMode": "imported_url",
                    "parentItemKey": "ITEM1234",
                    "url": "https://example.com/bundle",
                },
                entity_key="ATTBUNDL",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            self.assertTrue((data_dir / "storage" / "ATTBUNDL" / "index.html").exists())
            self.assertTrue((data_dir / "storage" / "ATTBUNDL" / "image.png").exists())
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTBUNDL")
            self.assertEqual(created["attachments"][0]["path"], "storage:index.html")
            self.assertEqual(created["attachments"][0]["linkMode"], 1)

    def test_apply_pending_writes_copies_nested_snapshot_directory_without_explicit_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            snapshot_dir = Path(tmp) / "snapshot"
            nested_dir = snapshot_dir / "nested"
            nested_dir.mkdir(parents=True)
            (nested_dir / "index.html").write_text("<html><img src='../image.png'></html>", encoding="utf-8")
            (snapshot_dir / "image.png").write_bytes(b"png")
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (9, 'url')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Nested Snapshot Bundle",
                    "sourcePath": str(snapshot_dir),
                    "contentType": "text/html",
                    "linkMode": "imported_url",
                    "parentItemKey": "ITEM1234",
                    "url": "https://example.com/nested-bundle",
                },
                entity_key="ATTNEST1",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            self.assertTrue((data_dir / "storage" / "ATTNEST1" / "nested" / "index.html").exists())
            self.assertTrue((data_dir / "storage" / "ATTNEST1" / "image.png").exists())
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTNEST1")
            self.assertEqual(created["attachments"][0]["path"], "storage:nested/index.html")
            self.assertEqual(created["attachments"][0]["linkMode"], 1)

    def test_apply_pending_writes_creates_linked_url_attachment_without_copying_into_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (9, 'url')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Remote PDF",
                    "path": "https://example.com/paper.pdf",
                    "contentType": "application/pdf",
                    "linkMode": "linked_url",
                    "parentItemKey": "ITEM1234",
                    "url": "https://example.com/paper.pdf",
                },
                entity_key="ATTLURL2",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            self.assertFalse((data_dir / "storage" / "ATTLURL2").exists())
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTLURL2")
            self.assertEqual(created["attachments"][0]["path"], "https://example.com/paper.pdf")
            self.assertEqual(created["attachments"][0]["linkMode"], 3)
            self.assertEqual(created["fields"]["url"], "https://example.com/paper.pdf")

    def test_apply_pending_writes_copies_embedded_image_attachment_into_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            image_file = Path(tmp) / "embedded.png"
            image_file.write_bytes(b"\x89PNG\r\n")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Inline image",
                    "sourcePath": str(image_file),
                    "contentType": "image/png",
                    "linkMode": "embedded_image",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTEMB02",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            stored_file = data_dir / "storage" / "ATTEMB02" / "image.png"
            self.assertTrue(stored_file.exists())
            db = LocalZoteroDB(sqlite_path)
            created = db.get_item_detail("ATTEMB02")
            self.assertEqual(created["attachments"][0]["path"], "storage:image.png")
            self.assertEqual(created["attachments"][0]["linkMode"], 4)

    def test_apply_pending_writes_creates_parent_item_before_child_attachment_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            source_file = Path(tmp) / "child.pdf"
            source_file.write_bytes(b"%PDF-child")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Batch Parent",
                    "fields": {"title": "Batch Parent"},
                },
                entity_key="PARENTB2",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Child Attachment",
                    "sourcePath": str(source_file),
                    "contentType": "application/pdf",
                    "linkMode": "imported_file",
                    "parentItemKey": "PARENTB2",
                },
                entity_key="CHILDB02",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 2)
            db = LocalZoteroDB(sqlite_path)
            parent = db.get_item_detail("PARENTB2")
            child = db.get_item_detail("CHILDB02")
            self.assertEqual(parent["fields"]["title"], "Batch Parent")
            self.assertEqual(child["attachments"][0]["parentItemKey"], "PARENTB2")
            self.assertTrue((data_dir / "storage" / "CHILDB02" / "child.pdf").exists())

    def test_apply_pending_writes_creates_parent_item_before_child_note_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Batch Parent",
                    "fields": {"title": "Batch Parent"},
                },
                entity_key="PARENTN2",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "note",
                    "title": "Child Note",
                    "note": "<p>Child note</p>",
                    "parentItemKey": "PARENTN2",
                },
                entity_key="CHILDN02",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 2)
            db = LocalZoteroDB(sqlite_path)
            child = db.get_item_detail("CHILDN02")
            self.assertEqual(child["notes"][0]["parentItemKey"], "PARENTN2")
            self.assertEqual(child["notes"][0]["note"], "<p>Child note</p>")

    def test_apply_pending_writes_creates_parent_attachment_before_child_annotation_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            source_file = Path(tmp) / "annotated.pdf"
            source_file.write_bytes(b"%PDF-annotated")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "attachment",
                    "title": "Annotated PDF",
                    "sourcePath": str(source_file),
                    "contentType": "application/pdf",
                    "linkMode": "imported_file",
                    "parentItemKey": "ITEM1234",
                },
                entity_key="ATTPDF02",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "annotation",
                    "parentItemKey": "ATTPDF02",
                    "annotationType": "highlight",
                    "annotationText": "Marked passage",
                    "annotationComment": "Important",
                    "annotationColor": "#ffd400",
                    "annotationPageLabel": "5",
                    "annotationSortIndex": "00001|000001|00000",
                    "annotationPosition": '{"pageIndex":0}',
                },
                entity_key="ANNOP002",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 2)
            db = LocalZoteroDB(sqlite_path)
            parent = db.get_item_detail("ATTPDF02")
            child = db.get_item_detail("ANNOP002")
            self.assertEqual(parent["itemType"], "attachment")
            self.assertEqual(child["itemType"], "annotation")
            self.assertEqual(child["parentItemKey"], "ATTPDF02")
            self.assertEqual(child["annotationType"], "highlight")
            self.assertEqual(child["annotationComment"], "Important")

    def test_import_snapshot_reads_existing_annotation_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute(
                    "INSERT INTO items (itemID, libraryID, key, version, synced, dateAdded, dateModified, itemTypeID) VALUES (11, 1, 'ATTPAR01', 1, 1, '2026-01-03', '2026-01-03', 3)"
                )
                conn.execute(
                    "INSERT INTO itemAttachments (itemID, parentItemID, contentType, path, linkMode) VALUES (11, 10, 'application/pdf', 'storage:paper.pdf', 0)"
                )
                conn.execute(
                    "INSERT INTO items (itemID, libraryID, key, version, synced, dateAdded, dateModified, itemTypeID) VALUES (12, 1, 'ANNOIMP1', 1, 1, '2026-01-03', '2026-01-03', 4)"
                )
                conn.execute(
                    """
                    INSERT INTO itemAnnotations (
                        itemID, parentItemID, type, authorName, text, comment, color, pageLabel, sortIndex, position, isExternal
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        12,
                        11,
                        1,
                        "Robin",
                        "Imported highlight",
                        "Keep this",
                        "#ffd400",
                        "3",
                        "00001|000001|00000",
                        '{"pageIndex":0}',
                        0,
                    ),
                )
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)

            result = adapter.import_snapshot(str(data_dir))

            self.assertEqual(result["items"], 3)
            item = canonical.get_entity("local:1", EntityType.ITEM, "ANNOIMP1")
            self.assertEqual(item["payload"]["itemType"], "annotation")
            self.assertEqual(item["payload"]["parentItemKey"], "ATTPAR01")
            self.assertEqual(item["payload"]["annotationType"], "highlight")
            self.assertEqual(item["payload"]["annotationText"], "Imported highlight")
            self.assertEqual(item["payload"]["annotationComment"], "Keep this")

    def test_apply_pending_writes_updates_existing_annotation_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute(
                    "INSERT INTO items (itemID, libraryID, key, version, synced, dateAdded, dateModified, itemTypeID) VALUES (11, 1, 'ATTPAR02', 1, 1, '2026-01-03', '2026-01-03', 3)"
                )
                conn.execute(
                    "INSERT INTO itemAttachments (itemID, parentItemID, contentType, path, linkMode) VALUES (11, 10, 'application/pdf', 'storage:paper.pdf', 0)"
                )
                conn.execute(
                    "INSERT INTO items (itemID, libraryID, key, version, synced, dateAdded, dateModified, itemTypeID) VALUES (12, 1, 'ANNOUPD1', 1, 1, '2026-01-03', '2026-01-03', 4)"
                )
                conn.execute(
                    """
                    INSERT INTO itemAnnotations (
                        itemID, parentItemID, type, authorName, text, comment, color, pageLabel, sortIndex, position, isExternal
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        12,
                        11,
                        1,
                        "Robin",
                        "Original highlight",
                        "Initial comment",
                        "#ffd400",
                        "3",
                        "00001|000001|00000",
                        '{"pageIndex":0}',
                        0,
                    ),
                )
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "annotation",
                    "parentItemKey": "ATTPAR02",
                    "annotationType": "underline",
                    "annotationText": "Updated highlight",
                    "annotationComment": "Updated comment",
                    "annotationColor": "#00aa00",
                    "annotationPageLabel": "4",
                    "annotationSortIndex": "00002|000001|00000",
                    "annotationPosition": '{"pageIndex":1}',
                },
                entity_key="ANNOUPD1",
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=1,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            db = LocalZoteroDB(sqlite_path)
            updated = db.get_item_detail("ANNOUPD1")
            self.assertEqual(updated["annotationType"], "underline")
            self.assertEqual(updated["annotationText"], "Updated highlight")
            self.assertEqual(updated["annotationComment"], "Updated comment")
            self.assertEqual(updated["parentItemKey"], "ATTPAR02")

    def test_apply_pending_writes_creates_parent_collection_before_child_collection_in_same_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.COLLECTION,
                {"name": "Parent Collection"},
                entity_key="COLLPAR2",
                synced=False,
                change_type=ChangeType.CREATE,
            )
            canonical.save_entity(
                "local:1",
                EntityType.COLLECTION,
                {"name": "Child Collection", "parentCollectionKey": "COLLPAR2"},
                entity_key="COLLCHD2",
                synced=False,
                change_type=ChangeType.CREATE,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 2)
            db = LocalZoteroDB(sqlite_path)
            parent = db.get_collection_by_key("COLLPAR2")
            child = db.get_collection_by_key("COLLCHD2")
            self.assertIsNotNone(parent)
            self.assertIsNotNone(child)
            self.assertEqual(child["parentCollectionID"], parent["collectionID"])

    def test_import_snapshot_detects_pinned_citation_key_from_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (2, 'extra')")
                conn.execute(
                    "INSERT INTO itemDataValues (valueID, value) VALUES (2, 'Citation Key: doe2026alpha\ntex.ids: doe2026alpha, doe2026book')"
                )
                conn.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (10, 2, 2)")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)

            adapter.import_snapshot(str(data_dir))

            item = canonical.get_entity("local:1", EntityType.ITEM, "ITEM1234")
            self.assertEqual(item["payload"]["citationKey"], "doe2026alpha")
            self.assertEqual(item["payload"]["citationAliases"], ["doe2026alpha", "doe2026book"])

    def test_import_snapshot_detects_native_citation_key_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (2, 'citationKey')")
                conn.execute("INSERT INTO itemDataValues (valueID, value) VALUES (2, 'doe2026native')")
                conn.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (10, 2, 2)")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)

            adapter.import_snapshot(str(data_dir))

            item = canonical.get_entity("local:1", EntityType.ITEM, "ITEM1234")
            self.assertEqual(item["payload"]["citationKey"], "doe2026native")
            self.assertEqual(item["payload"]["fields"]["citationKey"], "doe2026native")

    def test_apply_pending_writes_falls_back_to_extra_for_citation_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (2, 'extra')")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Alpha Applied",
                    "citationKey": "doe2026alpha",
                },
                entity_key="ITEM1234",
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=3,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            db = LocalZoteroDB(sqlite_path)
            updated = db.get_item_detail("ITEM1234")
            self.assertEqual(updated["citationKey"], "doe2026alpha")
            self.assertIn("Citation Key: doe2026alpha", updated["fields"]["extra"])

    def test_apply_pending_writes_updates_native_citation_key_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            sqlite_path = create_local_zotero_fixture(data_dir)
            with closing(sqlite3.connect(sqlite_path)) as conn:
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (2, 'citationKey')")
                conn.execute("INSERT INTO fieldsCombined (fieldID, fieldName) VALUES (3, 'extra')")
                conn.execute("INSERT INTO itemDataValues (valueID, value) VALUES (2, 'doe2026seed')")
                conn.execute("INSERT INTO itemData (itemID, fieldID, valueID) VALUES (10, 2, 2)")
                conn.commit()
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            adapter = LocalDesktopAdapter(canonical)
            adapter.import_snapshot(str(data_dir))

            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Alpha Applied",
                    "citationKey": "doe2026native",
                },
                entity_key="ITEM1234",
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=3,
            )

            result = adapter.apply_pending_writes(str(data_dir), library_id="local:1")

            self.assertEqual(result["applied"], 1)
            db = LocalZoteroDB(sqlite_path)
            updated = db.get_item_detail("ITEM1234")
            self.assertEqual(updated["citationKey"], "doe2026native")
            self.assertIn("Citation Key: doe2026native", updated["fields"]["extra"])


if __name__ == "__main__":
    unittest.main()
