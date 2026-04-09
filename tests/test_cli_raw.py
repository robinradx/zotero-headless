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


if __name__ == "__main__":
    unittest.main()
