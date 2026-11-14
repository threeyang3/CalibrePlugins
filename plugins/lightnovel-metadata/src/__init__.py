"""LightNovel Metadata -- independent edition metadata source for Calibre."""
import html
import re
from datetime import datetime, timezone
from queue import Empty, Queue

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Option, Source

from .engine import Engine, SOURCE_NAMES, explicit_sources
from .models import isbn
from .network import Client, FetchError, allowed, is_image


SOURCE_PREFERENCE_HELP = 'auto / ' + ' / '.join(SOURCE_NAMES) + '；仅同 ISBN 合并时应用。'


def comments_html(record):
    synopsis = synopsis_html(record)
    blocks = [synopsis] if synopsis else []
    extra = []
    for label, value in (('原名', record.original_title), ('译者', '、'.join(record.translators)),
                         ('插画', '、'.join(record.illustrators)), ('预计出版日（台湾新书预告）' if record.source == 'ncl_tw' else '出版日期（原文）', record.date_text if not record.pubdate else ''),
                         ('系列', record.series)):
        if value:
            extra.append('%s：%s' % (html.escape(label), html.escape(str(value))))
    if record.series_subject_id and re.fullmatch(r'[1-9][0-9]{0,11}', record.series_subject_id):
        extra.append('Bangumi 主系列：<a href="https://bgm.tv/subject/%s">%s</a>' %
                     (record.series_subject_id, record.series_subject_id))
    if record.field_sources:
        sources_for_fields = [('书名', 'title'), ('作者', 'authors'), ('封面', 'cover'),
                              ('出版社', 'publisher'), ('出版日期', 'pubdate'),
                              ('简介', 'description'), ('系列', 'series')]
        details = ['%s → %s' % (label, html.escape(', '.join(SOURCE_NAMES.get(v, v) for v in
                   record.field_sources[key].split(',')))) for label, key in sources_for_fields
                   if record.field_sources.get(key)]
        if details:
            extra.append('字段来源：' + '；'.join(details))
    if extra:
        blocks.append('<p>' + '<br />'.join(extra) + '</p>')
    sources = ', '.join(SOURCE_NAMES.get(v, v) for v in record.source_labels)
    cite = '数据来源：' + html.escape(sources)
    if record.url:
        cite += ' · <a href="%s">查看条目</a>' % html.escape(record.url, quote=True)
    blocks.append('<p>' + cite + '</p>')
    return '\n'.join(blocks)


def synopsis_html(record):
    paragraphs = [html.escape(p.strip()) for p in re.split(r'\n\s*\n', record.description or '') if p.strip()]
    return '\n'.join('<p>%s</p>' % p.replace('\n', '<br />') for p in paragraphs) or None


