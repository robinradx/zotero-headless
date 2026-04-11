import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
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

    def test_plugin_install_uses_human_output_by_default(self):
        buffer = io.StringIO()
        fake_result = {
            "target": "codex",
            "installed": True,
            "path": "/tmp/home/plugins/zotero-headless-codex",
            "instructions": ["Restart Codex if needed."],
        }
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.install_plugin",
            return_value=fake_result,
        ), redirect_stdout(buffer):
            exit_code = main(["plugin", "install", "codex"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Plugin installed", output)
        self.assertIn("codex", output)
        self.assertIn("/tmp/home/plugins/zotero-headless-codex", output)

    def test_plugin_install_openclaw_uses_human_output_by_default(self):
        buffer = io.StringIO()
        fake_result = {
            "target": "openclaw",
            "installed": True,
            "path": "/tmp/home/.openclaw/openclaw.json",
            "instructions": ["Inspect the plugin with openclaw plugins inspect zotero."],
        }
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.install_plugin",
            return_value=fake_result,
        ), redirect_stdout(buffer):
            exit_code = main(["plugin", "install", "openclaw"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Plugin installed", output)
        self.assertIn("openclaw", output)
        self.assertIn("/tmp/home/.openclaw/openclaw.json", output)

    def test_plugin_install_claude_code_uses_human_output_by_default(self):
        buffer = io.StringIO()
        fake_result = {
            "target": "claude-code",
            "installed": True,
            "path": "/tmp/home/.claude/plugins/zotero-headless-claude-code",
            "instructions": ["Restart Claude Code if needed."],
        }
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.install_plugin",
            return_value=fake_result,
        ), redirect_stdout(buffer):
            exit_code = main(["plugin", "install", "claude-code"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Plugin installed", output)
        self.assertIn("claude-code", output)
        self.assertIn("/tmp/home/.claude/plugins/zotero-headless-claude-code", output)

    def test_citations_status_can_emit_json(self):
        buffer = io.StringIO()
        with patch(
            "zotero_headless.cli.load_settings",
            return_value=Settings(state_dir="/tmp/zhl-state", citation_export_enabled=True, citation_export_format="csl-json"),
        ), redirect_stdout(buffer):
            exit_code = main(["--json", "citations", "status"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["format"], "csl-json")
        self.assertTrue(payload["path"].endswith("citations.json"))

    def test_citations_showpath_can_emit_json(self):
        buffer = io.StringIO()
        with patch(
            "zotero_headless.cli.load_settings",
            return_value=Settings(state_dir="/tmp/zhl-state", citation_export_enabled=True, citation_export_format="csl-json"),
        ), redirect_stdout(buffer):
            exit_code = main(["--json", "citations", "showpath"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["format"], "csl-json")
        self.assertEqual(payload["path"], "/tmp/zhl-state/citations.json")

    def test_setup_start_prints_citation_export_path(self):
        buffer = io.StringIO()
        result = SimpleNamespace(
            settings=Settings(state_dir="/tmp/zhl-state", citation_export_enabled=True, citation_export_format="csl-json"),
            autodiscovered={},
            discovered_libraries=[],
            selected_library_ids=[],
        )
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.run_setup_wizard",
            return_value=result,
        ), patch("zotero_headless.cli.save_settings", return_value="/tmp/zhl-state/config.json"), patch(
            "zotero_headless.cli.shutil.which",
            return_value=None,
        ), redirect_stdout(buffer):
            exit_code = main(["setup", "start"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Citations path: /tmp/zhl-state/citations.json", output)
        self.assertIn("Warnings:", output)
        self.assertIn("qmd is not installed.", output)

    def test_recovery_repositories_can_emit_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            settings = Settings(state_dir=tmp, backup_repositories=[{"name": "archive", "type": "filesystem", "path": "/tmp/archive"}])
            with patch("zotero_headless.cli.load_settings", return_value=settings), redirect_stdout(buffer):
                exit_code = main(["--json", "recovery", "repositories"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload[0]["name"], "local")
            self.assertEqual(payload[1]["name"], "archive")


if __name__ == "__main__":
    unittest.main()
