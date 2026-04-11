import unittest

from zotero_headless.raw_cli import build_parser


class CliRawParserTests(unittest.TestCase):
    def test_raw_item_create_parses_into_machine_namespace(self):
        args = build_parser().parse_args(["raw", "item", "create", "user:123", '{"itemType":"note"}'])

        self.assertEqual(args.command, "raw")
        self.assertEqual(args.raw_command, "item")
        self.assertEqual(args.item_command, "create")
        self.assertEqual(args.library_id, "user:123")

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


if __name__ == "__main__":
    unittest.main()
