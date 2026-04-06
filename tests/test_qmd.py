import tempfile
import unittest
from pathlib import Path

from zotero_headless.config import Settings
from zotero_headless.core import CanonicalStore, EntityType
from zotero_headless.qmd import QmdAutoIndexer, QmdClient


class StubQmdClient(QmdClient):
    def ensure_collection(self) -> dict:
        return {"created": False, "stdout": ""}


class FakeAutoQmdClient:
    def __init__(self):
        self.export_calls: list[tuple[str, str]] = []
        self.embed_calls: list[bool] = []

    def export_from_canonical(self, canonical, library_id: str) -> dict:
        self.export_calls.append(("canonical", library_id))
        return {"exported": 1, "pruned": 0, "export_dir": "/tmp/export", "collection": "test"}

    def export_from_store(self, store, library_id: str) -> dict:
        self.export_calls.append(("mirror", library_id))
        return {"exported": 1, "pruned": 0, "export_dir": "/tmp/export", "collection": "test"}

    def embed(self, force: bool = False) -> str:
        self.embed_calls.append(force)
        return "ok"


class QmdExportTests(unittest.TestCase):
    def test_export_from_canonical_writes_annotation_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                state_dir=tmp,
                export_dir=str(Path(tmp) / "export"),
                canonical_db=str(Path(tmp) / "canonical.sqlite"),
            )
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            canonical.upsert_library("local:1", name="Local Demo", source="local-desktop", editable=False)
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {
                    "itemType": "annotation",
                    "title": "highlight@5: Marked passage",
                    "parentItemKey": "ATTPDF01",
                    "annotationType": "highlight",
                    "annotationText": "Marked passage",
                    "annotationComment": "Important",
                    "annotationColor": "#ffd400",
                    "annotationPageLabel": "5",
                    "citationAliases": ["doe2026alpha", "doe2026book"],
                },
                entity_key="ANNOQMD1",
                synced=True,
                version=1,
            )

            client = StubQmdClient(settings)
            result = client.export_from_canonical(canonical, "local:1")

            self.assertEqual(result["exported"], 1)
            output = (Path(tmp) / "export" / "local-1" / "items" / "ANNOQMD1.md").read_text(encoding="utf-8")
            self.assertIn("## Annotation", output)
            self.assertIn("Type: `highlight`", output)
            self.assertIn("Parent item: `ATTPDF01`", output)
            self.assertIn("### Selected text", output)
            self.assertIn("Marked passage", output)
            self.assertIn("### Comment", output)
            self.assertIn("Important", output)
            self.assertIn("Citation aliases: `doe2026alpha, doe2026book`", output)

    def test_export_from_canonical_prunes_stale_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = Path(tmp) / "export"
            stale = export_dir / "local-1" / "items" / "STALE.md"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("stale", encoding="utf-8")
            settings = Settings(
                state_dir=tmp,
                export_dir=str(export_dir),
                canonical_db=str(Path(tmp) / "canonical.sqlite"),
            )
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            canonical.upsert_library("local:1", name="Local Demo", source="local-desktop", editable=False)
            canonical.save_entity(
                "local:1",
                EntityType.ITEM,
                {"itemType": "book", "title": "Fresh"},
                entity_key="FRESH1",
                synced=True,
                version=1,
            )

            client = StubQmdClient(settings)
            result = client.export_from_canonical(canonical, "local:1")

            self.assertEqual(result["pruned"], 1)
            self.assertFalse(stale.exists())

    def test_auto_indexer_refreshes_and_embeds_for_canonical_library(self):
        indexer = QmdAutoIndexer(Settings())
        indexer.client = FakeAutoQmdClient()
        indexer.enabled = lambda: True

        result = indexer.refresh_canonical_library(object(), "user:123")

        self.assertEqual(indexer.client.export_calls, [("canonical", "user:123")])
        self.assertEqual(indexer.client.embed_calls, [True])
        self.assertTrue(result["enabled"])

    def test_auto_indexer_refreshes_and_embeds_for_mirror_library(self):
        indexer = QmdAutoIndexer(Settings())
        indexer.client = FakeAutoQmdClient()
        indexer.enabled = lambda: True

        result = indexer.refresh_mirror_library(object(), "user:123")

        self.assertEqual(indexer.client.export_calls, [("mirror", "user:123")])
        self.assertEqual(indexer.client.embed_calls, [True])
        self.assertTrue(result["enabled"])


if __name__ == "__main__":
    unittest.main()
