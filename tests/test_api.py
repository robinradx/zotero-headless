import tempfile
import unittest

from zotero_headless.config import Settings
from zotero_headless.observability import (
    build_metrics_text,
    initialize_runtime_state,
    read_jobs_state,
    read_runtime_state,
    record_http_request,
)


class ApiObservabilityTests(unittest.TestCase):
    def test_observability_state_and_metrics_capture_runtime_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, daemon_host="127.0.0.1", daemon_port=8877)
            settings.ensure_runtime_dirs()
            initialize_runtime_state(
                settings,
                pid=4321,
                host="127.0.0.1",
                port=8877,
                sync_interval_seconds=60,
            )

            record_http_request(
                settings,
                method="GET",
                path="/daemon/runtime",
                status=200,
                duration_ms=12,
                remote_addr="127.0.0.1",
            )
            record_http_request(
                settings,
                method="GET",
                path="/metrics",
                status=200,
                duration_ms=4,
                remote_addr="127.0.0.1",
            )

            runtime_state = read_runtime_state(settings) or {}
            jobs_state = read_jobs_state(settings)
            metrics_payload = build_metrics_text(settings)

            self.assertEqual(runtime_state["pid"], 4321)
            self.assertEqual(runtime_state["request_count"], 2)
            self.assertEqual(runtime_state["last_request"]["path"], "/metrics")
            self.assertTrue(str(runtime_state["jobs_state_path"]).endswith("jobs.json"))
            self.assertTrue(str(runtime_state["events_log_path"]).endswith("events.jsonl"))
            self.assertTrue(jobs_state["background_sync"]["enabled"])
            self.assertEqual(jobs_state["background_sync"]["interval_seconds"], 60)
            self.assertIn("zotero_headless_runtime_running 1", metrics_payload)
            self.assertIn("zotero_headless_http_requests_total 2", metrics_payload)
            self.assertIn("zotero_headless_background_sync_enabled 1", metrics_payload)


if __name__ == "__main__":
    unittest.main()
