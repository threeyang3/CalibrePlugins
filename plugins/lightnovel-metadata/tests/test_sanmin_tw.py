"""Sanmin paperback identity, attributed fields and ISBN-only fallback."""

import json
import unittest
from unittest.mock import patch

import test_engine
from test_models import make_isbn
from lightnovel_metadata.engine import explicit_sources
from lightnovel_metadata.models import Record
from lightnovel_metadata.network import allowed
from lightnovel_metadata.providers import books_tw, kadokawa_tw, sanmin_tw


ISBN = '9789572696583'
LIMITED_ISBN = make_isbn('978957269659')
PID = '009001234'
LIMITED_PID = '009001235'
OTHER_PID = '009001236'
COVER = 'https://cdnec.sanmin.com.tw/product_images/957/957269658.jpg'
LIMITED_COVER = 'https://cdnec.sanmin.com.tw/product_images/957/957269659.jpg'
PRIMARY_COVER = 'https://im1.book.com.tw/verified.jpg'
SETTINGS = {'enable_books_tw': True, 'enable_kadokawa_tw': True, 'enable_sanmin_tw': True}
SEARCH_PAGE = f'''
<aside><a href="/product/index/{OTHER_PID}">站內推薦</a></aside>
<div class="Prod"><div class="sProduct">
  <a href="/product/index/{LIMITED_PID}">限定版</a>
</div></div>
<div class="Prod"><div class="sProduct">
  <a href="/product/index/{PID}">普通版</a>
  <a href="/product/index/{PID}">重複連結</a>
  <a href="https://example.test/product/index/{OTHER_PID}">第三方</a>
</div></div>'''


def product(pid=PID, code=ISBN, cover=COVER, *, headline_code=None, og_cover=None,
            translator='林海', title='星海旅人（07）'):
    def item(label, value):
        return f'<li><h3><span class="Bold">{label}</span><span class="colon">：</span><span>{value}</span></h3></li>'

    url = sanmin_tw.PRODUCT.format(pid)
    details = ''.join(item(label, value) for label, value in (
        ('ISBN13', headline_code if headline_code is not None else code),
        ('作者', '青山創'), ('譯者', translator), ('出版社', '出版社甲'), ('出版日', '2025/09/08'),
    ) if value)
    book = {'@context': 'https://schema.org', '@type': 'Book', '@id': url, 'url': url,
            'name': title, 'isbn': code, 'image': cover, 'bookFormat': 'https://schema.org/Paperback'}
    return f'''<html><head><link rel="canonical" href="{url}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{og_cover if og_cover is not None else cover}">
<script type="application/ld+json">{json.dumps(book, ensure_ascii=False)}</script></head>
<body><div class="ProductInfo"><h1>{title}</h1><ul class="ProdAttr">{details}</ul></div>
<h2 id="Intro1">商品簡介</h2><div class="SectionBody">這是普通版的簡介。</div>
<aside><ul class="ProdAttr">{item('譯者', '推薦書籍的譯者')}{item('ISBN13', LIMITED_ISBN)}</ul>
<img src="{LIMITED_COVER}"></aside></body></html>'''


class SanminAdapterTest(unittest.TestCase):
    def test_search_keeps_product_scope_ranking_and_limit(self):
        self.assertEqual(sanmin_tw.search_ids(SEARCH_PAGE, 5), [LIMITED_PID, PID])
        self.assertEqual(sanmin_tw.search_ids(SEARCH_PAGE, 1), [LIMITED_PID])
        self.assertEqual(sanmin_tw.product_id(sanmin_tw.PRODUCT.format(PID)), PID)
        self.assertFalse(sanmin_tw.product_id(f'https://www.sanmin.com.tw.example.test/product/index/{PID}'))

    def test_exact_book_owns_cover_and_translator(self):
        row = sanmin_tw.parse_detail(product(), PID, ISBN)
        self.assertEqual(row.isbn, ISBN)
        self.assertEqual(row.identifiers, {'sanmin_tw': PID})
        self.assertEqual(row.cover, COVER)
        self.assertEqual(row.translators, ['林海'])
        self.assertEqual(row.authors, ['青山創'])
        self.assertEqual(row.publisher, '出版社甲')
        self.assertEqual(row.pubdate, '2025-09-08')
        self.assertEqual(row.language, 'zho')
        self.assertEqual(sanmin_tw.parse_detail(product(translator=''), PID, ISBN).translators, [])
        self.assertTrue(allowed(sanmin_tw.SEARCH.format(ISBN)))
        self.assertTrue(allowed(COVER, image=True))
        self.assertFalse(allowed(COVER.replace('cdnec.sanmin.com.tw', 'sanmin.com.tw.example.test'), image=True))

    def test_wrong_product_or_isbn_is_rejected_and_conflicting_cover_is_ignored(self):
        with self.assertRaises(ValueError):
            sanmin_tw.parse_detail(product(pid=LIMITED_PID), PID, ISBN)
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            sanmin_tw.parse_detail(product(pid=LIMITED_PID, code=LIMITED_ISBN, cover=LIMITED_COVER), LIMITED_PID, ISBN)
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            sanmin_tw.parse_detail(product(headline_code=LIMITED_ISBN), PID, ISBN)
        self.assertFalse(sanmin_tw.parse_detail(product(og_cover=LIMITED_COVER), PID, ISBN).cover)
        self.assertFalse(sanmin_tw.parse_detail(product(cover=LIMITED_COVER), PID, ISBN).cover)


