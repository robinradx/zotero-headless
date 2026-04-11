import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from zotero_headless.cli import main
from zotero_headless.config import Settings
from zotero_headless.installer_update import UpdatePlan


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
            "zotero_headless.cli.install_plugin_set",
            return_value=[fake_result],
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
            "zotero_headless.cli.install_plugin_set",
            return_value=[fake_result],
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
            "zotero_headless.cli.install_plugin_set",
            return_value=[fake_result],
        ), redirect_stdout(buffer):
            exit_code = main(["plugin", "install", "claude-code"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Plugin installed", output)
        self.assertIn("claude-code", output)
        self.assertIn("/tmp/home/.claude/plugins/zotero-headless-claude-code", output)

    def test_plugin_update_uses_human_output_by_default(self):
        buffer = io.StringIO()
        fake_result = {
            "target": "codex",
            "installed": True,
            "path": "/tmp/home/plugins/zotero-headless-codex",
            "instructions": ["Restart Codex if needed."],
        }
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.install_plugin_set",
            return_value=[fake_result],
        ), redirect_stdout(buffer):
            exit_code = main(["plugin", "update", "codex"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Plugin updated", output)
        self.assertIn("codex", output)
        self.assertIn("/tmp/home/plugins/zotero-headless-codex", output)

    def test_plugin_update_all_uses_human_output_by_default(self):
        buffer = io.StringIO()
        fake_results = [
            {"target": "codex", "installed": True, "path": "/tmp/home/plugins/zotero-headless-codex"},
            {"target": "claude-code", "installed": True, "path": "/tmp/home/.claude/plugins/zotero-headless-claude-code"},
            {"target": "openclaw", "installed": True, "path": "/tmp/home/.openclaw/openclaw.json"},
        ]
        with patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.install_plugin_set",
            return_value=fake_results,
        ), redirect_stdout(buffer):
            exit_code = main(["plugin", "update", "all"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Plugin updated", output)
        self.assertIn("codex", output)
        self.assertIn("claude-code", output)
        self.assertIn("openclaw", output)

    def test_skill_update_all_uses_human_output_by_default(self):
        buffer = io.StringIO()
        fake_results = [
            {"target": "codex", "variant": "general", "installed": True, "path": "/tmp/home/.codex/skills/zotero-headless/SKILL.md"},
            {"target": "claude-code", "variant": "general", "installed": True, "path": "/tmp/home/.claude/skills/zotero-headless/SKILL.md"},
        ]
        with patch("zotero_headless.cli.install_skill_set", return_value=fake_results), redirect_stdout(buffer):
            exit_code = main(["skill", "update", "all"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Skill installed", output)
        self.assertIn("codex", output)
        self.assertIn("claude-code", output)

    def test_update_command_refreshes_installed_integrations_after_success(self):
        buffer = io.StringIO()
        plan = UpdatePlan(method="uv-tool", command=["uv", "tool", "upgrade", "zotero-headless"], auto_supported=True, reason="test")
        update_result = {
            "updated": True,
            "command_succeeded": True,
            "already_current": False,
            "before_version": "0.1.0",
            "after_version": "0.2.0",
            "plan": plan.to_dict(),
            "stdout": "",
            "stderr": "",
        }
        refresh_result = {
            "skills": [{"target": "codex"}],
            "plugins": [{"target": "claude-code"}, {"target": "openclaw"}],
            "skipped_plugins": [],
        }
        with patch("zotero_headless.cli.build_update_plan", return_value=plan), patch(
            "zotero_headless.cli.run_update",
            return_value=update_result,
        ), patch("zotero_headless.cli.load_settings", return_value=Settings()), patch(
            "zotero_headless.cli.refresh_installed_integrations",
            return_value=refresh_result,
        ), redirect_stdout(buffer):
            exit_code = main(["update"])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Updated: yes", output)
        self.assertIn("Version: 0.1.0 -> 0.2.0", output)
        self.assertIn("Post-update refresh:", output)
        self.assertIn("Skills refreshed: 1", output)
        self.assertIn("Plugins refreshed: 2", output)

    def test_update_command_skips_post_refresh_after_failed_update(self):
        buffer = io.StringIO()
        plan = UpdatePlan(method="uv-tool", command=["uv", "tool", "upgrade", "zotero-headless"], auto_supported=True, reason="test")
        update_result = {
            "updated": False,
            "command_succeeded": False,
            "already_current": False,
            "before_version": "0.2.0",
            "after_version": "0.2.0",
            "plan": plan.to_dict(),
            "stdout": "",
            "stderr": "",
            "message": "failed",
        }
        with patch("zotero_headless.cli.build_update_plan", return_value=plan), patch(
            "zotero_headless.cli.run_update",
            return_value=update_result,
        ), patch("zotero_headless.cli.refresh_installed_integrations") as refresh_mock, redirect_stdout(buffer):
            exit_code = main(["update"])

        self.assertEqual(exit_code, 0)
        refresh_mock.assert_not_called()
        output = buffer.getvalue()
        self.assertIn("Updated: no", output)
        self.assertNotIn("Post-update refresh:", output)

    def test_update_command_reports_already_current_when_version_does_not_change(self):
        buffer = io.StringIO()
        plan = UpdatePlan(method="uv-tool", command=["uv", "tool", "upgrade", "zotero-headless"], auto_supported=True, reason="test")
        update_result = {
            "updated": False,
            "command_succeeded": True,
            "already_current": True,
            "before_version": "0.2.0",
            "after_version": "0.2.0",
            "plan": plan.to_dict(),
            "stdout": "",
            "stderr": "Nothing to upgrade",
        }
        with patch("zotero_headless.cli.build_update_plan", return_value=plan), patch(
            "zotero_headless.cli.run_update",
            return_value=update_result,
        ), patch("zotero_headless.cli.refresh_installed_integrations") as refresh_mock, redirect_stdout(buffer):
            exit_code = main(["update"])

        self.assertEqual(exit_code, 0)
        refresh_mock.assert_not_called()
        output = buffer.getvalue()
        self.assertIn("Status: already current", output)
        self.assertIn("Version: 0.2.0 -> 0.2.0", output)

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
