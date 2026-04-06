import tempfile
import unittest
from pathlib import Path

from zotero_headless.config import Settings
from zotero_headless.core import CanonicalStore, EntityType
from zotero_headless.qmd import QmdClient


class StubQmdClient(QmdClient):
    def ensure_collection(self) -> dict:
        return {"created": False, "stdout": ""}


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


if __name__ == "__main__":
    unittest.main()
