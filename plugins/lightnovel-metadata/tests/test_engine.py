import threading
import unittest
from support import SRC
from test_models import JP, TW
from test_providers import BGM_SAMPLE
from lightnovel_metadata.engine import Engine
from lightnovel_metadata.network import FetchError
from lightnovel_metadata.providers import bangumi, books_tw, ndl, openbd


class FixtureClient:
    def __init__(self, abort, timeout, request_timeout, routes, calls):
        self.abort, self.routes, self.calls = abort, routes, calls
    def check(self):
        if self.abort.is_set():
            raise FetchError('Cancelled')
    def json(self, url, payload=None):
        self.check()
        self.calls.append(('json', url))
        value = self.routes.get(('json', url))
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise FetchError('network unavailable')
        return value
    def text(self, url):
        self.check()
        self.calls.append(('text', url))
        value = self.routes.get(('text', url))
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise FetchError('network unavailable')
        return value
    def read(self, url):
        self.check()
        self.calls.append(('read', url))
        value = self.routes.get(('read', url))
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise FetchError('network unavailable')
        return value


class EngineIntegrationTests(unittest.TestCase):
    def run_lookup(self, routes, settings=None, **query):
        calls, messages = [], []
        opts = {'enable_bangumi': True, 'enable_books_tw': False,
                'enable_openbd': False, 'enable_ndl': False,
                'enable_kadokawa_tw': False, 'enable_spp_tw': False,
                'resolve_bangumi_series': False}
        opts.update(settings or {})
        factory = lambda abort, timeout, request_timeout: FixtureClient(abort, timeout, request_timeout, routes, calls)
        rows = Engine(opts, factory).identify(messages.append, threading.Event(), **query)
        return rows, calls, messages

    def test_explicit_bangumi_id_only_hits_requested_subject(self):
        routes = {('json', 'https://api.bgm.tv/v0/subjects/123456'): BGM_SAMPLE}
        rows, calls, logs = self.run_lookup(routes, identifiers={'bangumi': '123456'}, title='私人改名')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].identifiers['bangumi'], '123456')
        self.assertEqual(calls, [('json', 'https://api.bgm.tv/v0/subjects/123456')])

    def test_wrong_explicit_id_does_not_fall_back_to_title(self):
        routes = {('json', 'https://api.bgm.tv/v0/subjects/123456'): dict(BGM_SAMPLE, id=888888)}
        rows, calls, logs = self.run_lookup(routes, identifiers={'bangumi': '123456'}, title='天空轨迹')
        self.assertEqual(rows, [])
        self.assertEqual(len(calls), 1)
        self.assertTrue(logs)

    def test_tw_isbn_does_not_query_openbd(self):
        # Search unsuccessful, but no Japanese ISBN endpoint should be queried.
        rows, calls, logs = self.run_lookup({}, settings={'enable_books_tw': True, 'enable_ndl': True,
                                                          'enable_openbd': True},
                                           identifiers={'isbn': TW})
        self.assertEqual(rows, [])
        self.assertEqual(calls, [('text', books_tw.SEARCH.format(TW))])

    def test_isbn_results_reject_wrong_editions(self):
        xml = f'''<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
        <item><title>天空轨迹 (1)</title><dc:identifier>ISBN:{JP}</dc:identifier></item>
        <item><title>天空轨迹 (1)</title><dc:identifier>ISBN:{TW}</dc:identifier></item>
        </channel></rss>'''.encode()
        routes = {('read', ndl.url_for(isbn_value=JP, count=3)): xml,
                  ('json', openbd.BASE + JP): [{'summary': {'isbn': JP, 'title': '天空轨迹 (1)',
                                        'author': '青空', 'publisher': '角川'}}]}
        rows, calls, logs = self.run_lookup(routes, settings={'enable_ndl': True, 'enable_openbd': True},
                                           identifiers={'isbn': JP})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].isbn, JP)
        self.assertIn('openbd', rows[0].source_labels)
        self.assertIn('ndl', rows[0].source_labels)
        self.assertEqual(len(calls), 2)

    def test_title_search_and_bangumi_match(self):
        url = 'https://api.bgm.tv/v0/search/subjects?limit=6&offset=0'
        routes = {('json', url): {'data': [{'id': 123456, 'type': 1, 'platform': 1002}]},
                  ('json', 'https://api.bgm.tv/v0/subjects/123456'): BGM_SAMPLE}
        rows, calls, logs = self.run_lookup(routes, title='天空轨迹（1）')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].isbn, JP)
        self.assertEqual(len(calls), 2)

    def test_cancelled_does_no_requests(self):
        calls = []
        aborted = threading.Event()
        aborted.set()
        factory = lambda abort, timeout, request_timeout: FixtureClient(abort, timeout, request_timeout, {}, calls)
        result = Engine({}, factory).identify(None, aborted, title='任何作品')
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

    def test_invalid_settings_get_safe_defaults(self):
        rows, calls, logs = self.run_lookup({}, {'max_candidates': 'bad', 'request_timeout': None}, title='天空轨迹')
        self.assertEqual(rows, [])
        self.assertTrue(logs)

if __name__ == '__main__':
    unittest.main()
