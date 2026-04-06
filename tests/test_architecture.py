import unittest

from zotero_headless.adapters.local_desktop import LocalWriteStrategy, local_write_strategy_note
from zotero_headless.architecture import current_architecture_state


class ArchitectureTests(unittest.TestCase):
    def test_architecture_state_is_clean_room(self):
        state = current_architecture_state().to_dict()
        self.assertEqual(state["canonical_store"], "clean-room core")
        self.assertEqual(state["runtime"], "minimal daemon host")
        self.assertEqual(state["web_sync"], "first-class adapter")

    def test_local_write_strategy_stays_undecided(self):
        note = local_write_strategy_note(LocalWriteStrategy.UNDECIDED)
        self.assertIn("undecided", note)


if __name__ == "__main__":
    unittest.main()
