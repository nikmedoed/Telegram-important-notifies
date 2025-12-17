import tempfile
import unittest

import service.db.database as db_module
from service.db.database import Database


class BlockedMessagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_data_directory = db_module.data_directory
        db_module.data_directory = self._tmp.name
        self.db = Database()

    def tearDown(self) -> None:
        try:
            self.db._conn.close()
        finally:
            db_module.data_directory = self._old_data_directory
            self._tmp.cleanup()

    def test_multiple_samples_per_author_allowed(self):
        created1, entry1 = self.db.add_blocked_message("sample one", author_id=123)
        created2, entry2 = self.db.add_blocked_message("sample two", author_id=123)

        self.assertTrue(created1)
        self.assertTrue(created2)
        self.assertNotEqual(entry1.id, entry2.id)

        entries = [e for e in self.db.get_blocked_entries() if e.author_id == 123]
        self.assertEqual(len(entries), 2)

    def test_duplicate_sample_for_author_is_deduped(self):
        created1, entry1 = self.db.add_blocked_message("same text", author_id=456)
        created2, entry2 = self.db.add_blocked_message("same text", author_id=456)

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(entry1.id, entry2.id)


if __name__ == "__main__":
    unittest.main()

