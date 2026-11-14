"""Offline regressions for Taiwanese publishers, NCL indexing and provenance."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from support import SRC
from test_models import JP, TW, make_isbn
from test_providers import BGM_SAMPLE
from lightnovel_metadata.models import Record, combine, volume_info
from lightnovel_metadata.engine import Engine, explicit_sources
from lightnovel_metadata.providers import bangumi, kadokawa_tw, spp_tw, ncl_tw
from lightnovel_metadata.network import allowed

ROOT = SRC.parent


def example_kado(code=TW):
    return '''<html><head><link rel="canonical" href="https://www.kadokawa.com.tw/products/%s">
<meta property="og:image" content="https://img.shoplineapp.com/mock.jpg"/></head>
<body><h1>天空軌跡 (7.5) 夜話</h1>
<div>作者資訊：坂石遊作 / 插畫：いちかわはる</div>
<div>上市日期：2025/10/22</div><div>ISBN：%s</div>
<section>〖內容介紹〗小說簡介。〖作者介紹〗作者資訊。</section>
</body></html>''' % (code, code)


def example_spp(pid='10055328', code=TW):
    return '''<html><head><meta property="og:url" content="https://www.spp.com.tw/SalePage/Index/%s">
<meta property="og:image" content="https://www.spp.com.tw/images/cover.jpg"/></head>
<body><h1>我想成為你的眼淚</h1><div>商品特色</div>
<div>商品編號：%s 條　碼：%s 書　號：7B000997 作　者：四季大雅
繪　者：柳珠栄 譯　者：李潔鈴 書　系：浮文字 規　格：新32開/膠裝 等　級：普遍級 上市日：2024/03/01</div>
<div>銷售重點：這是下一本書的ISBN：%s</div>
</body></html>''' % (pid, pid, code, JP)


class PublisherTests(unittest.TestCase):
    def test_kado_verified_isbn_authors_and_fractional_volume(self):
        r = kadokawa_tw.parse_detail(example_kado(), TW)
        self.assertEqual(r.isbn, TW)
        self.assertEqual(r.identifiers['kadokawa_tw'], TW)
        self.assertEqual(r.publisher, '台灣角川')
        self.assertEqual(r.authors, ['坂石遊作'])
        self.assertEqual(r.illustrators, ['いちかわはる'])
        self.assertEqual(r.pubdate, '2025-10-22')
        self.assertEqual(r.series_index, 7.5)
        self.assertIn('小說簡介', r.description)
        self.assertEqual(volume_info('作品 (9.5) 外传'), ('作品', 9.5))

    def test_kado_mismatch_or_bundle_cannot_be_an_edition(self):
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            kadokawa_tw.parse_detail(example_kado(JP), TW)
        self.assertEqual(kadokawa_tw.isbn_from_url('https://www.kadokawa.com.tw/products/bundle-01'), '')
        self.assertEqual(kadokawa_tw.isbn_from_url('https://www.kadokawa.com.tw.evil.net/products/' + TW), '')
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            kadokawa_tw.parse_detail(example_kado().replace('ISBN：' + TW, 'ISBN：' + JP), TW)

    def test_spp_book_and_identity(self):
        r = spp_tw.parse_detail(example_spp(), '10055328')
        self.assertEqual(r.isbn, TW)
        self.assertEqual(r.identifiers['spp_tw'], '10055328')
        self.assertEqual(r.authors, ['四季大雅'])
        self.assertEqual(r.illustrators, ['柳珠栄'])
        self.assertEqual(r.translators, ['李潔鈴'])
        self.assertEqual(r.pubdate, '2024-03-01')
        self.assertEqual(r.publisher, '尖端出版')
        with self.assertRaisesRegex(ValueError, '不同'):
            spp_tw.parse_detail(example_spp().replace('/Index/10055328', '/Index/10055329'), '10055328')
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            spp_tw.parse_detail(example_spp().replace('條　碼：' + TW, '條　碼：0000000000000'), '10055328')

    def test_allowed_hostnames(self):
        self.assertTrue(allowed('https://www.kadokawa.com.tw/products/' + TW))
        self.assertTrue(allowed('https://www.spp.com.tw/SalePage/Index/10055328'))
        self.assertTrue(allowed('https://img.shoplineapp.com/mock.jpg', image=True))
        self.assertFalse(allowed('http://www.spp.com.tw/SalePage/Index/10055328'))
        self.assertFalse(allowed('https://www.kadokawa.com.tw.bad.example/products/' + TW))

    def test_publisher_url_identity_in_calibre_search(self):
        ids, code = explicit_sources('https://www.kadokawa.com.tw/products/' + TW, {})
        self.assertEqual(ids, {'kadokawa_tw': TW})
        self.assertEqual(code, TW)
        ids, code = explicit_sources('https://www.spp.com.tw/SalePage/Index/10055328', {})
        self.assertEqual(ids, {'spp_tw': '10055328'})
        self.assertEqual(code, '')
        with self.assertRaisesRegex(ValueError, '冲突'):
            explicit_sources('https://www.kadokawa.com.tw/products/' + TW, {'isbn': JP})

    def test_kado_ignores_script_embedded_book_information(self):
        wrong = example_kado().replace('ISBN：' + TW, 'ISBN：0000000000000')
        wrong = wrong.replace('</body>', '<script>ISBN：' + TW + '</script></body>')
        with self.assertRaisesRegex(ValueError, 'ISBN'):
            kadokawa_tw.parse_detail(wrong, TW)


class DataFusionTests(unittest.TestCase):
    def test_same_isbn_field_preference_preserves_other_fields(self):
        a = Record('kadokawa_tw', TW, '繁體書名 (1)', ['原作者'], TW,
                   publisher='台灣角川', cover='https://img.shoplineapp.com/one.jpg')
        b = Record('books_tw', '0011234567', '博客來書名 (1)', ['作者資料'], TW,
                   description='博客來簡介', cover='https://im1.book.com.tw/other.jpg')
        original_title = a.title
        merged = combine([a,b], {'title':'books_tw','cover':'kadokawa_tw','description':'books_tw'})[0]
        self.assertEqual(merged.title, b.title)
        self.assertEqual(merged.publisher, '台灣角川')
        self.assertEqual(merged.description, '博客來簡介')
        self.assertEqual(merged.cover, a.cover)
        self.assertEqual(merged.field_sources['title'], 'books_tw')
        self.assertEqual(merged.identifiers, {'kadokawa_tw':TW,'books_tw':'0011234567'})
        self.assertEqual(a.title, original_title)

    def test_fallback_preference_never_crosses_isbn(self):
        a = Record('openbd', JP, '日文原書', ['日作者'], JP, cover='https://cover.openbd.jp/one.jpg')
        b = Record('kadokawa_tw', TW, '台灣翻譯', ['日作者'], TW, cover='https://img.shoplineapp.com/tw.jpg')
        result = combine([a,b], {'cover': 'kadokawa_tw'})
        self.assertEqual(len(result), 2)
        self.assertEqual([r.cover for r in result], [a.cover,b.cover])

    def test_missing_preferred_source_falls_back_with_provenance(self):
        a = Record('ncl_tw', TW, '官方書名', ['官方作者'], TW)
        b = Record('books_tw', '0011234567', '書店書名', ['書店作者'], TW, cover='https://im1.book.com.tw/c.jpg')
        row = combine([a,b], {'cover':'kadokawa_tw'})[0]
        self.assertEqual(row.field_sources['cover'], 'books_tw')
        self.assertEqual(row.cover, b.cover)

    def test_conflicting_volume_at_same_isbn_rejects_merge(self):
        a = Record('kadokawa_tw', TW, '天空軌跡 (1)', ['作者'], TW, language='zho')
        b = Record('books_tw', '0011234567', '天空軌跡 (2)', ['作者'], TW, language='zho')
        with self.assertRaisesRegex(ValueError, '卷次'):
            combine([a, b])

    def test_conflicting_languages_at_same_isbn_rejects_merge(self):
        a = Record('openbd', JP, '日文原书', ['作者'], JP, language='jpn')
        b = Record('bangumi', '123456', '错误书目', ['作者'], JP, language='zho')
        with self.assertRaisesRegex(ValueError, '语言'):
            combine([a, b])


class BangumiRelationsTests(unittest.TestCase):
    def test_text_and_numeric_novel_categories_are_accepted(self):
        for category in ('小说', '小說', '小説', 1002):
            with self.subTest(category=category):
                rec = bangumi.parse_detail(dict(BGM_SAMPLE, platform=category))
                self.assertIsNotNone(rec)
        self.assertIsNone(bangumi.parse_detail(dict(BGM_SAMPLE, platform='漫画')))
        class Fake:
            def json(self, url, payload):
                return {'data':[{'type':1,'id':123456,'platform':'小说'},
                                {'type':1,'id':123457,'platform':'漫画'}]}
        self.assertEqual(bangumi.search(Fake(), '天空', 2), ['123456'])

    def test_bangumi_series_relation_only_from_verified_series(self):
        class Fake:
            def json(self, url, payload=None):
                if url.endswith('/subjects/123456/subjects'):
                    return [ {'id':222222, 'type':1, 'relation':'单行本', 'name':'天空轨迹'},
                             {'id':333333, 'type':2, 'relation':'改编', 'name':'动画'}]
                if url.endswith('/subjects/222222'):
                    return dict(BGM_SAMPLE, id=222222, name='空の軌跡',
                                name_cn='天空軌跡 系列', series=True, infobox=[])
                raise AssertionError('Unexpected URL '+url)
        rec = bangumi.parse_detail(BGM_SAMPLE)
        updated = bangumi.enrich_series(Fake(), rec)
        self.assertEqual(updated.series_subject_id, '222222')
        self.assertEqual(updated.series, '天空軌跡 系列')
        self.assertEqual(updated.series_index, 1)
        self.assertEqual(len(updated.relations),1)

    def test_related_adaptation_or_unverified_series_does_not_override(self):
        class Fake:
            def json(self, url, payload=None):
                return [{'id':333333,'type':2,'relation':'改编','name':'动画'},
                        {'id':444444,'type':1,'relation':'续集','name':'续篇'}]
        rec = bangumi.parse_detail(BGM_SAMPLE)
        old = rec.series
        self.assertEqual(bangumi.enrich_series(Fake(),rec).series_subject_id, '')
        self.assertEqual(rec.series, old)


class NCLImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('ncl_import_test_module', ROOT / 'tools' / 'import_ncl.py')
        cls.importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.importer)

    def test_official_csv_index_then_readonly_isbn_and_title_lookup(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            csv_path = root/'202610.csv'
            with csv_path.open('w', encoding='utf-8-sig', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(('書名','作者','出版單位','預計出版年月','ISBN'))
                writer.writerow(('天空軌跡 (1)', '作者甲', '台灣角川', '2026/10', TW))
                writer.writerow(('日文原書', '作者乙', '日本社', '2026/10', JP))
                writer.writerow(('錯誤書號', '作者丙', '其他社', '2026', '9780000000000'))
            index = root/'ncl.sqlite'
            self.assertEqual(self.importer.build([csv_path],index),2)
            rows = ncl_tw.query(index, code=TW)
            self.assertEqual([r.isbn for r in rows],[TW])
            self.assertEqual(rows[0].publisher,'台灣角川')
            self.assertEqual(rows[0].pubdate,'')  # Month-only is not a publication date.
            self.assertEqual(ncl_tw.query(index,title='天空軌跡')[0].isbn,TW)
            self.assertEqual(ncl_tw.query(index,code='9780000000000'),[])
            with self.assertRaisesRegex(ValueError,'已存在'):
                self.importer.build([csv_path],index)
            self.assertEqual(self.importer.build([csv_path],index,replace=True),2)

    def test_missing_csv_headers_and_database_are_refused(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            csv_path = root/'bad.csv'
            csv_path.write_text('foo,bar\na,b\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'ISBN'):
                self.importer.build([csv_path],root/'index.sqlite')
            self.assertFalse((root/'index.sqlite').exists())
            with self.assertRaisesRegex(ValueError,'未找到'):
                ncl_tw.query(root/'none.sqlite',code=TW)

    def test_official_ncl_column_names_and_prepublication_date(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            csv_path = root / 'books.csv'
            with csv_path.open('w', encoding='cp950', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(('ISBN', '申請書名', '作者', '出版機構', '預訂出版日'))
                writer.writerow((TW, '魔法使 (1)', '台灣作者', '台灣角川', '2026/10/22'))
            path = root / 'index.sqlite'
            self.assertEqual(self.importer.build([csv_path], path), 1)
            rec = ncl_tw.query(path, code=TW)[0]
            self.assertEqual(rec.title, '魔法使 (1)')
            self.assertEqual(rec.publisher, '台灣角川')
            self.assertEqual(rec.date_text, '2026/10/22')
            self.assertEqual(rec.pubdate, '')  # A projected date is not a confirmed publication date.

    def test_saved_ncl_index_can_supply_metadata_without_network_access(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            csv_path = root / 'books.csv'
            csv_path.write_text('ISBN,申請書名,作者,出版機構,預訂出版日\n'
                                + TW + ',天空軌跡 (1),作者甲,台灣角川,2026/10\n',
                                encoding='utf-8-sig')
            db = root / 'ncl.sqlite'
            self.importer.build([csv_path], db)
            class NoNetworkClient:
                def __init__(self, abort, timeout, request_timeout):
                    self.abort = abort
                def check(self):
                    assert not self.abort.is_set()
                def text(self, url):
                    raise AssertionError('Unexpected HTTP request: ' + url)
                def json(self, url, payload=None):
                    raise AssertionError('Unexpected HTTP request: ' + url)
                def read(self, url):
                    raise AssertionError('Unexpected HTTP request: ' + url)
            settings = dict(ncl_index_path=str(db), enable_ncl_tw=True,
                            enable_bangumi=False, enable_books_tw=False,
                            enable_kadokawa_tw=False, enable_spp_tw=False,
                            enable_openbd=False, enable_ndl=False)
            results = Engine(settings, NoNetworkClient).identify(
                None, threading.Event(), title='无关的书名', identifiers={'isbn':TW})
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].isbn, TW)
            self.assertEqual(results[0].publisher, '台灣角川')
            self.assertFalse(results[0].pubdate)


if __name__ == '__main__':
    unittest.main()
