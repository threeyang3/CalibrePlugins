import unittest
from support import SRC
from lightnovel_metadata.models import Record, isbn, volume_info, safe_date, combine, relevance
from lightnovel_metadata.engine import explicit_sources


def make_isbn(prefix):
    assert len(prefix) == 12
    return prefix + str(-sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(prefix)) % 10)


JP = make_isbn('978404123456')
TW = make_isbn('978626123456')


class DataIdentityTests(unittest.TestCase):
    def test_checksums_and_conversion(self):
        self.assertEqual(isbn(JP), JP)
        self.assertEqual(isbn(TW), TW)
        self.assertEqual(isbn('0-306-40615-2'), '9780306406157')
        self.assertEqual(isbn('9780306406158'), '')
        self.assertEqual(isbn('not-an-isbn'), '')

    def test_date_precision(self):
        self.assertEqual(safe_date('2025-01-02'), '2025-01-02')
        self.assertEqual(safe_date('20250102'), '2025-01-02')
        self.assertEqual(safe_date('2025/1/2'), '2025-01-02')
        self.assertEqual(safe_date('2025-01'), '')
        self.assertEqual(safe_date('2025-02-30'), '')

    def test_volume_parsing_prevents_cross_volume_match(self):
        self.assertEqual(volume_info('轻小说 第3卷'), ('轻小说', 3.0))
        self.assertEqual(volume_info('轻小说 (2)'), ('轻小说', 2.0))
        self.assertEqual(volume_info('轻小说（第3册）'), ('轻小说', 3.0))
        book = Record('books_tw', '0011234567', '轻小说（2）', ['作者A'], TW)
        self.assertIsNone(relevance(book, '轻小说（3）'))
        self.assertIsNotNone(relevance(book, '轻小说（2）'))
        self.assertIsNone(relevance(Record('bangumi', '123456', '轻小说'), '轻小说（2）'))

    def test_distinct_isbn_cannot_merge_even_if_title_is_identical(self):
        a = Record('openbd', JP, '同名作品 第一卷', ['作者A'], JP)
        b = Record('books_tw', '0011234567', '同名作品 第一卷', ['作者A'], TW)
        merged = combine([a, b])
        self.assertEqual(len(merged), 2)
        self.assertEqual({r.isbn for r in merged}, {JP, TW})

    def test_exact_isbn_merges_but_keeps_source_ids(self):
        a = Record('openbd', JP, '同名作品 (1)', ['作者A'], JP, publisher='日本出版社')
        b = Record('bangumi', '123456', '同名作品 (1)', ['作者A'], JP,
                   description='中文介绍', tags=['轻小说'])
        merged = combine([b, a])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].identifiers, {'bangumi': '123456'})
        self.assertEqual(merged[0].source_labels, ['openbd', 'bangumi'])
        self.assertEqual(merged[0].publisher, '日本出版社')
        self.assertIn('轻小说', merged[0].tags)
        self.assertEqual(merged[0].series_index, 1.0)

    def test_conflicting_platform_ids_fail_instead_of_silently_choosing_one(self):
        a = Record('bangumi', '123456', '同名作品', ['作者A'], JP)
        b = Record('bangumi', '765432', '同名作品', ['作者A'], JP)
        with self.assertRaisesRegex(ValueError, '冲突'):
            combine([a, b])

    def test_no_isbn_means_no_cross_site_merge(self):
        a = Record('bangumi', '123456', '作品', ['作者A'])
        b = Record('ndl', 'https://ndlsearch.ndl.go.jp/books/R123', '作品', ['作者A'])
        self.assertEqual(len(combine([a, b])), 2)

    def test_known_site_identifiers_and_ssrf_defense(self):
        ids, code = explicit_sources('https://bgm.tv/subject/123456', {'isbn': JP})
        self.assertEqual(ids, {'bangumi': '123456'})
        self.assertEqual(code, JP)
        ids, code = explicit_sources('https://www.books.com.tw/products/0011234567', {})
        self.assertEqual(ids, {'books_tw': '0011234567'})
        ids, code = explicit_sources('https://evil.test/products/0011234567', {})
        self.assertFalse(ids)
        with self.assertRaises(ValueError):
            explicit_sources('https://bgm.tv/subject/123456', {'bangumi': '654321'})
        with self.assertRaises(ValueError):
            explicit_sources('', {'isbn': '978bad'})

if __name__ == '__main__':
    unittest.main()
