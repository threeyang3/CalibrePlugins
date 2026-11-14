"""Calibre metadata source for Chinese web novels."""

import html
import re
import time
from datetime import datetime, timezone
from queue import Empty, Queue

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Option, Source

from .engine import MetadataEngine, bounded_int, explicit_refs
from .network import FetchError, NetworkClient, RequestBudget, allowed_url, is_image
from .providers import PROVIDERS, make_ref, parse_book_url


def publication_datetime(value):
    """Require an explicit full publication date; never infer missing precision."""
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:[T ]|$)", value):
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
        if len(value.strip()) == 10:
            result = result.replace(hour=12)
    return result


def comments_html(book):
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", book.description or "") if part.strip()]
    return "\n".join("<p>" + html.escape(part).replace("\n", "<br />") + "</p>" for part in paragraphs)


class WebNovelMetadata(Source):
    name = "WebNovel Metadata"
    description = "从起点、七猫、番茄获取网文元数据和封面；支持官网作品 ID、链接及书名检索。"
    author = "threeyang3"
    version = (0, 2, 0)
    minimum_calibre_version = (5, 0, 0)
    supported_platforms = ["windows", "osx", "linux"]
    capabilities = frozenset(("identify", "cover"))
    touched_fields = frozenset((
        "title", "authors", "comments", "tags", "pubdate", "languages",
        "identifier:qidian", "identifier:qimao", "identifier:fanqie",
    ))
    has_html_comments = True
    prefer_results_with_isbn = False
    can_get_multiple_covers = True
    cached_cover_url_is_reliable = False
    options = (
        Option("enable_qidian", "bool", True, "启用起点中文网", "使用起点公开作品页和搜索页。"),
        Option("enable_qimao", "bool", True, "启用七猫中文网", "使用七猫公开作品页和官网搜索接口。"),
        Option("enable_fanqie", "bool", True, "启用番茄小说", "番茄搜索可能受限，建议填写作品 ID 或完整链接。"),
        Option("max_candidates", "number", 5, "每个平台最多核对的候选数", "范围 1–10，默认 5；越大请求越多。"),
        Option("request_timeout", "number", 10, "单次网络请求超时（秒）", "范围 1–30；同时受 Calibre 本次查询总时间限制。"),
        Option("max_covers", "number", 3, "最多下载的候选封面数", "范围 1–5；只要最佳封面时仅返回一张。"),
        Option("include_tags", "bool", True, "获取作品分类标签", "采用来源页中本作品的类型和题材标签。"),
        Option("include_status_tag", "bool", False, "添加连载状态标签", "例如 连载状态:已完结；不代表个人阅读状态。"),
        Option("saved_html_dir", "string", "", "浏览器已保存详情页目录（可选）", "填写本地目录；文件名为 qidian-作品ID.html、qimao-作品ID.html 或 fanqie-作品ID.html。同名文件优先于在线抓取，更新时请替换或移走。"),
    )

    def _settings(self):
        return {option.name: self.prefs[option.name] for option in self.options}

    def get_book_urls(self, identifiers):
        result = []
        for provider in PROVIDERS:
            ref = make_ref(provider, (identifiers or {}).get(provider))
            if ref:
                result.append((provider, ref.book_id, ref.url))
        return result

    def get_book_url(self, identifiers):
        urls = self.get_book_urls(identifiers)
        return urls[0] if urls else None

    def get_book_url_name(self, idtype, idval, url):
        return PROVIDERS.get(idtype, self.name)

    def id_from_url(self, url):
        ref = parse_book_url(url)
        return (ref.provider, ref.book_id) if ref else None

    def get_cached_cover_url(self, identifiers):
        for provider, value, unused in self.get_book_urls(identifiers):
            cached = self.cached_identifier_to_cover_url(provider + ":" + value)
            if cached and allowed_url(cached, provider, cover=True):
                return cached
        return None

    def test_fields(self, mi):
        # Publication date and categories are optional; any one platform ID is sufficient.
        for field in ("title", "authors"):
            if mi.is_null(field):
                return field
        if not self.get_book_url(mi.identifiers):
            return "identifier"
        return None

    def identify_results_keygen(self, title=None, authors=None, identifiers=None):
        return lambda mi: getattr(mi, "source_relevance", 0)

    def identify_books(self, log, abort, title=None, authors=None, identifiers=None, timeout=30):
        return MetadataEngine(self._settings()).identify(log, abort, title, authors, identifiers, timeout)

    def metadata_for_book(self, book):
        settings = self._settings()
        mi = Metadata(book.title, list(book.authors))
        mi.set_identifier(book.ref.provider, book.ref.book_id)
        mi.languages = ["zho"]
        mi.comments = comments_html(book) or None
        tags = list(book.tags) if settings["include_tags"] else []
        if settings["include_status_tag"] and book.serialization_status:
            tags.append("连载状态:" + book.serialization_status)
        mi.tags = list(dict.fromkeys(tags))
        published = publication_datetime(book.published_at)
        if published is not None:
            mi.pubdate = published
        mi.has_cover = bool(book.cover_url and allowed_url(book.cover_url, book.ref.provider, cover=True))
        self.clean_downloaded_metadata(mi)
        return mi

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers=None, timeout=30):
        books = self.identify_books(log, abort, title, authors, identifiers, timeout)
        for index, book in enumerate(books):
            if abort.is_set():
                return
            mi = self.metadata_for_book(book)
            mi.source_relevance = index
            if mi.has_cover:
                self.cache_identifier_to_cover_url(book.ref.provider + ":" + book.ref.book_id, book.cover_url)
            result_queue.put(mi)

    def download_cover(self, log, result_queue, abort, title=None, authors=None, identifiers=None,
                       timeout=30, get_best_cover=False):
        settings = self._settings()
        budget = RequestBudget(timeout, abort, bounded_int(settings["request_timeout"], 10, 1, 30))
        limit = 1 if get_best_cover else bounded_int(settings["max_covers"], 3, 1, 5)
        attempted, delivered = set(), set()

        def download(ref):
            key = ref.provider + ":" + ref.book_id
            if key in delivered or not settings.get("enable_" + ref.provider, True):
                return
            url = self.cached_identifier_to_cover_url(key)
            if not url or (key, url) in attempted:
                return
            attempted.add((key, url))
            try:
                response = NetworkClient(ref.provider, budget).fetch(url, cover=True, referer=ref.url)
                if not is_image(response.data):
                    raise FetchError("封面响应不是支持的图片，可能是验证页。")
                budget.check()
                result_queue.put((self, response.data))
                delivered.add(key)
            except (ValueError, OSError) as error:
                log.info("{}封面：{}".format(PROVIDERS[ref.provider], error))

        try:
            budget.check()
            refs, unused = explicit_refs(identifiers, title)
            for ref in refs:
                download(ref)
                if len(delivered) >= limit:
                    return
            # A signed CDN URL may have expired; one fresh identification can replace it.
            budget.check()
            if refs and len(delivered) == len(refs):
                return
            queue = Queue()
            self.identify(log, queue, abort, title, authors, identifiers,
                          timeout=max(0, budget.deadline - time.monotonic()))
            while len(delivered) < limit and not abort.is_set():
                try:
                    mi = queue.get_nowait()
                except Empty:
                    break
                for provider, value, unused in self.get_book_urls(mi.identifiers):
                    download(make_ref(provider, value))
                    if len(delivered) >= limit:
                        return
        except (ValueError, OSError) as error:
            log.info(str(error))
