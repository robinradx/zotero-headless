import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from zotero_headless.cli import main
from zotero_headless.config import Settings


class CliOutputTests(unittest.TestCase):
    def test_version_command_uses_human_output_by_default(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["version"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Install method:", output)
        self.assertNotIn('"package"', output)

    def test_version_command_can_emit_json(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["--json", "version"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["package"], "zotero-headless")
        self.assertIn("version", payload)

    def test_setup_list_uses_human_output_by_default(self):
        fake_targets = [
            {
                "target": "codex",
                "path": "/tmp/codex-config.toml",
                "installed": True,
                "scope": "user",
            }
        ]
        buffer = io.StringIO()
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.setup_list",
            return_value=fake_targets,
        ), redirect_stdout(buffer):
            exit_code = main(["setup", "list"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("MCP client setup targets", output)
        self.assertIn("codex", output)
        self.assertIn("/tmp/codex-config.toml", output)


if __name__ == "__main__":
    unittest.main()
