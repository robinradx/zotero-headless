import tempfile
import unittest
from pathlib import Path

from zotero_headless.store import MirrorStore


class MirrorStoreTests(unittest.TestCase):
    def test_upsert_and_get_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MirrorStore(Path(tmp) / "mirror.sqlite")
            store.upsert_library("user:1", "user", "1", "Test", "remote")
            store.upsert_object(
                "user:1",
                "item",
                {
                    "key": "ABCD1234",
                    "version": 2,
                    "data": {"key": "ABCD1234", "version": 2, "title": "Example"},
                },
            )
            item = store.get_object("user:1", "item", "ABCD1234")
            self.assertIsNotNone(item)
            self.assertEqual(item["title"], "Example")
            self.assertEqual(item["payload"]["data"]["title"], "Example")


if __name__ == "__main__":
    unittest.main()
