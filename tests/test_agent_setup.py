import json
import tempfile
import unittest
from pathlib import Path

from zotero_headless.agent_setup import (
    SERVER_NAME,
    doctor_report,
    export_skill,
    install_mcp_setup,
    install_skill,
    remove_mcp_setup,
    skill_target_path,
    setup_list,
)
from zotero_headless.config import Settings


class AgentSetupTests(unittest.TestCase):
    def test_install_codex_setup_writes_mcp_server_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config = home / ".codex" / "config.toml"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text('model = "gpt-5.4"\n', encoding="utf-8")
            settings = Settings(api_key="test-key", state_dir=str(home / "state"))

            result = install_mcp_setup("codex", settings, home=home, scope="user")

            text = config.read_text(encoding="utf-8")
            self.assertTrue(result["written"])
            self.assertIn(f"[mcp_servers.{SERVER_NAME}]", text)
            self.assertIn('command = "zotero-headless-mcp"', text)
            self.assertIn('ZOTERO_HEADLESS_API_KEY = "test-key"', text)

    def test_install_cursor_project_setup_writes_cursor_mcp_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            settings = Settings(api_key="test-key", state_dir=str(cwd / "state"))

            result = install_mcp_setup("cursor", settings, cwd=cwd, scope="project")

            path = cwd / ".cursor" / "mcp.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(result["path"]).resolve(), path.resolve())
            self.assertIn(SERVER_NAME, payload["mcpServers"])
            self.assertEqual(payload["mcpServers"][SERVER_NAME]["command"], "zotero-headless-mcp")

    def test_install_claude_code_project_setup_writes_project_mcp_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            settings = Settings(state_dir=str(cwd / "state"))

            result = install_mcp_setup("claude-code", settings, cwd=cwd, scope="project")

            path = cwd / ".mcp.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(result["path"]).resolve(), path.resolve())
            self.assertIn(SERVER_NAME, payload["mcpServers"])

    def test_install_claude_desktop_setup_writes_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = Settings(state_dir=str(home / "state"))

            result = install_mcp_setup("claude-desktop", settings, home=home, scope="user")

            path = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(result["path"]).resolve(), path.resolve())
            self.assertIn(SERVER_NAME, payload["mcpServers"])

    def test_install_cline_setup_writes_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = Settings(state_dir=str(home / "state"))

            result = install_mcp_setup("cline", settings, home=home, scope="user")

            path = home / ".cline" / "data" / "settings" / "cline_mcp_settings.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(result["path"]).resolve(), path.resolve())
            self.assertIn(SERVER_NAME, payload["mcpServers"])

    def test_install_antigravity_setup_writes_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = Settings(state_dir=str(home / "state"))

            result = install_mcp_setup("antigravity", settings, home=home, scope="user")

            path = home / ".gemini" / "antigravity" / "mcp_config.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(result["path"]).resolve(), path.resolve())
            self.assertIn(SERVER_NAME, payload["mcpServers"])

    def test_install_windsurf_setup_writes_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            settings = Settings(state_dir=str(home / "state"))

            result = install_mcp_setup("windsurf", settings, home=home, scope="user")

            path = home / ".codeium" / "windsurf" / "mcp_config.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(Path(result["path"]).resolve(), path.resolve())
            self.assertIn(SERVER_NAME, payload["mcpServers"])

    def test_remove_gemini_setup_removes_server_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".gemini" / "settings.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            SERVER_NAME: {"command": "zotero-headless-mcp", "args": []},
                            "Other": {"httpUrl": "https://example.test/mcp"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = remove_mcp_setup("gemini", home=home, scope="user")

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(result["removed"])
            self.assertNotIn(SERVER_NAME, payload["mcpServers"])
            self.assertIn("Other", payload["mcpServers"])

    def test_setup_list_reports_install_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = home / "project"
            cwd.mkdir(parents=True)
            install_mcp_setup("cursor", Settings(), cwd=cwd, scope="project")

            targets = setup_list(Settings(), cwd=cwd, home=home)
            cursor = next(entry for entry in targets if entry["target"] == "cursor")
            self.assertTrue(cursor["installed"])

    def test_setup_list_tolerates_empty_json_config_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            antigravity = home / ".gemini" / "antigravity" / "mcp_config.json"
            antigravity.parent.mkdir(parents=True, exist_ok=True)
            antigravity.write_text("", encoding="utf-8")

            targets = setup_list(Settings(), home=home)
            entry = next(item for item in targets if item["target"] == "antigravity")
            self.assertFalse(entry["installed"])

    def test_install_skill_for_codex_writes_skill_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = install_skill("codex", home=home)

            skill_path = home / ".codex" / "skills" / SERVER_NAME / "SKILL.md"
            self.assertEqual(result["path"], str(skill_path))
            self.assertIn("Zotero Headless", skill_path.read_text(encoding="utf-8"))

    def test_install_skill_for_all_supported_targets_writes_skill_file(self):
        targets = ("cline", "antigravity", "openclaw", "codex", "opencode", "claude-code", "gemini-cli")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for target in targets:
                result = install_skill(target, home=home)
                skill_path = skill_target_path(target, home=home)
                self.assertEqual(result["path"], str(skill_path))
                self.assertTrue(skill_path.exists(), msg=target)
                self.assertIn("Zotero Headless", skill_path.read_text(encoding="utf-8"))

    def test_export_skill_returns_content(self):
        exported = export_skill("codex")
        self.assertEqual(exported["target"], "codex")
        self.assertIn("sync conflicts", exported["content"])

    def test_doctor_report_includes_setup_targets_and_cli_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp)
            report = doctor_report(settings, cwd=Path(tmp), home=Path(tmp))
            self.assertIn("cli", report)
            self.assertIn("setup_targets", report)
            self.assertIn("daemon", report)


if __name__ == "__main__":
    unittest.main()
