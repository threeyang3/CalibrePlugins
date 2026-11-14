"""Simulated Calibre API smoke: package entrypoint and metadata mapping, offline."""
import importlib.util
import sys
import threading
import types
import unittest
from unittest.mock import patch
from queue import Queue
from support import SRC
from test_models import JP
from lightnovel_metadata.models import Record


class SourceStub:
    def __init__(self):
        self.prefs = {x.name: x.default for x in self.options}
        self._cache = {}
    def clean_downloaded_metadata(self, obj):
        pass
    def cache_identifier_to_cover_url(self, key, url):
        self._cache[key] = url
    def cached_identifier_to_cover_url(self, key):
        return self._cache.get(key)


class MetadataStub:
    def __init__(self, title, authors):
        self.title, self.authors = title, authors
        self.identifiers = {}
    def set_identifier(self, key, value):
        self.identifiers[key] = value


class OptionStub:
    def __init__(self, name, kind, default, title, help_text):
        self.name, self.default = name, default


def load_entrypoint():
    previous = {}
    for name in ('calibre', 'calibre.ebooks', 'calibre.ebooks.metadata',
                 'calibre.ebooks.metadata.book', 'calibre.ebooks.metadata.book.base',
                 'calibre.ebooks.metadata.sources', 'calibre.ebooks.metadata.sources.base'):
        previous[name] = sys.modules.get(name)
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    sys.modules['calibre.ebooks.metadata.book.base'].Metadata = MetadataStub
    src = sys.modules['calibre.ebooks.metadata.sources.base']
    src.Source, src.Option = SourceStub, OptionStub
    name = 'lnm_calibre_entry_mock'
    spec = importlib.util.spec_from_file_location(name, SRC / '__init__.py',
                                                  submodule_search_locations=[str(SRC)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        for key, val in previous.items():
            if val is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = val
    return mod


class CalibreContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = load_entrypoint()

    def test_plugin_metadata_fields_and_provenance(self):
        source = self.entry.LightNovelMetadata()
        rec = Record('openbd', JP, '示例作品 (1)', ['作者'], JP,
                     publisher='出版机构', pubdate='2025-04-10',
                     description='内容 <script>alert(1)</script>',
                     cover='https://cover.openbd.jp/mock.jpg',
                     source_labels=['openbd', 'bangumi'],
                     identifiers={'bangumi': '123456'},
                     illustrators=['绘师'], translators=['译者'])
        with patch.object(self.entry.Engine, 'identify', return_value=[rec]):
            q = Queue()
            source.identify(None, q, threading.Event(), title='示例作品 (1)')
        mi = q.get_nowait()
        self.assertEqual(mi.title, '示例作品 (1)')
        self.assertEqual(mi.identifiers, {'isbn': JP, 'bangumi': '123456'})
        self.assertEqual(mi.isbn, JP)
        self.assertEqual(mi.pubdate.year, 2025)
        self.assertEqual(mi.series_index, 1.0)
        self.assertNotIn('<script>', mi.comments)
        self.assertIn('译者', mi.comments)
        self.assertTrue(mi.has_cover)
        self.assertEqual(source.get_book_urls(mi.identifiers)[0][0], 'bangumi')
        self.assertEqual(source.get_cached_cover_url(mi.identifiers), rec.cover)

    def test_no_auto_series_index_on_series_work(self):
        source = self.entry.LightNovelMetadata()
        rec = Record('bangumi', '123456', '长篇作品系列', ['作者'], work_level=True)
        with patch.object(self.entry.Engine, 'identify', return_value=[rec]):
            q = Queue()
            source.identify(None, q, threading.Event(), title='长篇作品系列')
        mi = q.get_nowait()
        self.assertFalse(hasattr(mi, 'series_index'))
        self.assertFalse(mi.has_cover)
        self.assertEqual(source.id_from_url('https://bgm.tv/subject/123456'), ('bangumi', '123456'))

if __name__ == '__main__':
    unittest.main()
