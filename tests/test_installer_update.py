import unittest

from zotero_headless.installer_update import build_update_plan, detect_install_method


class InstallerUpdateTests(unittest.TestCase):
    def test_detects_uv_tool_installation(self):
        method = detect_install_method(
            prefix="/Users/example/.local/share/uv/tools/zotero-headless",
            executable="/Users/example/.local/share/uv/tools/zotero-headless/bin/python",
            argv0="/Users/example/.local/bin/zhl",
        )
        self.assertEqual(method, "uv-tool")

    def test_detects_pipx_installation(self):
        method = detect_install_method(
            prefix="/Users/example/.local/pipx/venvs/zotero-headless",
            executable="/Users/example/.local/pipx/venvs/zotero-headless/bin/python",
            argv0="/Users/example/.local/bin/zhl",
        )
        self.assertEqual(method, "pipx")

    def test_build_update_plan_for_uv_tool(self):
        plan = build_update_plan(
            prefix="/Users/example/.local/share/uv/tools/zotero-headless",
            executable="/Users/example/.local/share/uv/tools/zotero-headless/bin/python",
            argv0="/Users/example/.local/bin/zhl",
            uv_path="/usr/local/bin/uv",
            pipx_path=None,
        )
        self.assertEqual(plan.method, "uv-tool")
        self.assertTrue(plan.auto_supported)
        self.assertEqual(plan.command, ["/usr/local/bin/uv", "tool", "upgrade", "zotero-headless"])

    def test_build_update_plan_for_pipx(self):
        plan = build_update_plan(
            prefix="/Users/example/.local/pipx/venvs/zotero-headless",
            executable="/Users/example/.local/pipx/venvs/zotero-headless/bin/python",
            argv0="/Users/example/.local/bin/zhl",
            uv_path=None,
            pipx_path="/usr/local/bin/pipx",
        )
        self.assertEqual(plan.method, "pipx")
        self.assertTrue(plan.auto_supported)
        self.assertEqual(plan.command, ["/usr/local/bin/pipx", "upgrade", "zotero-headless"])

    def test_build_update_plan_for_virtualenv(self):
        plan = build_update_plan(
            prefix="/tmp/venv",
            executable="/tmp/venv/bin/python",
            argv0="/tmp/venv/bin/zhl",
            base_prefix="/usr/local",
            virtual_env="/tmp/venv",
            uv_path=None,
            pipx_path=None,
        )
        self.assertEqual(plan.method, "venv-pip")
        self.assertTrue(plan.auto_supported)
        self.assertEqual(plan.command, ["/tmp/venv/bin/python", "-m", "pip", "install", "--upgrade", "zotero-headless"])

    def test_build_update_plan_for_unknown_install(self):
        plan = build_update_plan(
            prefix="/usr/local",
            executable="/usr/local/bin/python3",
            argv0="/usr/local/bin/zhl",
            base_prefix="/usr/local",
            virtual_env="",
            uv_path=None,
            pipx_path=None,
        )
        self.assertEqual(plan.method, "unknown")
        self.assertFalse(plan.auto_supported)
        self.assertEqual(plan.command, [])


if __name__ == "__main__":
    unittest.main()
