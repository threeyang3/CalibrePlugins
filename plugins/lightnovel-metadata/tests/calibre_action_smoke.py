"""Run with calibre-debug -e after installing both packages in a test profile."""

import unittest
from collections import Counter
from dataclasses import replace
from queue import Queue
from threading import Event

from calibre_plugins.lightnovel_library.action import Target, edition_conflict, fetch_books, volume_marks
from calibre_plugins.lightnovel_metadata.models import Record


class Source:
    def __init__(self):
        self.records = []
        self.calls = []

    def identify_books(self, _log, _abort, *, identifiers):
        self.calls.append(identifiers)
        return self.records

    def cover_for_book(self, _log, _abort, record):
        self.calls.append(record.cover)
        return b'fixture-cover'


class CompanionTest(unittest.TestCase):
    def setUp(self):
        self.code = '9789578531222'
        self.target = Target(23, '妹妹人生〈下〉', ('入間人間',), {'isbn': self.code}, None, 1.0, frozenset(), False)
        self.official = Record('books_tw', '0010000123', '妹妹人生（下）', isbn=self.code,
                               language='zho', cover='fixture-url')
        self.source = Source()

    def fetch(self, count=1, target=None):
        return fetch_books(self.source, [target or self.target], Counter({self.code: count}),
                           abort=Event(), log=None, notifications=Queue())

    def test_duplicate_isbn_does_not_trigger_lookup(self):
        matches, skipped = self.fetch(count=2)
        self.assertFalse(matches)
        self.assertIn('多本', skipped[0][1])
        self.assertFalse(self.source.calls)

    def test_exact_isbn_still_requires_consistent_edition(self):
        wrong = replace(self.official, title='妹妹人生（上）')
        self.source.records = [wrong]
        matches, skipped = self.fetch()
        self.assertFalse(matches)
        self.assertIn('卷次', skipped[0][1])

        self.source.records = [self.official, wrong]
        matches, skipped = self.fetch()
        self.assertFalse(matches)
        self.assertIn('冲突', skipped[0][1])

    def test_cover_fetched_only_for_empty_slot(self):
        self.source.records = [self.official]
        matches, skipped = self.fetch()
        self.assertFalse(skipped)
        self.assertEqual(matches, [(self.target, self.official, b'fixture-cover')])
        self.source.calls.clear()
        with_cover = replace(self.target, has_cover=True)
        matches, skipped = self.fetch(target=with_cover)
        self.assertFalse(skipped)
        self.assertEqual(matches, [(with_cover, self.official, None)])
        self.assertEqual(self.source.calls, [with_cover.identifiers])

    def test_compare_only_recognized_edition_markers(self):
        japanese = Record('ndl', 'fixture', 'テスト', isbn='9784041026229',
                          language='jpn', series='テスト', series_index=1)
        generic = replace(self.target, title='テスト', series='日本轻小说', series_index=3)
        self.assertFalse(edition_conflict(generic, japanese, japanese.isbn))
        same_series = replace(generic, series='テスト')
        self.assertIn('卷次', edition_conflict(same_series, japanese, japanese.isbn))
        taiwan = replace(generic, edition_markers=frozenset({'台版'}))
        self.assertIn('地区', edition_conflict(taiwan, japanese, japanese.isbn))
        self.assertEqual(volume_marks('流光 第十二巻'), (12, None))
        self.assertEqual(volume_marks('流光（７.５）'), (7.5, None))
        self.assertEqual(volume_marks('流光 下冊'), (None, '下'))


if __name__ == '__main__':
    tests = unittest.defaultTestLoader.loadTestsFromTestCase(CompanionTest)
    if not unittest.TextTestRunner(verbosity=2).run(tests).wasSuccessful():
        raise SystemExit(1)
