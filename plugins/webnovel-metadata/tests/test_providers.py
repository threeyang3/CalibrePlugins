"""Offline parser regressions; fixtures deliberately contain invented book text."""

import json
from pathlib import Path
import sys
import types
import unittest


SRC = Path(__file__).resolve().parents[1] / 'src'
if 'webnovel_metadata' not in sys.modules:
    package = types.ModuleType('webnovel_metadata')
    package.__path__ = [str(SRC)]
    sys.modules['webnovel_metadata'] = package

from webnovel_metadata.models import BookRef
from webnovel_metadata.providers import (detail_urls, make_ref, parse_book_url,
                                         parse_detail, parse_search, search_urls)
from webnovel_metadata.providers.common import image_url


FIXTURES = Path(__file__).with_name('fixtures')
QD = BookRef('qidian', '1012345678')
QM = BookRef('qimao', '123456')
FQ = BookRef('fanqie', '7123456789012345678')


def fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


class IdentityTests(unittest.TestCase):
    def test_canonicalizes_supported_details_preserving_large_id(self):
        self.assertEqual(parse_book_url('http://book.qidian.com/info/1012345678/?a=1'), QD)
        self.assertEqual(parse_book_url('https://m.qidian.com/book/1012345678/#book'), QD)
        self.assertEqual(parse_book_url('https://fanqienovel.com/page/7123456789012345678'), FQ)
        self.assertEqual(FQ.book_id, '7123456789012345678')
        self.assertEqual(make_ref('fanqie', 7123456789012345678), FQ)
        self.assertEqual(make_ref('qidian', QD.url), QD)
        self.assertIsNone(make_ref('qimao', QD.url))
        self.assertIsNone(make_ref('fanqie', 7.123456789012345678e18))

    def test_rejects_search_chapters_spoofed_hosts_and_unsafe_authority(self):
        bad = [
            'https://www.qidian.com/chapter/1012345678/99/',
            'https://www.qidian.com/so/test.html',
            'https://www.qimao.com/shuku/123456-99/',
            'https://fanqienovel.com/reader/7123456789012345678',
            'https://www.qidian.com.evil.invalid/book/1012345678/',
            'https://evil.invalid/www.qidian.com/book/1012345678/',
            'https://user:pass@www.qidian.com/book/1012345678/',
            'https://@www.qidian.com/book/1012345678/',
            'https://www.qidian.com:443/book/1012345678/',
            'https://www.qidian.com:0/book/1012345678/',
            'file:///book/1012345678/',
            'https://www.qidian.com/book/١٢٣/',
            'https://www.qidian.com\\@evil.invalid/book/1012345678/',
        ]
        for value in bad:
            with self.subTest(value=value):
                self.assertIsNone(parse_book_url(value))

    def test_mismatching_saved_page_and_redirect_are_rejected(self):
        source = fixture('qidian_desktop.html')
        with self.assertRaisesRegex(ValueError, 'ID.*不一致'):
            parse_detail(source, BookRef('qidian', '999'))
        with self.assertRaisesRegex(ValueError, 'ID.*不一致'):
            parse_detail(source.replace('data-bid="1012345678"', 'data-bid="999"'), QD)
        with self.assertRaisesRegex(ValueError, '跳转'):
            parse_detail(source, QD, final_url='https://www.qidian.com/book/999/')
        with self.assertRaisesRegex(ValueError, '跳转'):
            parse_detail(source, QD, final_url='https://www.qidian.com/login/')

    def test_verification_and_unidentified_pages_never_become_metadata(self):
        for source in ('<html><title>访问验证</title><script>challenge()</script></html>',
                       '<h1>某作品</h1><span class="author">作者</span>', ''):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_detail(source, QD)


