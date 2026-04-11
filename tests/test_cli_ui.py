import unittest

from zotero_headless.cli_ui import render_install_result


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


if __name__ == "__main__":
    unittest.main()
