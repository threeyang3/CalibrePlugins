import json
import unittest
from support import SRC
from test_models import JP, TW
from lightnovel_metadata.providers import bangumi, books_tw, ndl, openbd


BGM_SAMPLE = {
    'id': 123456, 'type': 1, 'platform': 1002, 'name': '空の軌跡 (1)',
    'name_cn': '天空轨迹（1）', 'date': '2025-10-10',
    'infobox': [{'key': '作者', 'value': '青空'},
                {'key': '插画', 'value': [{'v': '绘师'}]},
                {'key': 'ISBN', 'value': JP},
                {'key': '出版社', 'value': '角川'}],
    'summary': '第一卷故事简介', 'images': {'large': 'https://lain.bgm.tv/pic/cover/l/demo.jpg'},
    'tags': [{'name': '轻小说'}]
}


class ProviderParsers(unittest.TestCase):
    def test_bangumi_novel(self):
        r = bangumi.parse_detail(BGM_SAMPLE)
        self.assertEqual(r.identifiers, {'bangumi': '123456'})
        self.assertEqual(r.title, '天空轨迹（1）')
        self.assertEqual(r.original_title, '空の軌跡 (1)')
        self.assertEqual(r.series_index, 1.0)
        self.assertEqual(r.illustrators, ['绘师'])
        self.assertEqual(r.isbn, JP)

    def test_bangumi_manga_is_not_a_novel(self):
        for category in (1001, 1003, 9999):
            item = dict(BGM_SAMPLE, platform=category)
            self.assertIsNone(bangumi.parse_detail(item))
        self.assertIsNone(bangumi.parse_detail(dict(BGM_SAMPLE, type=2)))
        self.assertIsNone(bangumi.parse_detail({k:v for k,v in BGM_SAMPLE.items() if k != 'platform'}))

    def test_bangumi_search_shape(self):
        class Fake:
            def json(self, url, body=None):
                self.url, self.body = url, body
                return {'data': [{'id': 123456, 'type': 1, 'platform': 1002},
                                 {'id': 123457, 'type': 1, 'platform': 1001}]}
        fake = Fake()
        self.assertEqual(bangumi.search(fake, '天空轨迹', 5), ['123456'])
        self.assertIn('/v0/search/subjects?', fake.url)
        self.assertEqual(fake.body['filter']['type'], [1])

    def test_openbd_japanese_edition_and_contributor_roles(self):
        sample = [{'summary': {'isbn': JP, 'title': '空の軌跡 (1)',
                               'author': '青空', 'publisher': 'KADOKAWA',
                               'pubdate': '20251010', 'cover': 'https://cover.openbd.jp/mock.jpg'},
                   'onix': {'DescriptiveDetail': {'Contributor': [
                       {'PersonName': {'content': '青空'}, 'ContributorRole': ['A01']},
                       {'PersonName': {'content': '绘师'}, 'ContributorRole': ['A12']},
                       {'PersonName': {'content': '译者'}, 'ContributorRole': ['B06']},
                   ]}, 'CollateralDetail': {'TextContent': [{'TextType': '03', 'Text': {'content': '书籍介绍'}}]}}}]
        r = openbd.parse_detail(sample, JP)
        self.assertEqual(r.pubdate, '2025-10-10')
        self.assertEqual(r.authors, ['青空'])
        self.assertEqual(r.illustrators, ['绘师'])
        self.assertEqual(r.translators, ['译者'])
        self.assertEqual(r.description, '书籍介绍')
        self.assertIsNone(openbd.parse_detail(sample, TW))

    def sample_tw_product(self):
        pid = '0011234567'
        html = '''<!doctype html><html><head>
        <link rel="canonical" href="https://www.books.com.tw/products/0011234567" />
        <meta property="og:image" content="https://im1.book.com.tw/image/getImage?mock" />
        <script type="application/ld+json">''' + json.dumps({
            '@type': 'Book', 'url': 'https://www.books.com.tw/products/' + pid,
            'name': '天空軌跡（1）', 'isbn': TW, 'author': [{'name': '青空'}],
            'publisher': {'name': '台灣出版社'}, 'datePublished': '2025-11-12',
            'description': '台版简介'}) + '''</script></head><body>
        <h1>天空軌跡（1）</h1><div class="type02_p003">譯者： 阿明 出版日期：2025/11/12</div>
        <div class="bd type02_m02">詳細資料 ISBN：''' + TW + ''' </div></body></html>'''
        return html

    def test_books_tw_identifies_print_edition_and_extracts_credits(self):
        pid = '0011234567'
        html = self.sample_tw_product()
        r = books_tw.parse_detail(html, pid)
        self.assertEqual(r.isbn, TW)
        self.assertEqual(r.identifiers, {'books_tw': pid})
        self.assertEqual(r.publisher, '台灣出版社')
        self.assertEqual(r.pubdate, '2025-11-12')
        self.assertEqual(r.tags, ['台版'])
        self.assertEqual(r.translators, ['阿明'])

    def test_books_tw_wrong_product_or_isbn_is_rejected(self):
        markup = self.sample_tw_product()
        self.assertRaisesRegex(ValueError, '标识|指向', books_tw.parse_detail,
                               markup.replace('canonical" href="https://www.books.com.tw/products/0011234567',
                                              'canonical" href="https://www.books.com.tw/products/0019999999'),
                               '0011234567')
        self.assertRaisesRegex(ValueError, 'ISBN', books_tw.parse_detail,
                               markup.replace('詳細資料 ISBN：'+TW, '詳細資料 ISBN：'+JP),
                               '0011234567')
        self.assertRaisesRegex(ValueError, '标识', books_tw.parse_detail,
                               markup.replace('<link rel="canonical" href="https://www.books.com.tw/products/0011234567" />', ''),
                               '0011234567')

    def test_books_tw_search_links(self):
        markup = '<a href="//www.books.com.tw/products/0011234567">good</a>' \
                 '<a href="https://fakebooks.com/products/0011234567">fake</a>' \
                 '<a href="https://www.books.com.tw/products/0011234567">repeat</a>'
        self.assertEqual(books_tw.search_ids(markup), ['0011234567'])

    def test_ndl_rss_namespaced_isbn(self):
        rss = f'''<?xml version="1.0"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/">
        <channel><item><title>空の軌跡 (1)</title><link>https://ndlsearch.ndl.go.jp/books/R123</link>
        <dc:creator>青空</dc:creator><dc:identifier>ISBN:{JP}</dc:identifier>
        <dc:publisher>角川</dc:publisher><dc:date>2025-10-10</dc:date></item>
        <item><title>別の本</title><dc:identifier>ISBN:{TW}</dc:identifier></item></channel></rss>'''
        rows = ndl.parse_search(rss)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].isbn, JP)
        self.assertEqual(rows[0].authors, ['青空'])
        self.assertEqual(len(ndl.parse_search(rss, JP)), 1)
        self.assertEqual(rows[1].language, '')
        with self.assertRaises(ValueError):
            ndl.url_for(isbn_value='0')

if __name__ == '__main__':
    unittest.main()