class LightNovelMetadata(Source):
    name = 'LightNovel Metadata'
    author = 'threeyang3'
    description = '轻小说分卷元数据：Bangumi、台版出版社和书店、NCL 离线书目，以及日本 KADOKAWA、openBD 和 NDL。'
    version = (0, 3, 0)
    minimum_calibre_version = (5, 0, 0)
    supported_platforms = ['windows', 'osx', 'linux']
    capabilities = frozenset(('identify', 'cover'))
    touched_fields = frozenset(('title', 'authors', 'publisher', 'pubdate', 'comments', 'tags',
                                'languages', 'isbn', 'series', 'series_index',
                                'identifier:bangumi', 'identifier:books_tw',
                                'identifier:kadokawa_tw', 'identifier:spp_tw', 'identifier:kadokawa_jp'))
    has_html_comments = True
    cached_cover_url_is_reliable = False
    can_get_multiple_covers = True
    prefer_results_with_isbn = True
    options = (
        Option('enable_bangumi', 'bool', True, '启用 Bangumi', '公开条目及标签；不需要 Token，不获取个人收藏。'),
        Option('enable_books_tw', 'bool', True, '启用博客来（台湾）', '公开印刷书商品页。页面变化时可暂时关闭。'),
        Option('enable_kadokawa_tw', 'bool', True, '启用台灣角川', '有 ISBN 时查询出版社商品页；不猜测套装版商品号。'),
        Option('enable_spp_tw', 'bool', True, '启用尖端出版', '仅根据尖端完整商品链接或商品 ID 获取。'),
        Option('enable_ncl_tw', 'bool', True, '启用 NCL 台湾官方书目', '需要先配置本地 SQLite 索引，不联网下载大数据集。'),
        Option('ncl_index_path', 'string', '', 'NCL 本地书目索引路径', '先运行 tools/import_ncl.py 把官方 CSV 导入 SQLite，然后填写完整路径。'),
        Option('resolve_bangumi_series', 'bool', True, 'Bangumi 系列关联', '从公开关联确认系列，但不自动合并不同 ISBN。'),
        Option('enable_openbd', 'bool', True, '启用 openBD（日本）', '仅通过 ISBN 查询正式出版的日文书目。'),
        Option('enable_ndl', 'bool', True, '启用日本国立国会图书馆', '官方书目 OpenSearch，书名及 ISBN。'),
        Option('enable_kadokawa_jp', 'bool', True, '启用 KADOKAWA（日本）', '核对官网同一 ISBN 版本的书目信息和封面。'),
        Option('include_series_entries', 'bool', False, '允许作品级/系列级条目', '默认不导入 Bangumi 系列总条目，防止错当单卷。'),
        Option('max_candidates', 'number', 3, '单数据源候选上限', '范围 1–6，避免大量请求。'),
        Option('request_timeout', 'number', 7, '单次请求超时秒数', '范围 1–20；也受 Calibre 总时限约束。'),
        Option('pref_title', 'string', 'auto', '书名优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_authors', 'string', 'auto', '作者优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_publisher', 'string', 'auto', '出版社优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_pubdate', 'string', 'auto', '出版日期优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_cover', 'string', 'auto', '封面优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_description', 'string', 'auto', '简介优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_series', 'string', 'auto', '系列优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_tags', 'string', 'auto', '标签优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_illustrators', 'string', 'auto', '插画师优先来源', SOURCE_PREFERENCE_HELP),
        Option('pref_translators', 'string', 'auto', '译者优先来源', SOURCE_PREFERENCE_HELP),
        Option('include_source_comments', 'bool', False, '简介附带出处和出版字段', '仅影响 Calibre 的普通下载。使用轻小说工具栏操作可将下载到的译者等资料写入书目列。'),
    )

    def _settings(self):
        return {option.name: self.prefs[option.name] for option in self.options}

    def get_book_urls(self, identifiers):
        ids = identifiers or {}
        out = []
        if re.fullmatch(r'[1-9][0-9]{0,11}', str(ids.get('bangumi', ''))):
            sid = str(ids['bangumi'])
            out.append(('bangumi', sid, 'https://bgm.tv/subject/' + sid))
        if re.fullmatch(r'001[0-9]{7}', str(ids.get('books_tw', ''))):
            sid = str(ids['books_tw'])
            out.append(('books_tw', sid, 'https://www.books.com.tw/products/' + sid))
        if re.fullmatch(r'97[89][0-9]{10}', str(ids.get('kadokawa_tw', ''))) and isbn(ids['kadokawa_tw']):
            sid = str(ids['kadokawa_tw'])
            out.append(('kadokawa_tw', sid, 'https://www.kadokawa.com.tw/products/' + sid))
        if re.fullmatch(r'[1-9][0-9]{4,11}', str(ids.get('spp_tw', ''))):
            sid = str(ids['spp_tw'])
            out.append(('spp_tw', sid, 'https://www.spp.com.tw/SalePage/Index/' + sid))
        if re.fullmatch(r'[0-9]{12}', str(ids.get('kadokawa_jp', ''))):
            sid = str(ids['kadokawa_jp'])
            out.append(('kadokawa_jp', sid, 'https://www.kadokawa.co.jp/product/' + sid + '/'))
        return out

    def get_book_url(self, identifiers):
        return next(iter(self.get_book_urls(identifiers)), None)

    def get_book_url_name(self, idtype, idval, url):
        return SOURCE_NAMES.get(idtype, self.name)

    def id_from_url(self, url):
        try:
            ids, unused = explicit_sources(url, {})
            return next(iter(ids.items()), None)
        except (ValueError, TypeError):
            return None

    def get_cached_cover_url(self, identifiers):
        ids = identifiers or {}
        keys = ['isbn:' + isbn(ids.get('isbn'))] if isbn(ids.get('isbn')) else []
        keys.extend(k + ':' + value for k, value, unused in self.get_book_urls(ids))
        for key in keys:
            url = self.cached_identifier_to_cover_url(key)
            if url and allowed(url, image=True):
                return url
        return None

    def identify_results_keygen(self, title=None, authors=None, identifiers=None):
        return lambda mi: getattr(mi, 'source_relevance', 0)

    def identify_books(self, log, abort, title=None, authors=None, identifiers=None, timeout=30):
        return Engine(self._settings()).identify(log, abort, title, authors, identifiers, timeout)

    def metadata_for_book(self, record):
        mi = Metadata(record.title, record.authors)
        if record.isbn:
            mi.isbn = record.isbn
            mi.set_identifier('isbn', record.isbn)
        for source, source_id in record.identifiers.items():
            mi.set_identifier(source, source_id)
        mi.publisher = record.publisher or None
        mi.languages = [record.language] if record.language else []
        if record.pubdate:
            mi.pubdate = datetime.strptime(record.pubdate, '%Y-%m-%d').replace(hour=12, tzinfo=timezone.utc)
        if record.series and record.series_index is not None:
            mi.series = record.series
            mi.series_index = record.series_index
        mi.comments = comments_html(record) if self.prefs['include_source_comments'] else synopsis_html(record)
        mi.tags = record.tags
        mi.has_cover = bool(record.cover and allowed(record.cover, image=True))
        self.clean_downloaded_metadata(mi)
        return mi

    def cover_for_book(self, log, abort, record, timeout=15):
        if not record.cover or not allowed(record.cover, image=True) or abort.is_set():
            return None
        client = Client(abort, timeout, self.prefs['request_timeout'])
        return self._read_cover(log, client, record.cover)

    def _read_cover(self, log, client, url):
        try:
            raw = client.read(url, image=True)
            if not is_image(raw):
                raise FetchError('图片响应不是有效的封面文件。')
            return raw
        except (FetchError, ValueError, OSError) as exc:
            log.info('封面下载：%s' % exc)
            return None

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers=None, timeout=30):
        records = self.identify_books(log, abort, title, authors, identifiers, timeout)
        for i, rec in enumerate(records):
            if abort.is_set():
                return
            mi = self.metadata_for_book(rec)
            mi.source_relevance = i
            if mi.has_cover:
                if rec.isbn:
                    self.cache_identifier_to_cover_url('isbn:' + rec.isbn, rec.cover)
                for source, source_id in rec.identifiers.items():
                    self.cache_identifier_to_cover_url(source + ':' + source_id, rec.cover)
            result_queue.put(mi)

    def download_cover(self, log, result_queue, abort, title=None, authors=None, identifiers=None,
                       timeout=30, get_best_cover=False):
        settings = self._settings()
        candidates = []
        url = self.get_cached_cover_url(identifiers)
        if url:
            candidates.append(url)
        if not candidates:
            collected = Queue()
            self.identify(log, collected, abort, title, authors, identifiers, timeout)
            while not abort.is_set():
                try:
                    mi = collected.get_nowait()
                except Empty:
                    break
                url = self.get_cached_cover_url(mi.identifiers)
                if url and url not in candidates:
                    candidates.append(url)
                if len(candidates) >= (1 if get_best_cover else 3):
                    break
        client = Client(abort, timeout, settings.get('request_timeout', 7))
        for url in candidates[:1 if get_best_cover else 3]:
            if abort.is_set() or not allowed(url, image=True):
                return
            raw = self._read_cover(log, client, url)
            if raw:
                result_queue.put((self, raw))