class DetailTests(unittest.TestCase):
    def test_qidian_desktop_fields_and_multiline_synopsis(self):
        book = parse_detail(fixture('qidian_desktop.html'), QD)
        self.assertEqual((book.title, book.authors), ('星河旅人', ['风与河']))
        self.assertEqual(book.description, '在星海中寻找故乡。\n在归途中寻找自己。')
        self.assertEqual(book.tags, ['科幻', '星际文明'])
        self.assertEqual(book.word_count, '51.20万字')
        self.assertEqual(book.serialization_status, '连载中')
        self.assertEqual(book.latest_chapter, '第一百章 归航')
        self.assertEqual(book.published_at, '')
        self.assertNotIn('bad()', book.description)

    def test_qidian_mobile_uses_own_ssr_and_explicit_work_publication(self):
        book = parse_detail(fixture('qidian_mobile.html'), QD, 'https://m.qidian.com/book/1012345678/')
        self.assertEqual(book.title, '星河旅人')
        self.assertEqual(book.cover_url, 'https://bookcover.yuewen.com/qdbimg/349573/1012345678/600')
        self.assertEqual(book.published_at, '2020-04-01')
        self.assertEqual(book.word_count, '51.20万字')
        self.assertIn('\n第二段简介。', book.description)
        self.assertIn('<这不是标签>', book.description)
        self.assertEqual(book.serialization_status, '已完结')

    def test_updated_date_or_other_book_publication_is_never_used(self):
        source = fixture('qidian_mobile.html').replace('"datePublished":"2020-04-01T12:34:11+08:00",', '')
        self.assertEqual(parse_detail(source, QD).published_at, '')
        self.assertEqual(parse_detail(fixture('fanqie.html'), FQ).published_at, '')
        self.assertEqual(parse_detail(fixture('qimao.html'), QM).published_at, '')

    def test_invalid_calendar_date_is_ignored(self):
        source = fixture('qidian_mobile.html').replace('2020-04-01T12:34:11+08:00', '2020-02-31T12:34:11+08:00')
        self.assertEqual(parse_detail(source, QD).published_at, '')

    def test_qimao_uses_book_header_not_protagonist_or_recommendations(self):
        book = parse_detail(fixture('qimao.html'), QM)
        self.assertEqual((book.title, book.authors), ('山海拾遗', ['青川']))
        self.assertEqual(book.tags, ['古代言情'])
        self.assertEqual(book.word_count, '20.5万字')
        self.assertEqual(book.serialization_status, '已完结')
        self.assertIn('/readerCover/', book.cover_url)
        self.assertEqual(book.latest_chapter, '第八十章 后记')
        self.assertEqual(book.updated_at, '2025-06-01 12:00:00')
        self.assertEqual(book.description, '第一段简介。\n第二段简介。')

    def test_qimao_wrong_latest_chapter_book_id_is_rejected(self):
        source = fixture('qimao.html').replace('/shuku/123456-1700000000/', '/shuku/654321-1700000000/')
        with self.assertRaisesRegex(ValueError, 'ID.*不一致'):
            parse_detail(source, QM)

    def test_fanqie_uses_identity_bound_signed_cover(self):
        book = parse_detail(fixture('fanqie.html'), FQ)
        self.assertEqual((book.title, book.authors), ('漫长的归途', ['北风']))
        self.assertEqual(book.cover_url, 'https://p9-novel-sign.byteimg.com/cover.image?x-expires=1900000000&x-signature=a%2Bb%3D')
        self.assertEqual(book.word_count, '13.5万字')
        self.assertEqual(book.latest_chapter, '第十章 山路')
        self.assertIn('\n', book.description)

    def test_fanqie_placeholder_and_other_book_jsonld_are_not_covers(self):
        source = fixture('fanqie.html').replace('"@id":"https://fanqienovel.com/page/7123456789012345678"', '"@id":"https://fanqienovel.com/page/999"')
        self.assertEqual(parse_detail(source, FQ).cover_url, '')

    def test_fanqie_json_state_fallback_uses_book_abstract_not_author_profile(self):
        state = {'home': {'bookId': '999'}, 'page': {
            'bookId': FQ.book_id, 'bookName': '漫长的归途', 'author': '北风',
            'abstract': '第一行。\n第二行。', 'description': '作者简介，不是作品简介。',
            'thumbUri': 'https://p3-novel.byteimg.com/book.jpg', 'wordNumber': 12345,
            'categoryV2': json.dumps([{'Name': '玄幻'}]),
        }}
        source = '<script>window.__INITIAL_STATE__=' + json.dumps(state) + ';throw new Error("not executed")</script>'
        book = parse_detail(source, FQ)
        self.assertEqual(book.title, '漫长的归途')
        self.assertEqual(book.description, '第一行。\n第二行。')
        self.assertEqual(book.tags, ['玄幻'])
        self.assertEqual(book.word_count, '12345字')

    def test_missing_author_does_not_fall_back_to_page_title(self):
        source = fixture('fanqie.html').replace('<span class="author-name-text">北风</span>', '')
        with self.assertRaisesRegex(ValueError, '书名和作者'):
            parse_detail(source, FQ)

    def test_nested_recommendation_is_not_identity_evidence(self):
        data = {'recommendation': {'@type': 'Book', '@id': FQ.url, 'name': '推荐作品', 'author': {'name': '作者'}}}
        source = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        with self.assertRaisesRegex(ValueError, '可靠的作品 ID'):
            parse_detail(source, FQ)

    def test_qidian_unscoped_recommendation_cannot_supply_missing_book_header(self):
        source = ('<link rel="canonical" href="' + QD.url + '">'
                  '<aside><div class="book-info"><h1><em>推荐作品</em>'
                  '<a class="writer">其他作者</a></h1></div>'
                  '<div class="book-img"><img src="https://qidian.qpic.cn/other.jpg"></div></aside>')
        with self.assertRaisesRegex(ValueError, '书名和作者'):
            parse_detail(source, QD)

    def test_rejects_non_public_image_urls(self):
        for value in ('data:image/png;base64,abc', 'file:///tmp/cover.png',
                      'https://127.0.0.1/cover.jpg', 'https://localhost/cover.jpg',
                      'https://x.local/cover.jpg', 'https://u:p@cdn.qimao.com/cover.jpg',
                      'https://cdn.qimao.com:0/cover.jpg', 'https://cdn.qimao.com/loading.png'):
            with self.subTest(value=value):
                self.assertEqual(image_url(value, QM.url), '')