class SanminFallbackTest(unittest.TestCase):
    def lookup(self, *, existing=(), options=None, identifiers=None):
        routes = {
            ('text', sanmin_tw.SEARCH.format(ISBN)): SEARCH_PAGE,
            ('text', sanmin_tw.PRODUCT.format(LIMITED_PID)): product(
                pid=LIMITED_PID, code=LIMITED_ISBN, cover=LIMITED_COVER, translator='限定譯者', title='星海旅人（07）限定版'),
            ('text', sanmin_tw.PRODUCT.format(PID)): product(),
        }
        primaries = {row.source: row for row in existing}
        with patch.object(books_tw, 'search', return_value=['0011234567']), \
             patch.object(books_tw, 'detail', return_value=primaries.get('books_tw')), \
             patch.object(kadokawa_tw, 'detail', return_value=primaries.get('kadokawa_tw')):
            return test_engine.EngineIntegrationTests().run_lookup(
                routes, {**SETTINGS, **(options or {})}, identifiers=identifiers or {'isbn': ISBN})

    def test_store_fallback_selects_standard_edition_after_limited_result(self):
        rows, calls, _ = self.lookup()
        self.assertEqual(calls, [
            ('text', sanmin_tw.SEARCH.format(ISBN)),
            ('text', sanmin_tw.PRODUCT.format(LIMITED_PID)),
            ('text', sanmin_tw.PRODUCT.format(PID)),
        ])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.isbn, ISBN)
        self.assertEqual(row.identifiers, {'sanmin_tw': PID})
        self.assertEqual(row.cover, COVER)
        self.assertEqual(row.translators, ['林海'])

    def test_uses_primary_cover_when_filling_a_missing_translator(self):
        primary = Record('books_tw', '0011234567', '星海旅人（07）', isbn=ISBN,
                         cover=PRIMARY_COVER, language='zho')
        rows, calls, _ = self.lookup(existing=[primary])
        self.assertIn(('text', sanmin_tw.SEARCH.format(ISBN)), calls)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].cover, PRIMARY_COVER)
        self.assertEqual(rows[0].field_sources['cover'], 'books_tw')
        self.assertEqual(rows[0].translators, ['林海'])
        self.assertEqual(rows[0].field_sources['translators'], 'sanmin_tw')

    def test_sufficient_combined_primary_fields_skip_extra_store(self):
        books = Record('books_tw', '0011234567', '星海旅人（07）', isbn=ISBN,
                       cover=PRIMARY_COVER, language='zho')
        publisher = Record('kadokawa_tw', ISBN, '星海旅人（07）', isbn=ISBN,
                           translators=['出版社譯者'], language='zho')
        rows, calls, _ = self.lookup(existing=[books, publisher])
        self.assertEqual(calls, [])
        self.assertEqual(rows[0].cover, PRIMARY_COVER)
        self.assertEqual(rows[0].translators, ['出版社譯者'])

        rows, calls, _ = self.lookup(existing=[books, publisher], options={'pref_cover': 'sanmin_tw'})
        self.assertIn(('text', sanmin_tw.SEARCH.format(ISBN)), calls)
        self.assertEqual(rows[0].cover, COVER)
        self.assertEqual(rows[0].field_sources['cover'], 'sanmin_tw')

    def test_explicit_sanmin_or_other_source_id_is_not_replaced_by_isbn_search(self):
        self.assertEqual(explicit_sources(sanmin_tw.PRODUCT.format(PID), {'isbn': ISBN}),
                         ({'sanmin_tw': PID}, ISBN))
        rows, calls, _ = self.lookup(identifiers={'isbn': ISBN, 'sanmin_tw': LIMITED_PID})
        self.assertEqual(rows, [])
        self.assertEqual(calls, [('text', sanmin_tw.PRODUCT.format(LIMITED_PID))])

        rows, calls, _ = self.lookup(identifiers={'isbn': ISBN, 'sanmin_tw': PID})
        self.assertEqual([row.identifiers for row in rows], [{'sanmin_tw': PID}])
        self.assertEqual(calls, [('text', sanmin_tw.PRODUCT.format(PID))])

        rows, calls, _ = self.lookup(identifiers={'isbn': ISBN, 'books_tw': '0011234567'})
        self.assertEqual(rows, [])
        self.assertEqual(calls, [])
