"""Offline tests for KADOKAWA Japan's ISBN-verified publisher data."""

import unittest

import test_engine
from lightnovel_metadata.engine import explicit_sources
from lightnovel_metadata.network import allowed
from lightnovel_metadata.providers import kadokawa_jp


ISBN = '9784041026229'
PID = '321603000121'
OTHER_PID = '321603000124'
COVER = 'https://cdn.kdkw.jp/cover_1000/321603/321603000121.webp'
SEARCH = '''
<a href="/shop/g/g111111111111/">おすすめ</a>
<a class="js-enhanced-ecommerce-image" href="/shop/g/g321603000124/">別版</a>
<a class="block-extra js-enhanced-ecommerce-image" href="/shop/g/g321603000121/">小説</a>
<a class="js-enhanced-ecommerce-image" href="/shop/g/g321603000121/">重複</a>
<a class="js-enhanced-ecommerce-image" href="https://example.com/shop/g/g321603000125/">別サイト</a>
'''


def product(pid=PID, isbn=ISBN, cover=COVER, category='文庫'):
    return f'''<html><head>
<link rel="canonical" href="https://www.kadokawa.co.jp/product/{pid}/">
<meta property="og:url" content="https://www.kadokawa.co.jp/product/{pid}/">
<meta property="og:image" content="{cover}">
</head><body>
<ul itemtype="https://schema.org/BreadcrumbList"><li><span itemprop="name">{category}</span></li></ul>
<h1 itemprop="name" id="book-title-sp">小説　星の旅</h1>
<span itemprop="datePublished" content="2016-06-18">2016年06月18日</span>
<ul itemprop="author"><li>著者&nbsp;青山　海</li><li>イラスト&nbsp;<a>山田</a></li></ul>
<dl itemprop="workExample"><dt>ISBN：</dt><dd itemprop="isbn">{isbn}</dd></dl>
<div id="book-description"><span class="show-text">星を探しに行く物語。</span></div>
<div class="recommendations"><span itemprop="isbn">{ISBN}</span></div>
</body></html>'''


class KadokawaJapanTests(unittest.TestCase):
    def test_search_prefers_product_cards_with_official_urls(self):
        self.assertEqual(kadokawa_jp.search_ids(SEARCH, 5), [OTHER_PID, PID])
        self.assertEqual(kadokawa_jp.search_ids(SEARCH, 1), [OTHER_PID])
        self.assertTrue(allowed(kadokawa_jp.SEARCH.format(ISBN)))
        self.assertTrue(allowed(COVER, image=True))
        self.assertFalse(allowed(COVER.replace('cdn.kdkw.jp', 'example.cdn.kdkw.jp'), image=True))

    def test_bound_detail_and_cover(self):
        row = kadokawa_jp.parse_detail(product(), PID, ISBN)
        self.assertEqual(row.isbn, ISBN)
        self.assertEqual(row.identifiers, {'kadokawa_jp': PID})
        self.assertEqual(row.language, 'jpn')
        self.assertEqual(row.pubdate, '2016-06-18')
        self.assertEqual(row.authors, ['青山 海'])
        self.assertEqual(row.illustrators, ['山田'])
        self.assertEqual(row.description, '星を探しに行く物語。')
        self.assertEqual(row.cover, COVER)
        different_cover = COVER.replace(PID, OTHER_PID)
        self.assertEqual(kadokawa_jp.parse_detail(product(cover=different_cover), PID).cover, '')

    def test_rejects_conflicting_product_isbn_or_category(self):
        with self.assertRaisesRegex(ValueError, '商品标识'):
            kadokawa_jp.parse_detail(product(pid=OTHER_PID), PID, ISBN)
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            kadokawa_jp.parse_detail(product(isbn='9784046837936'), PID, ISBN)
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            kadokawa_jp.parse_detail(product(isbn=''), PID, ISBN)
        with self.assertRaisesRegex(ValueError, '漫画版'):
            kadokawa_jp.parse_detail(product(category='コミック'), PID, ISBN)

    def test_both_official_urls_resolve_to_canonical_id(self):
        for url in (kadokawa_jp.PRODUCT.format(PID), kadokawa_jp.STORE + '/shop/g/g' + PID + '/'):
            self.assertEqual(explicit_sources(url, {'isbn': ISBN}), ({'kadokawa_jp': PID}, ISBN))

    def test_engine_validates_actual_product_isbn_before_selecting_cover(self):
        routes = {('text', kadokawa_jp.SEARCH.format(ISBN)): SEARCH,
                  ('text', kadokawa_jp.PRODUCT.format(PID)): product(),
                  ('text', kadokawa_jp.PRODUCT.format(OTHER_PID)): product(pid=OTHER_PID, isbn='9784046837936')}
        settings = {'enable_kadokawa_jp': True}
        rows, calls, logs = test_engine.EngineIntegrationTests().run_lookup(routes, settings, identifiers={'isbn': ISBN})
        self.assertEqual([(row.source_id, row.cover) for row in rows], [(PID, COVER)])
        self.assertEqual(len(calls), 3)
        self.assertIn('ISBN', logs[0])
        rows, calls, logs = test_engine.EngineIntegrationTests().run_lookup(
            routes, settings, identifiers={'isbn': ISBN, 'kadokawa_jp': OTHER_PID})
        self.assertEqual(rows, [])
        self.assertEqual(calls, [('text', kadokawa_jp.PRODUCT.format(OTHER_PID))])
