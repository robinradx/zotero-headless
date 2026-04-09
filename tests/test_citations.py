import json
import tempfile
import unittest
from pathlib import Path

from zotero_headless.citations import CitationExportClient
from zotero_headless.config import Settings
from zotero_headless.core import CanonicalStore, EntityType
from zotero_headless.qmd import QmdAutoIndexer


class FakeCitationExportClient:
    def __init__(self):
        self.export_calls: list[str | None] = []

    def enabled(self) -> bool:
        return True

    def export_from_canonical(self, canonical, library_id: str | None = None) -> dict:
        self.export_calls.append(library_id)
        return {"enabled": True, "format": "biblatex", "path": "/tmp/citations.bib", "exported": 1}


class CitationExportTests(unittest.TestCase):
    def test_export_from_canonical_writes_biblatex_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                state_dir=tmp,
                canonical_db=str(Path(tmp) / "canonical.sqlite"),
                citation_export_enabled=True,
                citation_export_format="biblatex",
            )
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            canonical.upsert_library("user:123", name="Demo", source="remote-sync")
            canonical.save_entity(
                "user:123",
                EntityType.ITEM,
                {
                    "itemType": "book",
                    "title": "Example Book",
                    "citationKey": "doe2026book",
                    "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}],
                    "publisher": "Headless Press",
                    "date": "2026-04-09",
                    "url": "https://example.com/book",
                },
                entity_key="ITEM1234",
                synced=True,
                version=1,
            )
            canonical.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "attachment", "title": "PDF"},
                entity_key="ATTACH01",
                synced=True,
                version=1,
            )

            result = CitationExportClient(settings).export_from_canonical(canonical)

            self.assertEqual(result["exported"], 1)
            output = settings.resolved_citation_export_path().read_text(encoding="utf-8")
            self.assertIn("@book{doe2026book,", output)
            self.assertIn("author = {Lovelace, Ada}", output)
            self.assertIn("publisher = {Headless Press}", output)
            self.assertIn("date = {2026-04-09}", output)
            self.assertNotIn("ATTACH01", output)

    def test_export_from_canonical_writes_csl_json_database_and_deduplicates_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                state_dir=tmp,
                canonical_db=str(Path(tmp) / "canonical.sqlite"),
                citation_export_enabled=True,
                citation_export_format="csl-json",
            )
            canonical = CanonicalStore(Path(tmp) / "canonical.sqlite")
            canonical.upsert_library("user:123", name="Demo User", source="remote-sync")
            canonical.upsert_library("group:456", name="Demo Group", source="remote-sync")
            for library_id, title in (("user:123", "First"), ("group:456", "Second")):
                canonical.save_entity(
                    library_id,
                    EntityType.ITEM,
                    {
                        "itemType": "journalArticle",
                        "title": title,
                        "citationKey": "doe2026article",
                        "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}],
                        "publicationTitle": "Journal of Headless Systems",
                        "date": "2026-04",
                        "DOI": "10.1234/example",
                    },
                    entity_key=f"{library_id.replace(':', '')}ITEM1",
                    synced=True,
                    version=1,
                )

            result = CitationExportClient(settings).export_from_canonical(canonical)

            self.assertEqual(result["exported"], 2)
            payload = json.loads(settings.resolved_citation_export_path().read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["id"], "doe2026article")
            self.assertEqual(payload[1]["id"], "doe2026article-2")
            self.assertEqual(payload[0]["type"], "article-journal")
            self.assertEqual(payload[0]["container-title"], "Journal of Headless Systems")
            self.assertEqual(payload[0]["issued"], {"date-parts": [[2026, 4]]})

    def test_status_reflects_current_resolved_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, citation_export_enabled=False, citation_export_format="csl-json")

            status = CitationExportClient(settings).status()

            self.assertFalse(status["enabled"])
            self.assertTrue(status["path"].endswith("citations.json"))


class QmdAutoIndexerCitationTests(unittest.TestCase):
    def test_refresh_canonical_library_exports_citations_even_without_qmd(self):
        settings = Settings(citation_export_enabled=True)
        indexer = QmdAutoIndexer(settings)
        indexer.qmd_enabled = lambda: False
        fake_citations = FakeCitationExportClient()
        indexer.citation_client = fake_citations

        result = indexer.refresh_canonical_library(object(), "user:123")

        self.assertTrue(result["enabled"])
        self.assertEqual(fake_citations.export_calls, [None])
        self.assertEqual(result["citations"]["exported"], 1)
        self.assertEqual(result["qmd"]["reason"], "qmd_missing")


if __name__ == "__main__":
    unittest.main()
