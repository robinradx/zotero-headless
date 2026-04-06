import tempfile
import unittest
from pathlib import Path

from zotero_headless.core import CanonicalStore
from zotero_headless.library_routing import merged_libraries, prefers_canonical_reads, prefers_canonical_writes
from zotero_headless.store import MirrorStore


class LibraryRoutingTests(unittest.TestCase):
    def test_prefers_canonical_reads_for_headless_remote_and_local_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            canonical.upsert_library("headless:demo", name="Demo", source="headless")
            canonical.upsert_library("user:123", name="Remote Demo", source="remote-sync")
            canonical.upsert_library("local:1", name="Local Demo", source="local-desktop")

            self.assertTrue(prefers_canonical_reads(canonical, "headless:demo"))
            self.assertTrue(prefers_canonical_reads(canonical, "user:123"))
            self.assertTrue(prefers_canonical_reads(canonical, "local:1"))

    def test_prefers_canonical_writes_excludes_local_libraries(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            canonical.upsert_library("user:123", name="Remote Demo", source="remote-sync")
            canonical.upsert_library("local:1", name="Local Demo", source="local-desktop")

            self.assertTrue(prefers_canonical_writes(canonical, "user:123"))
            self.assertFalse(prefers_canonical_writes(canonical, "local:1"))

    def test_merged_libraries_prefers_canonical_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MirrorStore(Path(tmp) / "mirror.sqlite")
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            store.upsert_library(
                library_id="user:123",
                library_type="user",
                remote_id="123",
                name="Mirror User",
                source="remote",
            )
            canonical.upsert_library("user:123", name="Canonical User", source="remote-sync")
            canonical.upsert_library("headless:demo", name="Demo", source="headless")

            libraries = merged_libraries(store, canonical)
            self.assertEqual([library["library_id"] for library in libraries], ["headless:demo", "user:123"])
            self.assertEqual(libraries[1]["name"], "Canonical User")
            self.assertEqual(libraries[1]["source"], "remote-sync")


if __name__ == "__main__":
    unittest.main()
