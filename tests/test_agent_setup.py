import json
import tempfile
import unittest
import zipfile
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
            self.assertEqual(result["variant"], "general")

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

    def test_install_skill_for_claude_desktop_writes_archive_to_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = install_skill("claude-desktop", home=home)

            archive_path = home / "Desktop" / f"{SERVER_NAME}-claude-desktop-skill.zip"
            self.assertEqual(result["path"], str(archive_path))
            self.assertEqual(result["format"], "zip")
            self.assertEqual(result["variant"], "general")
            self.assertTrue(archive_path.exists())
            self.assertTrue(any("Claude Desktop" in line for line in result["instructions"]))
            with zipfile.ZipFile(archive_path) as zf:
                self.assertEqual(set(zf.namelist()), {"SKILL.md", "metadata.json"})
                self.assertIn("Zotero Headless", zf.read("SKILL.md").decode("utf-8"))
                metadata = json.loads(zf.read("metadata.json").decode("utf-8"))
                self.assertEqual(metadata["slug"], SERVER_NAME)

    def test_install_daemon_variant_for_claude_desktop_uses_distinct_archive_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = install_skill("claude-desktop", home=home, variant="daemon")

            archive_path = home / "Desktop" / f"{SERVER_NAME}-claude-desktop-daemon-skill.zip"
            self.assertEqual(result["path"], str(archive_path))
            self.assertEqual(result["variant"], "daemon")
            self.assertTrue(archive_path.exists())
            with zipfile.ZipFile(archive_path) as zf:
                body = zf.read("SKILL.md").decode("utf-8")
                self.assertIn("Active skill variant: `daemon`", body)
                self.assertIn("Assume a true headless deployment", body)

    def test_export_skill_returns_content(self):
        exported = export_skill("codex")
        self.assertEqual(exported["target"], "codex")
        self.assertEqual(exported["variant"], "general")
        self.assertIn("sync conflicts", exported["content"])
        self.assertIn("Routing policy:", exported["content"])
        self.assertIn("- Use qmd semantic search for:", exported["content"])
        self.assertIn("Prefer the HTTP API over MCP", exported["content"])
        self.assertIn("Do not use qmd semantic search when the task already names exact objects", exported["content"])
        self.assertIn("automatically maintained from dataset changes", exported["content"])
        self.assertNotIn("Use `qmd export` before qmd queries", exported["content"])
        self.assertIn("Decision table:", exported["content"])
        self.assertIn("Common recipes:", exported["content"])
        self.assertIn("Anti-patterns:", exported["content"])
        self.assertIn("This client is comfortable with MCP tool use", exported["content"])
        self.assertIn("Do not use mirror sync paths unless the task explicitly requires mirror-backed compatibility behavior.", exported["content"])
        self.assertIn("Active skill variant: `general`", exported["content"])
        self.assertIn("Treat the local desktop adapter as an interoperability layer", exported["content"])

    def test_export_daemon_variant_emphasizes_headless_constraints(self):
        exported = export_skill("codex", variant="daemon")
        self.assertEqual(exported["target"], "codex")
        self.assertEqual(exported["variant"], "daemon")
        self.assertIn("Active skill variant: `daemon`", exported["content"])
        self.assertIn("Assume a true headless deployment", exported["content"])
        self.assertIn("Prefer the daemon HTTP API as the primary integration surface", exported["content"])
        self.assertIn("Daemon observability:", exported["content"])

    def test_export_skill_for_claude_desktop_describes_archive(self):
        exported = export_skill("claude-desktop")
        self.assertEqual(exported["target"], "claude-desktop")
        self.assertEqual(exported["variant"], "general")
        self.assertEqual(exported["format"], "zip")
        self.assertEqual(exported["archive_contents"], ["SKILL.md", "metadata.json"])
        self.assertIn("- Use qmd semantic search for:", exported["content"])
        self.assertIn("This skill is uploaded manually into Claude Desktop or claude.ai", exported["content"])
        self.assertIn("Prefer the HTTP API when you can reach a running `zotero-headless` daemon directly.", exported["content"])

    def test_doctor_report_includes_setup_targets_and_cli_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp)
            report = doctor_report(settings, cwd=Path(tmp), home=Path(tmp))
            self.assertIn("cli", report)
            self.assertIn("setup_targets", report)
            self.assertIn("daemon", report)
            self.assertTrue(all("variants" in entry for entry in report["skill_targets"]))


if __name__ == "__main__":
    unittest.main()
