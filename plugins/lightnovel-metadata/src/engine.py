"""Bounded multisource discovery; no library writes and no background work."""
import re
from urllib.parse import urlsplit
from .models import combine, isbn, norm, relevance, clean, FIELD_NAMES, SOURCES
from .network import Client, FetchError, allowed
from .providers import bangumi, books_tw, ndl, openbd, kadokawa_tw, spp_tw, ncl_tw

SOURCE_NAMES = {'bangumi': 'Bangumi', 'books_tw': '博客来（台湾）',
                'kadokawa_tw': '台灣角川', 'spp_tw': '尖端出版',
                'ncl_tw': '台湾国家图书馆开放书目',
                'ndl': '日本国立国会图书馆', 'openbd': 'openBD（日本）'}


def explicit_sources(title, identifiers):
    identifiers = identifiers or {}
    ids = {}
    for key, pattern in (('bangumi', r'[1-9][0-9]{0,11}'),
                         ('books_tw', r'001[0-9]{7}'),
                         ('spp_tw', r'[1-9][0-9]{4,11}'),
                         ('kadokawa_tw', r'[0-9]{13}')):
        raw = identifiers.get(key)
        if raw is not None and str(raw).strip():
            value = str(raw).strip()
            if not re.fullmatch(pattern, value) or (key == 'kadokawa_tw' and isbn(value) != value):
                raise ValueError('%s 标识符无效。' % SOURCE_NAMES[key])
            ids[key] = value
    for raw in (title, identifiers.get('url')):
        if not isinstance(raw, str) or not raw.startswith('https://'):
            continue
        parsed = urlsplit(raw.strip())
        if parsed.username or parsed.password or parsed.port:
            continue
        key = None
        sid = None
        if parsed.hostname in ('bgm.tv', 'bangumi.tv', 'chii.in'):
            match = re.fullmatch(r'/subject/([1-9][0-9]{0,11})/?', parsed.path)
            key = 'bangumi'
            sid = match.group(1) if match else None
        elif parsed.hostname == 'www.books.com.tw':
            sid = books_tw.product_id(raw.split('?', 1)[0])
            key = 'books_tw'
        elif parsed.hostname == 'www.kadokawa.com.tw':
            sid = kadokawa_tw.isbn_from_url(raw)
            key = 'kadokawa_tw'
        elif parsed.hostname == 'www.spp.com.tw':
            sid = spp_tw.product_id(raw)
            key = 'spp_tw'
        if sid:
            if key in ids and ids[key] != sid:
                raise ValueError('URL 与已填写的 %s 标识符冲突。' % SOURCE_NAMES[key])
            ids[key] = sid
    code = ''
    if identifiers.get('isbn'):
        code = isbn(identifiers['isbn'])
        if not code:
            raise ValueError('ISBN 校验失败。')
    if 'kadokawa_tw' in ids:
        if code and code != ids['kadokawa_tw']:
            raise ValueError('台湾角川商品 ISBN 与已填写 ISBN 冲突。')
        code = ids['kadokawa_tw']
    return ids, code


