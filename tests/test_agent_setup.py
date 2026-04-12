import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from zotero_headless.agent_setup import (
    BULK_SKILL_TARGETS,
    CLAUDE_CODE_PLUGIN_NAME,
    CODEX_PLUGIN_NAME,
    SERVER_NAME,
    doctor_report,
    export_skill,
    refresh_installed_integrations,
    install_mcp_setup,
    install_plugin,
    install_plugin_set,
    install_skill,
    install_skill_set,
    installed_plugin_targets,
    installed_skill_targets,
    mcp_stdio_spec,
    remove_mcp_setup,
    skill_target_path,
    setup_list,
)
from zotero_headless.config import Settings


class AgentSetupTests(unittest.TestCase):
    def test_mcp_stdio_spec_pins_selected_profile_in_args(self):
        spec = mcp_stdio_spec(Settings(selected_profile="alice"))

        self.assertEqual(spec["command"], "zotero-headless-mcp")
        self.assertEqual(spec["args"], ["--profile", "alice"])

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

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    @patch(
        "zotero_headless.agent_setup._ensure_runtime_daemon",
        return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
    )
    def test_install_openclaw_setup_runs_plugin_install_and_enable(self, _daemon, _which, run_mock):
        run_mock.side_effect = [
            CompletedProcess(args=["openclaw"], returncode=0, stdout="installed", stderr=""),
            CompletedProcess(args=["openclaw"], returncode=0, stdout="enabled", stderr=""),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = home / "project"
            plugin_dir = cwd / "plugins" / "openclaw-plugin-zotero"
            (plugin_dir / "src").mkdir(parents=True)
            (plugin_dir / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "src" / "index.ts").write_text("export default {};\n", encoding="utf-8")

            result = install_mcp_setup("openclaw", Settings(), cwd=cwd, home=home, scope="user")

            self.assertTrue(result["written"])
            self.assertEqual(result["config"]["plugin_id"], "zotero")
            managed = home / ".openclaw" / "plugins" / "openclaw-plugin-zotero"
            self.assertEqual(Path(result["config"]["plugin_path"]).resolve(), managed.resolve())
            self.assertTrue((managed / "src" / "openclaw.plugin.json").exists())
            self.assertEqual(run_mock.call_args_list[0].args[0][:4], ["/usr/local/bin/openclaw", "plugins", "install", "-l"])
            self.assertEqual(Path(run_mock.call_args_list[0].args[0][4]).resolve(), managed.resolve())
            self.assertEqual(run_mock.call_args_list[1].args[0], ["/usr/local/bin/openclaw", "plugins", "enable", "zotero"])

    @patch("zotero_headless.agent_setup.shutil.which", return_value=None)
    @patch(
        "zotero_headless.agent_setup._ensure_runtime_daemon",
        return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
    )
    def test_install_openclaw_setup_returns_instructions_when_cli_missing(self, _daemon, _which):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = home / "project"
            plugin_dir = cwd / "plugins" / "openclaw-plugin-zotero"
            (plugin_dir / "src").mkdir(parents=True)
            (plugin_dir / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "src" / "index.ts").write_text("export default {};\n", encoding="utf-8")

            result = install_mcp_setup("openclaw", Settings(), cwd=cwd, home=home, scope="user")

            self.assertFalse(result["written"])
            self.assertEqual(result["reason"], "openclaw_not_found")
            self.assertTrue(any(str(home / ".openclaw" / "plugins" / "openclaw-plugin-zotero") in line for line in result["instructions"]))

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    @patch(
        "zotero_headless.agent_setup._ensure_runtime_daemon",
        return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
    )
    def test_install_plugin_for_openclaw_runs_plugin_install_and_enable(self, _daemon, _which, run_mock):
        run_mock.side_effect = [
            CompletedProcess(args=["openclaw"], returncode=0, stdout="installed", stderr=""),
            CompletedProcess(args=["openclaw"], returncode=0, stdout="enabled", stderr=""),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            plugin_dir = cwd / "plugins" / "openclaw-plugin-zotero"
            (plugin_dir / "src").mkdir(parents=True)
            (plugin_dir / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "src" / "index.ts").write_text("export default {};\n", encoding="utf-8")

            result = install_plugin("openclaw", Settings(), cwd=cwd, home=home)

            self.assertTrue(result["installed"])
            managed = home / ".openclaw" / "plugins" / "openclaw-plugin-zotero"
            self.assertEqual(Path(result["config"]["plugin_path"]).resolve(), managed.resolve())
            self.assertTrue((managed / "src" / "openclaw.plugin.json").exists())
            self.assertEqual(run_mock.call_args_list[0].args[0][:4], ["/usr/local/bin/openclaw", "plugins", "install", "-l"])
            self.assertEqual(Path(run_mock.call_args_list[0].args[0][4]).resolve(), managed.resolve())
            self.assertEqual(run_mock.call_args_list[1].args[0], ["/usr/local/bin/openclaw", "plugins", "enable", "zotero"])

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    @patch(
        "zotero_headless.agent_setup._ensure_runtime_daemon",
        return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
    )
    def test_install_plugin_for_openclaw_demotes_benign_gateway_stderr_to_notes(self, _daemon, _which, run_mock):
        benign_stderr = "\n".join(
            [
                "Zotero: daemon unavailable. Start zotero-headless and point the plugin at its HTTP endpoint.",
                "Config overwrite: /root/.openclaw/openclaw.json (sha256 old -> new, backup=/root/.openclaw/openclaw.json.bak)",
                "Zotero: daemon unavailable. Start zotero-headless and point the plugin at its HTTP endpoint.",
            ]
        )
        run_mock.side_effect = [
            CompletedProcess(args=["openclaw"], returncode=0, stdout="installed", stderr=benign_stderr),
            CompletedProcess(args=["openclaw"], returncode=0, stdout="enabled", stderr=benign_stderr),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            plugin_dir = cwd / "plugins" / "openclaw-plugin-zotero"
            (plugin_dir / "src").mkdir(parents=True)
            (plugin_dir / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "src" / "index.ts").write_text("export default {};\n", encoding="utf-8")

            result = install_plugin("openclaw", Settings(), cwd=cwd, home=home)

            self.assertTrue(result["installed"])
            self.assertEqual(result["stderr"], "")
            notes = result["notes"]
            self.assertIn("zotero-headless daemon already running", notes)
            self.assertIn(
                "OpenClaw loaded the plugin, but the zotero-headless daemon was not reachable during install.",
                notes,
            )
            self.assertEqual(
                sum(1 for note in notes if note.startswith("Config overwrite: ")),
                1,
            )

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    @patch(
        "zotero_headless.agent_setup._ensure_runtime_daemon",
        return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
    )
    def test_install_plugin_accepts_open_claw_alias(self, _daemon, _which, run_mock):
        run_mock.side_effect = [
            CompletedProcess(args=["openclaw"], returncode=0, stdout="installed", stderr=""),
            CompletedProcess(args=["openclaw"], returncode=0, stdout="enabled", stderr=""),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            plugin_dir = cwd / "plugins" / "openclaw-plugin-zotero"
            (plugin_dir / "src").mkdir(parents=True)
            (plugin_dir / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "src" / "index.ts").write_text("export default {};\n", encoding="utf-8")

            result = install_plugin("open-claw", Settings(), cwd=cwd, home=home)

            self.assertTrue(result["installed"])
            self.assertEqual(result["target"], "openclaw")

    def test_install_skill_set_for_all_skips_claude_desktop_archive_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = install_skill_set("all", home=home)

            targets = {entry["target"] for entry in result}
            self.assertEqual(targets, set(BULK_SKILL_TARGETS))
            self.assertNotIn("claude-desktop", targets)

    def test_install_plugin_set_for_all_installs_all_supported_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"

            codex = cwd / "plugins" / CODEX_PLUGIN_NAME
            (codex / ".codex-plugin").mkdir(parents=True, exist_ok=True)
            (codex / ".codex-plugin" / "plugin.json").write_text('{"name":"zotero-headless-codex"}\n', encoding="utf-8")
            (codex / ".mcp.json").write_text('{"mcpServers":{}}\n', encoding="utf-8")

            claude = cwd / "plugins" / CLAUDE_CODE_PLUGIN_NAME
            (claude / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            (claude / ".claude-plugin" / "plugin.json").write_text('{"name":"zotero-headless"}\n', encoding="utf-8")
            (claude / ".mcp.json").write_text('{"mcpServers":{}}\n', encoding="utf-8")

            openclaw = cwd / "plugins" / "openclaw-plugin-zotero"
            (openclaw / "src").mkdir(parents=True, exist_ok=True)
            (openclaw / "openclaw.plugin.json").write_text("{}", encoding="utf-8")
            (openclaw / "src" / "index.ts").write_text("export default {};\n", encoding="utf-8")

            with patch("zotero_headless.agent_setup.subprocess.run") as run_mock, patch(
                "zotero_headless.agent_setup.shutil.which",
                return_value="/usr/local/bin/openclaw",
            ), patch(
                "zotero_headless.agent_setup._ensure_runtime_daemon",
                return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
            ):
                run_mock.side_effect = [
                    CompletedProcess(args=["openclaw"], returncode=0, stdout="installed", stderr=""),
                    CompletedProcess(args=["openclaw"], returncode=0, stdout="enabled", stderr=""),
                ]

                result = install_plugin_set("all", Settings(), cwd=cwd, home=home)

            self.assertEqual({entry["target"] for entry in result}, {"codex", "claude-code", "openclaw"})

    def test_openclaw_plugin_package_has_prepare_script_for_source_installs(self):
        package_json = Path(__file__).resolve().parents[1] / "plugins" / "openclaw-plugin-zotero" / "package.json"
        payload = json.loads(package_json.read_text(encoding="utf-8"))

        self.assertEqual(payload["scripts"]["prepare"], "tsc")
        self.assertEqual(payload["main"], "src/index.ts")
        self.assertEqual(payload["openclaw"]["extensions"], ["./src/index.ts"])
        self.assertEqual(payload["openclaw"]["hooks"], ["./src/hooks/gateway-sync.ts"])

    def test_openclaw_plugin_defaults_match_settings_defaults(self):
        root = Path(__file__).resolve().parents[1]
        settings = Settings()
        plugin_roots = [
            root / "plugins" / "openclaw-plugin-zotero",
            root / "src" / "zotero_headless" / "packaged_plugins" / "openclaw-plugin-zotero",
        ]

        for plugin_root in plugin_roots:
            manifest = json.loads((plugin_root / "openclaw.plugin.json").read_text(encoding="utf-8"))
            daemon_props = manifest["configSchema"]["daemon"]["properties"]
            self.assertEqual(daemon_props["host"]["default"], settings.daemon_host)
            self.assertEqual(daemon_props["port"]["default"], settings.daemon_port)

            index_ts = (plugin_root / "src" / "index.ts").read_text(encoding="utf-8")
            self.assertIn(f'host: String(pluginCfg.daemon?.host ?? "{settings.daemon_host}")', index_ts)
            self.assertIn(f"port: Number(pluginCfg.daemon?.port ?? {settings.daemon_port})", index_ts)

    def test_openclaw_plugin_source_does_not_ship_child_process_calls(self):
        root = Path(__file__).resolve().parents[1]
        plugin_roots = [
            root / "plugins" / "openclaw-plugin-zotero",
            root / "src" / "zotero_headless" / "packaged_plugins" / "openclaw-plugin-zotero",
        ]
        for plugin_root in plugin_roots:
            for path in plugin_root.rglob("*.ts"):
                self.assertNotIn("child_process", path.read_text(encoding="utf-8"), str(path))
                self.assertNotIn("@sinclair/typebox", path.read_text(encoding="utf-8"), str(path))

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    def test_installed_plugin_targets_reports_present_targets(self, _which, run_mock):
        run_mock.return_value = CompletedProcess(args=["openclaw"], returncode=0, stdout='{"id":"zotero"}', stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            (home / "plugins" / CODEX_PLUGIN_NAME).mkdir(parents=True, exist_ok=True)
            (home / ".claude" / "plugins" / CLAUDE_CODE_PLUGIN_NAME).mkdir(parents=True, exist_ok=True)

            targets = installed_plugin_targets(Settings(), cwd=cwd, home=home)

            self.assertEqual(targets, ["codex", "claude-code", "openclaw"])

    def test_installed_skill_targets_reports_existing_in_place_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = skill_target_path("codex", home=home)
            openclaw = skill_target_path("openclaw", home=home)
            codex.parent.mkdir(parents=True, exist_ok=True)
            openclaw.parent.mkdir(parents=True, exist_ok=True)
            codex.write_text("x", encoding="utf-8")
            openclaw.write_text("x", encoding="utf-8")

            targets = installed_skill_targets(home=home)

            self.assertEqual(targets, ["openclaw", "codex"])

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    @patch(
        "zotero_headless.agent_setup._ensure_runtime_daemon",
        return_value={"running": True, "started": False, "message": "zotero-headless daemon already running"},
    )
    def test_refresh_installed_integrations_updates_installed_targets_with_packaged_plugin_fallback(self, _daemon, _which, run_mock):
        run_mock.side_effect = [
            CompletedProcess(args=["openclaw"], returncode=0, stdout='{"id":"zotero"}', stderr=""),
            CompletedProcess(args=["openclaw"], returncode=0, stdout="installed", stderr=""),
            CompletedProcess(args=["openclaw"], returncode=0, stdout="enabled", stderr=""),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"

            codex_skill = skill_target_path("codex", home=home)
            codex_skill.parent.mkdir(parents=True, exist_ok=True)
            codex_skill.write_text("old", encoding="utf-8")

            (home / "plugins" / CODEX_PLUGIN_NAME).mkdir(parents=True, exist_ok=True)
            (home / ".claude" / "plugins" / CLAUDE_CODE_PLUGIN_NAME).mkdir(parents=True, exist_ok=True)

            codex_source = cwd / "plugins" / CODEX_PLUGIN_NAME
            (codex_source / ".codex-plugin").mkdir(parents=True, exist_ok=True)
            (codex_source / ".codex-plugin" / "plugin.json").write_text('{"name":"zotero-headless-codex"}\n', encoding="utf-8")
            (codex_source / ".mcp.json").write_text('{"mcpServers":{}}\n', encoding="utf-8")

            refreshed = refresh_installed_integrations(Settings(), cwd=cwd, home=home)

            self.assertEqual([entry["target"] for entry in refreshed["skills"]], ["codex"])
            self.assertEqual([entry["target"] for entry in refreshed["plugins"]], ["codex", "claude-code", "openclaw"])
            self.assertEqual(refreshed["skipped_plugins"], [])

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

    @patch("zotero_headless.agent_setup.subprocess.run")
    @patch("zotero_headless.agent_setup.shutil.which", return_value="/usr/local/bin/openclaw")
    def test_setup_list_reports_openclaw_install_state(self, _which, run_mock):
        run_mock.return_value = CompletedProcess(args=["openclaw"], returncode=0, stdout='{"id":"zotero"}', stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = home / "project"
            cwd.mkdir(parents=True)
            path = home / ".openclaw" / "openclaw.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

            targets = setup_list(Settings(), cwd=cwd, home=home)
            entry = next(item for item in targets if item["target"] == "openclaw")
            self.assertTrue(entry["installed"])

    def test_install_skill_for_codex_writes_skill_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = install_skill("codex", home=home)

            skill_path = home / ".codex" / "skills" / SERVER_NAME / "SKILL.md"
            self.assertEqual(result["path"], str(skill_path))
            self.assertIn("Zotero Headless", skill_path.read_text(encoding="utf-8"))
            self.assertEqual(result["variant"], "general")

    def test_install_plugin_for_codex_copies_bundle_and_updates_marketplace(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            source = cwd / "plugins" / CODEX_PLUGIN_NAME
            (source / ".codex-plugin").mkdir(parents=True, exist_ok=True)
            (source / "skills" / SERVER_NAME).mkdir(parents=True, exist_ok=True)
            (source / "skills" / "zotero-search").mkdir(parents=True, exist_ok=True)
            (source / "agents").mkdir(parents=True, exist_ok=True)
            (source / "scripts").mkdir(parents=True, exist_ok=True)
            (source / ".codex-plugin" / "plugin.json").write_text('{"name":"zotero-headless-codex"}\n', encoding="utf-8")
            (source / ".mcp.json").write_text('{"mcpServers":{}}\n', encoding="utf-8")
            (source / "hooks.json").write_text('{"hooks":{}}\n', encoding="utf-8")
            (source / "skills" / SERVER_NAME / "SKILL.md").write_text("# Rich Core Skill\n", encoding="utf-8")
            (source / "skills" / "zotero-search" / "SKILL.md").write_text("# Search Skill\n", encoding="utf-8")
            (source / "agents" / "library-researcher.md").write_text("research agent\n", encoding="utf-8")
            (source / "scripts" / "session-status.sh").write_text("#!/bin/bash\n", encoding="utf-8")

            result = install_plugin("codex", Settings(api_key="test-key", state_dir=str(home / "state")), cwd=cwd, home=home)

            destination = home / "plugins" / CODEX_PLUGIN_NAME
            self.assertTrue(result["installed"])
            self.assertEqual(Path(result["path"]).resolve(), destination.resolve())
            self.assertTrue((destination / ".codex-plugin" / "plugin.json").exists())
            installed_mcp = json.loads((destination / ".mcp.json").read_text(encoding="utf-8"))
            self.assertIn(SERVER_NAME, installed_mcp["mcpServers"])
            skill_path = destination / "skills" / SERVER_NAME / "SKILL.md"
            self.assertTrue(skill_path.exists())
            self.assertIn("Rich Core Skill", skill_path.read_text(encoding="utf-8"))
            self.assertTrue((destination / "skills" / "zotero-search" / "SKILL.md").exists())
            self.assertTrue((destination / "agents" / "library-researcher.md").exists())
            self.assertTrue((destination / "hooks.json").exists())
            self.assertTrue((destination / "scripts" / "session-status.sh").exists())
            marketplace = json.loads((home / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
            self.assertTrue(any(entry.get("name") == CODEX_PLUGIN_NAME for entry in marketplace["plugins"]))

    def test_install_plugin_for_claude_code_copies_bundle_and_writes_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            source = cwd / "plugins" / CLAUDE_CODE_PLUGIN_NAME
            (source / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            (source / "skills" / SERVER_NAME).mkdir(parents=True, exist_ok=True)
            (source / ".claude-plugin" / "plugin.json").write_text('{"name":"zotero-headless"}\n', encoding="utf-8")
            (source / ".mcp.json").write_text('{"mcpServers":{}}\n', encoding="utf-8")
            (source / "skills" / SERVER_NAME / "SKILL.md").write_text("# Zotero Headless\n", encoding="utf-8")

            result = install_plugin("claude-code", Settings(api_key="test-key", state_dir=str(home / "state")), cwd=cwd, home=home)

            destination = home / ".claude" / "plugins" / CLAUDE_CODE_PLUGIN_NAME
            self.assertTrue(result["installed"])
            self.assertEqual(Path(result["path"]).resolve(), destination.resolve())
            self.assertTrue((destination / ".claude-plugin" / "plugin.json").exists())
            installed_mcp = json.loads((destination / ".mcp.json").read_text(encoding="utf-8"))
            self.assertIn(SERVER_NAME, installed_mcp["mcpServers"])
            skill_path = destination / "skills" / SERVER_NAME / "SKILL.md"
            self.assertTrue(skill_path.exists())

    def test_install_plugin_for_claude_code_uses_packaged_source_when_repo_source_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cwd = Path(tmp) / "repo"
            cwd.mkdir(parents=True)

            result = install_plugin("claude-code", Settings(), cwd=cwd, home=home)

            destination = home / ".claude" / "plugins" / CLAUDE_CODE_PLUGIN_NAME
            self.assertTrue(result["installed"])
            self.assertEqual(Path(result["path"]).resolve(), destination.resolve())
            self.assertTrue((destination / ".claude-plugin" / "plugin.json").exists())

    def test_install_skill_for_openclaw_writes_skill_file_in_openclaw_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)

            result = install_skill("openclaw", home=home)

            skill_path = home / ".openclaw" / "skills" / SERVER_NAME / "SKILL.md"
            self.assertEqual(result["path"], str(skill_path))
            self.assertTrue(skill_path.exists())
            self.assertIn("native OpenClaw Zotero plugin", skill_path.read_text(encoding="utf-8"))

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

    def test_export_skill_for_openclaw_mentions_native_plugin_flow(self):
        exported = export_skill("openclaw")
        self.assertEqual(exported["target"], "openclaw")
        self.assertIn("native OpenClaw Zotero plugin", exported["content"])
        self.assertIn("without a separate MCP bridge", exported["content"])

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
