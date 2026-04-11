import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from zotero_headless.installer_update import build_update_plan, detect_install_method, run_update


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

    @patch("zotero_headless.installer_update.subprocess.run")
    @patch("zotero_headless.installer_update.current_version")
    def test_run_update_reports_version_change(self, current_version_mock, run_mock):
        plan = build_update_plan(
            prefix="/Users/example/.local/share/uv/tools/zotero-headless",
            executable="/Users/example/.local/share/uv/tools/zotero-headless/bin/python",
            argv0="/Users/example/.local/bin/zhl",
            uv_path="/usr/local/bin/uv",
            pipx_path=None,
        )
        current_version_mock.side_effect = ["0.1.0", "0.2.0"]
        run_mock.return_value = CompletedProcess(args=plan.command, returncode=0, stdout="upgraded", stderr="")

        result = run_update(plan)

        self.assertTrue(result["command_succeeded"])
        self.assertTrue(result["updated"])
        self.assertFalse(result["already_current"])
        self.assertEqual(result["before_version"], "0.1.0")
        self.assertEqual(result["after_version"], "0.2.0")

    @patch("zotero_headless.installer_update.subprocess.run")
    @patch("zotero_headless.installer_update.current_version")
    def test_run_update_reports_already_current_when_version_does_not_change(self, current_version_mock, run_mock):
        plan = build_update_plan(
            prefix="/Users/example/.local/share/uv/tools/zotero-headless",
            executable="/Users/example/.local/share/uv/tools/zotero-headless/bin/python",
            argv0="/Users/example/.local/bin/zhl",
            uv_path="/usr/local/bin/uv",
            pipx_path=None,
        )
        current_version_mock.side_effect = ["0.2.0", "0.2.0"]
        run_mock.return_value = CompletedProcess(args=plan.command, returncode=0, stdout="", stderr="Nothing to upgrade")

        result = run_update(plan)

        self.assertTrue(result["command_succeeded"])
        self.assertFalse(result["updated"])
        self.assertTrue(result["already_current"])
        self.assertEqual(result["before_version"], "0.2.0")
        self.assertEqual(result["after_version"], "0.2.0")


if __name__ == "__main__":
    unittest.main()