class Engine:
    def __init__(self, settings=None, client_factory=Client):
        self.settings = settings or {}
        self.client_factory = client_factory

    def _log(self, log, msg):
        if log is not None:
            getattr(log, 'info', log)(msg)

    def identify(self, log, abort, title=None, authors=None, identifiers=None, timeout=30):
        try:
            ids, code = explicit_sources(title, identifiers)
        except ValueError as e:
            self._log(log, str(e))
            return []
        title = clean(title)
        is_url = title.startswith('https://')
        search_query = '' if is_url else re.sub(r'\.(epub|azw3|mobi|pdf|txt)$', '', title, flags=re.I)
        if not (ids or code or search_query):
            self._log(log, '需要书名、有效 ISBN 或支持的条目 URL/ID。')
            return []
        try:
            max_hits = max(1, min(6, int(self.settings.get('max_candidates', 3))))
        except (ValueError, TypeError, OverflowError):
            max_hits = 3
        try:
            request_timeout = max(1, min(20, float(self.settings.get('request_timeout', 7))))
        except (ValueError, TypeError, OverflowError):
            request_timeout = 7
        client = self.client_factory(abort, timeout, request_timeout)
        found = []
        direct = bool(ids)

        def attempt(provider, desc, call):
            if not self.settings.get('enable_' + provider, True):
                return None
            try:
                client.check()
                return call()
            except (FetchError, ValueError, OSError) as e:
                self._log(log, '%s %s：%s' % (SOURCE_NAMES[provider], desc, str(e)))
                return None
            except Exception as e:
                self._log(log, '%s %s：结构处理失败（%s）。' % (SOURCE_NAMES[provider], desc, type(e).__name__))
                return None

        # Explicit site IDs have priority. Do not fall back to a homonymous work.
        for provider, sid in ids.items():
            if abort.is_set():
                return []
            loaders = {'bangumi': bangumi.detail, 'books_tw': books_tw.detail,
                       'kadokawa_tw': kadokawa_tw.detail, 'spp_tw': spp_tw.detail}
            rec = attempt(provider, '精确条目', lambda: loaders[provider](client, sid))
            if rec:
                found.append(rec)
                if provider == 'bangumi' and self.settings.get('resolve_bangumi_series', True):
                    attempt('bangumi', '关联系列', lambda rec=rec: bangumi.enrich_series(client, rec))

        if not direct and not code and search_query:
            # Bangumi can supply an original Japanese title for cross-lingual discovery.
            matches = attempt('bangumi', '搜索', lambda: bangumi.search(client, search_query, max_hits)) or []
            for sid in matches:
                rec = attempt('bangumi', '条目', lambda sid=sid: bangumi.detail(client, sid))
                if rec and relevance(rec, search_query, authors) is not None:
                    found.append(rec)
                    if self.settings.get('resolve_bangumi_series', True):
                        attempt('bangumi', '关联系列', lambda rec=rec: bangumi.enrich_series(client, rec))
            tw_queries = [search_query]
            for rec in found:
                if rec.source == 'bangumi' and rec.title and norm(rec.title) != norm(search_query):
                    tw_queries.append(rec.title)
                    break
            seen_tw = set()
            for q in tw_queries[:2]:
                ids_tw = attempt('books_tw', '搜索', lambda q=q: books_tw.search(client, q, max_hits)) or []
                for pid in ids_tw:
                    if pid in seen_tw:
                        continue
                    seen_tw.add(pid)
                    rec = attempt('books_tw', '商品', lambda pid=pid: books_tw.detail(client, pid))
                    if rec and (relevance(rec, q, authors) is not None or relevance(rec, search_query, authors) is not None):
                        found.append(rec)
            jp_title = search_query
            for rec in found:
                if rec.source == 'bangumi' and rec.original_title and norm(rec.original_title) != norm(search_query):
                    jp_title = rec.original_title
                    break
            books = attempt('ndl', '题名搜索', lambda: ndl.search(client, title=jp_title, limit=max_hits)) or []
            found.extend(rec for rec in books if relevance(rec, jp_title, authors) is not None)

        # ISBN lookup is edition-specific. Discover Japanese ISBNs in NDL and openBD;
        # only a Taiwan Books.com.tw product match may establish a Taiwan ISBN.
        isbn_pool = set([code] if code else [])
        isbn_pool.update(rec.isbn for rec in found if rec.isbn)
        if code and not direct and code.startswith(('978626', '978986', '978957')):
            # Bookstore search returns product IDs, not ISBNs; validate the actual detail ISBN.
            ids_tw = attempt('books_tw', 'ISBN 搜索', lambda: books_tw.search(client, code, max_hits)) or []
            for pid in ids_tw:
                rec = attempt('books_tw', '商品', lambda pid=pid: books_tw.detail(client, pid))
                if rec and rec.isbn == code:
                    found.append(rec)
        if code and not direct and not code.startswith(('978626', '978986', '978957')):
            found.extend(attempt('ndl', 'ISBN', lambda: ndl.search(client, isbn_value=code, limit=3)) or [])
        # Taiwan official publisher pages: only exact ISBN URLs, no guessed
        # keyword search or product IDs. Different SKUs may have different ISBNs.
        tw_codes = sorted(v for v in isbn_pool if v.startswith(('978626', '978986', '978957')))[:max_hits]
        for number in tw_codes:
            if not (direct and 'kadokawa_tw' in ids and ids['kadokawa_tw'] == number):
                rec = attempt('kadokawa_tw', 'ISBN', lambda number=number: kadokawa_tw.detail(client, number))
                if rec:
                    found.append(rec)

        # NCL is an optional OFFLINE indexed data set; no automatic CSV download.
        ncl_path = clean(self.settings.get('ncl_index_path', ''))
        if ncl_path and self.settings.get('enable_ncl_tw', True):
            ncl_codes = sorted(isbn_pool)
            if code and code not in ncl_codes:
                ncl_codes.append(code)
            if ncl_codes:
                for number in ncl_codes[:max_hits]:
                    recs = attempt('ncl_tw', '本地 ISBN', lambda number=number: ncl_tw.query(ncl_path, code=number)) or []
                    found.extend(recs)
            elif not direct and search_query:
                recs = attempt('ncl_tw', '本地书名', lambda: ncl_tw.query(ncl_path, title=search_query, limit=max_hits)) or []
                found.extend(r for r in recs if relevance(r, search_query, authors) is not None)

        # Don't attempt Japanese openBD for Taiwanese ISBNs; bound follow-up requests.
        jp_codes = sorted(v for v in isbn_pool if v.startswith('9784'))[:max_hits]
        for number in jp_codes:
            rec = attempt('openbd', 'ISBN', lambda number=number: openbd.detail(client, number))
            if rec:
                found.append(rec)
        if abort.is_set():
            return []
        if code:
            found = [r for r in found if r.isbn == code]
        if not self.settings.get('include_series_entries', False):
            found = [r for r in found if not r.work_level]
        seen, unique = set(), []
        for r in found:
            key = (r.source, r.source_id)
            if key not in seen:
                unique.append(r)
                seen.add(key)
        # An unsafe/unsupported cover URL is not a usable candidate. Drop it
        # *before* applying per-field preference so another source's valid
        # edition-identical cover can be selected instead.
        for r in unique:
            if r.cover and not allowed(r.cover, image=True):
                r.cover = ''
        # Source records can only be fused on a checksum-valid, identical ISBN.
        try:
            result = combine(unique, {field: self.settings.get('pref_' + field, 'auto') for field in FIELD_NAMES})
        except ValueError as error:
            # Inconsistent source identities must be shown independently, not fused.
            self._log(log, '不同条目声称相同 ISBN，但来源 ID 存在冲突；已禁止融合：%s' % error)
            result = unique
        if not code and not direct:
            result.sort(key=lambda r: (relevance(r, search_query, authors) or (2, 1.0),
                                       (['kadokawa_tw','spp_tw','books_tw','ncl_tw','bangumi','openbd','ndl'].index(r.source) if r.source in SOURCE_NAMES else 99)))
        else:
            result.sort(key=lambda r: (0 if r.isbn == code and code else 1,
                                       (['kadokawa_tw','spp_tw','books_tw','ncl_tw','bangumi','openbd','ndl'].index(r.source) if r.source in SOURCE_NAMES else 99)))
        return result[:max_hits * 3]