class SearchTests(unittest.TestCase):
    def test_search_urls_are_fixed_official_paths_with_encoded_query(self):
        urls = search_urls('qimao', '书名 & 作者')
        self.assertTrue(urls[0].startswith('https://www.qimao.com/qimaoapi/api/search/result?'))
        self.assertIn('%26', urls[0])
        self.assertIn('https://m.qidian.com/book/1012345678/', detail_urls(QD))
        self.assertEqual(search_urls('fanqie', '..'), [])

    def test_qimao_api_excludes_recommendations_and_conflicting_url(self):
        payload = {'data': {'search_list': [
            {'book_id': '123456', 'read_url': QM.url},
            {'book_id': '123456', 'read_url': QM.url},
            {'book_id': '222', 'read_url': 'https://www.qimao.com/shuku/333/'},
        ], 'do_you_like_list': [{'book_id': '999'}]}}
        self.assertEqual(parse_search(json.dumps(payload), 'qimao', search_urls('qimao', '山海')[0]), [QM])

    def test_qidian_mobile_ssr_uses_bid_not_cbid(self):
        payload = {'pageContext': {'pageProps': {'pageData': {'bookInfo': {'records': [
            {'bid': 1012345678, 'cbid': '777', 'bName': '星河旅人'},
            {'cbid': '888', 'bName': '不是起点作品 ID'},
        ]}, 'recommend': [{'bid': 999}]}}}}
        source = '<script type="application/json" id="vite-plugin-ssr_pageContext">' + json.dumps(payload) + '</script>'
        self.assertEqual(parse_search(source, 'qidian', 'https://m.qidian.com/so/test.html'), [QD])

    def test_fanqie_api_keeps_large_integer_id_without_rounding(self):
        payload = {'code': 0, 'data': {'search_book_data_list': [
            {'book_id': 7123456789012345678}, {'book_id': 7.123456789012345e18},
        ], 'author_data_list': [{'book_id': '999'}]}}
        self.assertEqual(parse_search(json.dumps(payload), 'fanqie', 'https://fanqienovel.com/search/test'), [FQ])

    def test_html_links_filter_chapters_spoofed_hosts_and_duplicate_books(self):
        source = ('<a href="//m.qidian.com/book/1012345678/">作品</a>'
                  '<a href="https://www.qidian.com/book/1012345678/">同一作品</a>'
                  '<a href="https://www.qidian.com.evil.invalid/book/999/">假链接</a>'
                  '<a href="/chapter/1012345678/123/">章节</a>')
        self.assertEqual(parse_search(source, 'qidian', 'https://m.qidian.com/so/test.html'), [QD])

    def test_empty_error_or_unrecognizable_json_is_not_reported_as_no_matches(self):
        for source in ('', '{"code":403,"data":{}}', '{"data":{}}', '{broken', '[]'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_search(source, 'fanqie', 'https://fanqienovel.com/search/test')
        self.assertEqual(parse_search('{"data":{"search_list":[]}}', 'qimao', 'https://www.qimao.com/search/index/'), [])


if __name__ == '__main__':
    unittest.main()
