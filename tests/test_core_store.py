import tempfile
import unittest
from pathlib import Path

from zotero_headless.core import CanonicalStore, ChangeType, EntityType


class CanonicalStoreTests(unittest.TestCase):
    def test_create_library_and_item_records_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("headless:demo", name="Demo")
            item = store.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "Example"},
                entity_key="ABCD1234",
                change_type=ChangeType.CREATE,
            )

            self.assertEqual(item["entity_key"], "ABCD1234")
            self.assertEqual(item["payload"]["title"], "Example")
            changes = store.list_changes(library_id="headless:demo")
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["change_type"], "create")

    def test_update_increments_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("headless:demo", name="Demo")
            store.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "First"},
                entity_key="ABCD1234",
                change_type=ChangeType.CREATE,
            )
            item = store.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "Second"},
                entity_key="ABCD1234",
                change_type=ChangeType.UPDATE,
            )

            self.assertEqual(item["version"], 1)
            self.assertEqual(item["payload"]["title"], "Second")

    def test_list_entities_supports_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("headless:demo", name="Demo")
            store.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "Alpha"},
                entity_key="AAAA1111",
                change_type=ChangeType.CREATE,
            )
            store.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "Beta"},
                entity_key="BBBB2222",
                change_type=ChangeType.CREATE,
            )

            items = store.list_entities("headless:demo", EntityType.ITEM, query="Alpha")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["entity_key"], "AAAA1111")

    def test_conflict_state_can_be_recorded_rebased_and_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library("user:123", name="Demo", source="remote-sync")
            store.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Local"},
                entity_key="ITEM1234",
                version=2,
                remote_version=1,
                synced=False,
                change_type=ChangeType.UPDATE,
                base_version=1,
            )

            store.set_entity_conflict(
                "user:123",
                EntityType.ITEM,
                "ITEM1234",
                {
                    "message": "Precondition Failed",
                    "remote": {
                        "version": 3,
                        "data": {"key": "ITEM1234", "version": 3, "itemType": "book", "title": "Remote"},
                    },
                },
            )
            conflicted = store.get_entity("user:123", EntityType.ITEM, "ITEM1234")
            self.assertEqual(conflicted["conflict"]["remote"]["version"], 3)
            self.assertEqual(store.list_unsynced_entities("user:123", EntityType.ITEM), [])
            self.assertEqual(len(store.list_conflicted_entities("user:123")), 1)

            rebased = store.rebase_conflict_keep_local("user:123", EntityType.ITEM, "ITEM1234")
            self.assertIsNone(rebased["conflict"])
            self.assertEqual(rebased["remote_version"], 3)
            self.assertEqual(len(store.list_unsynced_entities("user:123", EntityType.ITEM)), 1)

            store.set_entity_conflict(
                "user:123",
                EntityType.ITEM,
                "ITEM1234",
                {
                    "message": "Precondition Failed",
                    "remote": {
                        "version": 4,
                        "data": {"key": "ITEM1234", "version": 4, "itemType": "book", "title": "Remote Wins"},
                    },
                },
            )
            accepted = store.accept_remote_conflict("user:123", EntityType.ITEM, "ITEM1234")
            self.assertTrue(accepted["synced"])
            self.assertIsNone(accepted["conflict"])
            self.assertEqual(accepted["payload"]["title"], "Remote Wins")


if __name__ == "__main__":
    unittest.main()
