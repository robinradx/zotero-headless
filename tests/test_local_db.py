import unittest

from zotero_headless.local_db import validate_readonly_sql


class ReadOnlySqlTests(unittest.TestCase):
    def test_accepts_select(self):
        self.assertEqual(validate_readonly_sql("SELECT * FROM items"), "SELECT * FROM items")

    def test_rejects_write(self):
        with self.assertRaises(ValueError):
            validate_readonly_sql("DELETE FROM items")

    def test_rejects_multiple_statements(self):
        with self.assertRaises(ValueError):
            validate_readonly_sql("SELECT 1; SELECT 2")


if __name__ == "__main__":
    unittest.main()

