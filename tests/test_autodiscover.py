import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zotero_headless.autodiscover import autodiscover_settings
from zotero_headless.config import Settings


class AutodiscoverTests(unittest.TestCase):
    def test_preserves_existing_settings(self):
        settings = Settings(
            data_dir="/tmp/Zotero",
            zotero_bin="/usr/bin/zotero",
            api_key="secret",
            remote_library_ids=["user:123"],
            default_library_id="user:123",
        )
        result = autodiscover_settings(settings)
        self.assertEqual(result.data_dir, "/tmp/Zotero")
        self.assertEqual(result.zotero_bin, "/usr/bin/zotero")
        self.assertTrue(result.api_key_found)
        self.assertEqual(result.selected_remote_library_ids, ["user:123"])
        self.assertEqual(result.default_library_id, "user:123")

    def test_finds_standard_data_dir_and_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "Zotero"
            data_dir.mkdir()
            (data_dir / "zotero.sqlite").write_text("", encoding="utf-8")
            binary_dir = Path(tmp) / "bin"
            binary_dir.mkdir()
            binary = binary_dir / "zotero"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            with patch("zotero_headless.autodiscover._candidate_data_dirs", return_value=[data_dir]), patch(
                "zotero_headless.autodiscover._candidate_binaries", return_value=[binary]
            ):
                result = autodiscover_settings(Settings())
            self.assertEqual(result.data_dir, str(data_dir))
            self.assertEqual(result.zotero_bin, str(binary))


if __name__ == "__main__":
    unittest.main()
