import tempfile
import unittest
from pathlib import Path

from zotero_headless.capabilities import get_capabilities
from zotero_headless.config import Settings


class CapabilitiesTests(unittest.TestCase):
    def test_capability_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, mirror_db=str(Path(tmp) / "mirror.sqlite"))
            caps = get_capabilities(settings)
            self.assertIn("local_read", caps)
            self.assertIn("local_write", caps)
            self.assertIn("local_desktop_adapter_read", caps)
            self.assertIn("local_desktop_adapter_write", caps)
            self.assertIn("local_desktop_apply_planner", caps)
            self.assertIn("runtime_daemon_read_api_ready", caps)
            self.assertIn("runtime_daemon_write_api_ready", caps)
            self.assertIn("qmd_search", caps)
            self.assertIn("paths", caps)

    def test_desktop_helper_workflow_path_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, mirror_db=str(Path(tmp) / "mirror.sqlite"))
            caps = get_capabilities(settings)
            self.assertTrue(caps["paths"]["desktop_helper_workflow"].endswith("desktop_helper"))


if __name__ == "__main__":
    unittest.main()
