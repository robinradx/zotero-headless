import tempfile
import unittest
from pathlib import Path

from zotero_headless.config import Settings
from zotero_headless.core import CanonicalStore, ChangeType, EntityType
from zotero_headless.recovery import RecoveryService


class RecoveryServiceTests(unittest.TestCase):
    def test_snapshot_verify_and_full_restore_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, recovery_auto_snapshots=False, citation_export_enabled=True)
            settings.ensure_runtime_dirs()
            canonical = CanonicalStore(settings.resolved_canonical_db())
            canonical.upsert_library("headless:demo", name="Demo")
            canonical.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "Original"},
                entity_key="ITEM1234",
                synced=True,
                version=1,
                remote_version=1,
                change_type=ChangeType.CREATE,
            )
            (settings.resolved_file_cache_dir() / "paper.pdf").write_bytes(b"pdf-v1")
            (settings.resolved_export_dir() / "demo.md").write_text("# Demo\n", encoding="utf-8")
            settings.resolved_citation_export_path().write_text('{"items":[]}', encoding="utf-8")

            recovery = RecoveryService(settings, canonical=canonical)
            snapshot = recovery.create_snapshot(reason="test")
            verification = recovery.verify_snapshot(snapshot["snapshot_id"])
            self.assertTrue(verification["ok"])

            canonical.save_entity(
                "headless:demo",
                EntityType.ITEM,
                {"itemType": "book", "title": "Mutated"},
                entity_key="ITEM1234",
                synced=True,
                version=2,
                remote_version=2,
                change_type=ChangeType.UPDATE,
                base_version=1,
            )
            (settings.resolved_file_cache_dir() / "paper.pdf").write_bytes(b"pdf-v2")
            (settings.resolved_export_dir() / "demo.md").write_text("# Mutated\n", encoding="utf-8")
            settings.resolved_citation_export_path().write_text('{"items":[1]}', encoding="utf-8")

            result = recovery.execute_restore(snapshot_id=snapshot["snapshot_id"], confirm=True)
            self.assertEqual(result["mode"], "full-state")

            restored_item = canonical.get_entity("headless:demo", EntityType.ITEM, "ITEM1234")
            self.assertEqual(restored_item["payload"]["title"], "Original")
            self.assertEqual((settings.resolved_file_cache_dir() / "paper.pdf").read_bytes(), b"pdf-v1")
            self.assertEqual((settings.resolved_export_dir() / "demo.md").read_text(encoding="utf-8"), "# Demo\n")
            self.assertEqual(settings.resolved_citation_export_path().read_text(encoding="utf-8"), '{"items":[]}')

    def test_library_restore_stages_snapshot_payload_back_into_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, recovery_auto_snapshots=False)
            settings.ensure_runtime_dirs()
            canonical = CanonicalStore(settings.resolved_canonical_db())
            canonical.upsert_library("user:123", name="Demo", source="remote-sync", metadata={"library_version": 1})
            canonical.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Original"},
                entity_key="ITEM1234",
                synced=True,
                version=1,
                remote_version=1,
                change_type=ChangeType.CREATE,
            )

            recovery = RecoveryService(settings, canonical=canonical)
            snapshot = recovery.create_snapshot(reason="pre-mutation")

            canonical.save_entity(
                "user:123",
                EntityType.ITEM,
                {"itemType": "book", "title": "Mutated"},
                entity_key="ITEM1234",
                synced=True,
                version=2,
                remote_version=2,
                change_type=ChangeType.UPDATE,
                base_version=1,
            )

            plan = recovery.plan_restore(snapshot_id=snapshot["snapshot_id"], library_id="user:123")
            self.assertEqual(plan["summary"]["update"], 1)

            result = recovery.execute_restore(
                snapshot_id=snapshot["snapshot_id"],
                library_id="user:123",
                confirm=True,
            )
            self.assertEqual(result["mode"], "library")
            runs = recovery.list_restore_runs()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["status"], "completed")
            self.assertEqual(runs[0]["run_id"], result["run_id"])
            restored = canonical.get_entity("user:123", EntityType.ITEM, "ITEM1234")
            self.assertEqual(restored["payload"]["title"], "Original")
            self.assertFalse(restored["synced"])

    def test_filesystem_repository_push_and_pull(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as backup:
            settings = Settings(
                state_dir=tmp,
                recovery_auto_snapshots=False,
                backup_repositories=[{"name": "archive", "type": "filesystem", "path": backup}],
            )
            settings.ensure_runtime_dirs()
            canonical = CanonicalStore(settings.resolved_canonical_db())
            canonical.upsert_library("headless:demo", name="Demo")
            recovery = RecoveryService(settings, canonical=canonical)

            snapshot = recovery.create_snapshot(reason="repository-test")
            recovery.push_snapshot(snapshot["snapshot_id"], repository="archive")
            shutil_target = Path(backup) / snapshot["snapshot_id"] / "manifest.json"
            self.assertTrue(shutil_target.exists())

            snapshot_path = settings.resolved_recovery_snapshot_dir() / snapshot["snapshot_id"]
            for child in snapshot_path.iterdir():
                child.unlink()
            snapshot_path.rmdir()

            pulled = recovery.pull_snapshot(snapshot["snapshot_id"], repository="archive")
            self.assertEqual(pulled["snapshot_id"], snapshot["snapshot_id"])
            self.assertTrue((settings.resolved_recovery_snapshot_dir() / snapshot["snapshot_id"] / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
