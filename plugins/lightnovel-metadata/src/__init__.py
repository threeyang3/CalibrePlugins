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


def comments_html(record):
    blocks = []
    if record.description:
        paragraphs = [html.escape(p.strip()) for p in re.split(r'\n\s*\n', record.description) if p.strip()]
        if paragraphs:
            blocks.extend('<p>%s</p>' % p.replace('\n', '<br />') for p in paragraphs)
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


class LightNovelMetadata(Source):
    name = 'LightNovel Metadata'
    author = 'threeyang3'
    description = '轻小说分卷元数据：Bangumi、台版出版社/书店、NCL 离线书目、日本 openBD/NDL。'
    version = (0, 2, 0)
    minimum_calibre_version = (5, 0, 0)
    supported_platforms = ['windows', 'osx', 'linux']
    capabilities = frozenset(('identify', 'cover'))
    touched_fields = frozenset(('title', 'authors', 'publisher', 'pubdate', 'comments', 'tags',
                                'languages', 'isbn', 'series', 'series_index',
                                'identifier:bangumi', 'identifier:books_tw',
                                'identifier:kadokawa_tw', 'identifier:spp_tw'))
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
        Option('include_series_entries', 'bool', False, '允许作品级/系列级条目', '默认不导入 Bangumi 系列总条目，防止错当单卷。'),
        Option('max_candidates', 'number', 3, '单数据源候选上限', '范围 1–6，避免大量请求。'),
        Option('request_timeout', 'number', 7, '单次请求超时秒数', '范围 1–20；也受 Calibre 总时限约束。'),
        Option('pref_title', 'string', 'auto', '书名优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_authors', 'string', 'auto', '作者优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_publisher', 'string', 'auto', '出版社优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_pubdate', 'string', 'auto', '出版日期优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_cover', 'string', 'auto', '封面优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_description', 'string', 'auto', '简介优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_series', 'string', 'auto', '系列优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_tags', 'string', 'auto', '标签优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_illustrators', 'string', 'auto', '插画师优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('pref_translators', 'string', 'auto', '译者优先来源', 'auto / bangumi / books_tw / kadokawa_tw / spp_tw / ncl_tw / openbd / ndl；仅同 ISBN 合并时应用。'),
        Option('include_source_comments', 'bool', True, '简介附带出处和出版字段', '不包括任何用户评分、读书笔记或收藏状态。'),
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

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers=None, timeout=30):
        settings = self._settings()
        records = Engine(settings).identify(log, abort, title, authors, identifiers, timeout)
        for i, rec in enumerate(records):
            if abort.is_set():
                return
            mi = Metadata(rec.title, rec.authors)
            if rec.isbn:
                mi.isbn = rec.isbn
                # Calibre models ISBN as an identifier; setting it explicitly
                # also makes the cover cache portable across source results.
                mi.set_identifier('isbn', rec.isbn)
            for source, source_id in rec.identifiers.items():
                mi.set_identifier(source, source_id)
            mi.publisher = rec.publisher or None
            mi.languages = [rec.language] if rec.language else []
            if rec.pubdate:
                mi.pubdate = datetime.strptime(rec.pubdate, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            if rec.series and rec.series_index is not None:
                mi.series = rec.series
                mi.series_index = rec.series_index
            mi.comments = comments_html(rec) if settings.get('include_source_comments', True) else (html.escape(rec.description) or None)
            mi.tags = rec.tags
            mi.source_relevance = i
            mi.has_cover = bool(rec.cover and allowed(rec.cover, image=True))
            self.clean_downloaded_metadata(mi)
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
            try:
                raw = client.read(url, image=True)
                if not is_image(raw):
                    raise FetchError('图片响应不是有效的封面文件。')
                result_queue.put((self, raw))
            except (FetchError, ValueError, OSError) as exc:
                log.info('封面下载：%s' % exc)
