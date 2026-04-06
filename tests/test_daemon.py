import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zotero_headless.config import Settings
from zotero_headless.daemon import (
    _write_runtime_state,
    build_daemon_command,
    build_runtime_command,
    current_daemon_status,
    vendored_daemon_patch_status,
)
from zotero_headless.observability import default_jobs_state, read_jobs_state


class DaemonTests(unittest.TestCase):
    def test_vendored_patch_detected(self):
        self.assertTrue(vendored_daemon_patch_status())

    def test_build_command_includes_daemon_flag_and_datadir(self):
        settings = Settings(data_dir="/tmp/Zotero", zotero_bin="/Applications/Zotero.app/Contents/MacOS/zotero")
        command = build_daemon_command(settings)
        self.assertEqual(
            command,
            [
                "/Applications/Zotero.app/Contents/MacOS/zotero",
                "-ZoteroDaemon",
                "-datadir",
                "/tmp/Zotero",
            ],
        )

    def test_build_runtime_command_uses_clean_room_daemon_entrypoint(self):
        settings = Settings(state_dir="/tmp/zotero-headless", daemon_host="127.0.0.1", daemon_port=8787)
        command = build_runtime_command(settings, sync_interval_seconds=300)
        self.assertEqual(command[:4], [command[0], "-m", "zotero_headless.daemon", "serve"])
        self.assertIn("--sync-interval", command)
        self.assertIn("300", command)

    def test_status_reports_runtime_as_implemented(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, mirror_db=str(Path(tmp) / "mirror.sqlite"))
            status = current_daemon_status(settings)
            self.assertEqual(status.mode, "clean-room-runtime-ready")
            self.assertTrue(status.vendor_patched)
            self.assertFalse(status.available)
            self.assertTrue(status.runtime_available)
            self.assertFalse(status.runtime_running)
            self.assertFalse(status.runtime_read_api_ready)
            self.assertFalse(status.read_api_ready)

    def test_status_reports_running_runtime_from_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, daemon_host="127.0.0.1", daemon_port=8787)
            _write_runtime_state(
                settings,
                {
                    "pid": 1234,
                    "host": "127.0.0.1",
                    "port": 8787,
                    "started_at": "2026-04-06T12:00:00Z",
                    "sync_interval_seconds": 0,
                    "api_url": "http://127.0.0.1:8787",
                },
            )
            with patch("zotero_headless.daemon._probe_runtime_health", return_value=True):
                status = current_daemon_status(settings)
            self.assertTrue(status.available)
            self.assertTrue(status.runtime_running)
            self.assertEqual(status.runtime_mode, "running")
            self.assertTrue(status.runtime_read_api_ready)
            self.assertFalse(status.write_api_ready)
            self.assertTrue(str(status.runtime_state_path).endswith("runtime.json"))
            self.assertTrue(str(status.jobs_state_path).endswith("jobs.json"))
            self.assertTrue(str(status.events_log_path).endswith("events.jsonl"))

    def test_jobs_state_defaults_to_disabled_background_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp)
            jobs = read_jobs_state(settings)
            self.assertEqual(jobs, default_jobs_state())


if __name__ == "__main__":
    unittest.main()
