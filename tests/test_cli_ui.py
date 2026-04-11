import unittest

from zotero_headless.cli_ui import render_install_result, render_update_result_rich, render_version_payload_rich


class CliUiTests(unittest.TestCase):
    def test_render_install_result_uses_notes_label_for_optional_hints(self):
        rendered = render_install_result(
            {
                "target": "openclaw",
                "installed": True,
                "path": "/tmp/home/.openclaw/openclaw.json",
                "notes": [
                    "Already ran `openclaw plugins install -l /tmp/plugin`.",
                    "Already ran `openclaw plugins enable zotero`.",
                ],
            },
            heading="Plugin installed",
        )

        self.assertIn("Notes:", rendered)
        self.assertNotIn("Next steps:", rendered)

    def test_render_install_result_does_not_label_failed_plugin_as_installed(self):
        rendered = render_install_result(
            {
                "target": "openclaw",
                "installed": False,
                "written": False,
                "path": "/tmp/home/.openclaw/openclaw.json",
                "reason": "openclaw_not_found",
                "instructions": ["Run `openclaw plugins install -l /tmp/plugin`."],
            },
            heading="Plugin installed",
        )

        self.assertIn("Plugin not installed", rendered)
        self.assertIn("Reason: The `openclaw` CLI is not available on PATH.", rendered)

    def test_render_update_result_rich_includes_version_transition(self):
        try:
            from rich.console import Console
        except ImportError:
            self.skipTest("rich is not installed in this environment")
        console = Console(record=True, width=120)
        console.print(
            render_update_result_rich(
                {
                    "updated": False,
                    "command_succeeded": True,
                    "already_current": True,
                    "before_version": "0.2.0",
                    "after_version": "0.2.0",
                    "duration_seconds": 0.4,
                    "plan": {"method": "uv-tool", "command": ["uv", "tool", "upgrade", "zotero-headless"]},
                    "stderr": "Nothing to upgrade",
                }
            )
        )
        rendered = console.export_text()
        self.assertIn("already current", rendered)
        self.assertIn("0.2.0 -> 0.2.0", rendered)

    def test_render_version_payload_rich_includes_aliases(self):
        try:
            from rich.console import Console
        except ImportError:
            self.skipTest("rich is not installed in this environment")
        console = Console(record=True, width=120)
        console.print(
            render_version_payload_rich(
                {
                    "package": "zotero-headless",
                    "version": "0.2.0",
                    "install_method": "uv-tool",
                    "executable": "zhl",
                    "python": "/usr/bin/python3",
                    "aliases_found": ["zhl", "zotero-headless"],
                }
            )
        )
        rendered = console.export_text()
        self.assertIn("zotero-headless", rendered)
        self.assertIn("zhl, zotero-headless", rendered)


if __name__ == "__main__":
    unittest.main()
