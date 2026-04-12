import unittest
import tempfile
from unittest.mock import patch

from zotero_headless.config import Settings
from zotero_headless.raw_cli import build_parser, main


class CliRawParserTests(unittest.TestCase):
    def test_raw_item_create_parses_into_machine_namespace(self):
        args = build_parser().parse_args(["raw", "item", "create", "user:123", '{"itemType":"note"}'])

        self.assertEqual(args.command, "raw")
        self.assertEqual(args.raw_command, "item")
        self.assertEqual(args.item_command, "create")
        self.assertEqual(args.library_id, "user:123")

    def test_global_profile_option_parses_before_command(self):
        args = build_parser().parse_args(["--profile", "alice", "raw", "item", "create", "user:123", '{"itemType":"note"}'])

        self.assertEqual(args.profile, "alice")
        self.assertEqual(args.command, "raw")

    def test_raw_sync_pull_parses_library_argument(self):
        args = build_parser().parse_args(["raw", "sync", "pull", "--library", "user:123"])

        self.assertEqual(args.command, "raw")
        self.assertEqual(args.raw_command, "sync")
        self.assertEqual(args.sync_command, "pull")
        self.assertEqual(args.library, "user:123")

    def test_raw_citations_enable_parses_arguments(self):
        args = build_parser().parse_args(["raw", "citations", "enable", "--format", "csl-json", "--path", "/tmp/citations.json"])

        self.assertEqual(args.command, "raw")
        self.assertEqual(args.raw_command, "citations")
        self.assertEqual(args.citations_command, "enable")
        self.assertEqual(args.format, "csl-json")
        self.assertEqual(args.path, "/tmp/citations.json")

    def test_raw_citations_showpath_parses_arguments(self):
        args = build_parser().parse_args(["raw", "citations", "showpath"])

        self.assertEqual(args.command, "raw")
        self.assertEqual(args.raw_command, "citations")
        self.assertEqual(args.citations_command, "showpath")

    def test_raw_recovery_restore_execute_parses_arguments(self):
        args = build_parser().parse_args(
            [
                "raw",
                "recovery",
                "restore",
                "execute",
                "--snapshot",
                "snap-1",
                "--library",
                "group:123",
                "--push-remote",
                "--confirm",
            ]
        )

        self.assertEqual(args.command, "raw")
        self.assertEqual(args.raw_command, "recovery")
        self.assertEqual(args.recovery_command, "restore")
        self.assertEqual(args.recovery_restore_command, "execute")
        self.assertEqual(args.snapshot_id, "snap-1")
        self.assertEqual(args.library, "group:123")
        self.assertTrue(args.push_remote)
        self.assertTrue(args.confirm)

    def test_plugin_install_accepts_open_claw_alias(self):
        args = build_parser().parse_args(["plugin", "install", "open-claw"])

        self.assertEqual(args.command, "plugin")
        self.assertEqual(args.plugin_command, "install")
        self.assertEqual(args.tool, "open-claw")

    def test_raw_api_serve_uses_settings_daemon_port_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, daemon_port=23119)
            with patch("zotero_headless.raw_cli.load_settings", return_value=settings), patch(
                "zotero_headless.raw_cli.serve_api",
            ) as serve_api_mock:
                exit_code = main(["api", "serve"])

            self.assertEqual(exit_code, 0)
            serve_api_mock.assert_called_once_with(settings, "127.0.0.1", 23119)

    def test_raw_api_serve_loads_named_profile_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(state_dir=tmp, daemon_port=23119)
            with patch("zotero_headless.raw_cli.load_settings", return_value=settings) as load_settings_mock, patch(
                "zotero_headless.raw_cli.serve_api",
            ):
                exit_code = main(["--profile", "alice", "api", "serve"])

            self.assertEqual(exit_code, 0)
            load_settings_mock.assert_called_with(profile="alice")


if __name__ == "__main__":
    unittest.main()
