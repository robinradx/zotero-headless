import tempfile
import unittest
from pathlib import Path

from zotero_headless.config import DEFAULT_PROFILE, Settings, load_settings, save_settings, set_default_profile
from zotero_headless.utils import default_state_dir, read_json


class ConfigProfilesTests(unittest.TestCase):
    def test_load_settings_reads_named_profile_from_profiled_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                """
{
  "default_profile": "alice",
  "profiles": {
    "alice": {"api_key": "alice-key"},
    "bob": {"api_key": "bob-key"}
  }
}
                """.strip(),
                encoding="utf-8",
            )

            settings = load_settings(path=path, profile="bob", ensure_dirs=False)

            self.assertEqual(settings.api_key, "bob-key")
            self.assertEqual(settings.selected_profile, "bob")
            self.assertEqual(settings.resolved_state_dir(), default_state_dir("bob"))

    def test_save_settings_creates_profiled_config_for_first_named_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"

            save_settings(Settings(api_key="alice-key", selected_profile="alice"), path=path)

            payload = read_json(path, {})
            self.assertEqual(payload["default_profile"], "alice")
            self.assertEqual(payload["profiles"]["alice"]["api_key"], "alice-key")

    def test_save_settings_migrates_legacy_flat_config_preserving_default_profile_state_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"api_key": "legacy-key"}', encoding="utf-8")

            save_settings(Settings(api_key="alice-key", selected_profile="alice"), path=path)

            payload = read_json(path, {})
            self.assertEqual(payload["default_profile"], DEFAULT_PROFILE)
            self.assertEqual(payload["profiles"][DEFAULT_PROFILE]["api_key"], "legacy-key")
            self.assertEqual(payload["profiles"][DEFAULT_PROFILE]["state_dir"], str(default_state_dir()))
            self.assertEqual(payload["profiles"]["alice"]["api_key"], "alice-key")

    def test_set_default_profile_updates_profiled_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                """
{
  "default_profile": "alice",
  "profiles": {
    "alice": {"api_key": "alice-key"},
    "bob": {"api_key": "bob-key"}
  }
}
                """.strip(),
                encoding="utf-8",
            )

            set_default_profile("bob", path=path)

            payload = read_json(path, {})
            self.assertEqual(payload["default_profile"], "bob")


if __name__ == "__main__":
    unittest.main()
