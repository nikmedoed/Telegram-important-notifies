import tempfile
import unittest

import service.db.database as db_module
from service.db.database import Database
from service.ignore_matcher import IgnoreMatcher
from service.utils import sorted_tokens


class IgnoreMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_data_directory = db_module.data_directory
        db_module.data_directory = self._tmp.name
        self.db = Database()
        self.matcher = IgnoreMatcher(self.db)

    def tearDown(self) -> None:
        try:
            self.db._conn.close()
        finally:
            db_module.data_directory = self._old_data_directory
            self._tmp.cleanup()

    @staticmethod
    def prepared(text: str) -> dict:
        token_sorted = sorted_tokens(text)
        return {
            "token_sorted": token_sorted,
            "length": len(token_sorted),
            "raw": text,
        }

    def test_author_scoped_ignore_still_blocks_same_author(self):
        sample = "продаю apple watch series 6 44mm nike хорошее состояние без торга"
        _, entry = self.db.add_blocked_message(sample, author_id=111)
        self.matcher.add_entry(entry)

        self.assertTrue(
            self.matcher.check(
                self.prepared("продаю apple watch series 6 44mm nike хорошее состояние без торга"),
                entry.hash,
                111,
            )
        )

    def test_long_near_duplicate_blocks_even_if_author_differs(self):
        sample = (
            "продаю apple ipad mini 2 64 гб wi-fi+sim space gray\n"
            "аккумулятор хорошо держит\n"
            "хорошее состояние есть потертости\n"
            "заменен тачскрин работает как новый\n"
            "35 000\n"
            "отлично для просмотра фильмов мультиков игр и музыки\n"
            "продаю apple watch series 6 44mm nike\n"
            "аккумулятор 80%\n"
            "хорошее состояние на экране есть царапины\n"
            "40 000 без торга\n"
            "отличные умные часы на каждый день и для тренировок\n"
            "продаю samsung galaxy s8+ duos\n"
            "аккумулятор держит нормально\n"
            "идеальное состояние без царапин\n"
            "45 000\n"
            "отличный телефон как запасной или даже как основной нормально работает\n"
            "ереван\n"
            "пишите отвечаю быстро\n"
            "без обмена"
        )
        variant = sample.replace("35 000", "34 500").replace("аккумулятор 80%", "аккумулятор 79%")

        created, entry = self.db.add_blocked_message(sample, author_id=222)
        self.assertTrue(created)
        self.matcher.add_entry(entry)

        self.assertTrue(
            self.matcher.check(
                self.prepared(variant),
                "not-the-same-hash",
                333,
            )
        )


if __name__ == "__main__":
    unittest.main()
