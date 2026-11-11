"""Search orchestration independent of Calibre's UI and library database."""

import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

from .network import (
    AccessRestricted, Cancelled, DeadlineExceeded, FetchError, MAX_HTML_BYTES,
    NetworkClient, Payload, RequestBudget,
)
from .providers import (
    PROVIDERS, detail_urls, make_ref, parse_book_url, parse_detail, parse_search, search_urls,
)


def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in value if char.isalnum())


def clean_query(title):
    text = str(title or "").strip()
    text = re.sub(r"\.(?:epub|txt|mobi|azw3|pdf)$", "", text, flags=re.I)
    return re.sub(r"\s*[（(【\[]\s*(?:完结|完本|全本|完整版|精校版)\s*[）)】\]]\s*$", "", text).strip()


def known_authors(authors):
    return [str(author).strip() for author in (authors or [])
            if normalize(author) not in ("", "unknown", "未知", "佚名", "作者不详")]


def relevance(book, title=None, authors=None):
    """Known conflicting authors are rejected, even for exactly equal titles."""
    authors = known_authors(authors)
    if authors and not ({normalize(a) for a in authors} & {normalize(a) for a in book.authors}):
        return None
    query, found = normalize(clean_query(title)), normalize(book.title)
    if not query:
        return (0, 0) if authors else None
    if query == found:
        return (0, 0)
    score = SequenceMatcher(None, query, found).ratio()
    if score < 0.84:
        return None
    return (1, round(1.0 - score, 6))


def explicit_refs(identifiers=None, title=None):
    refs = {}
    supplied = False

    def add(ref):
        old = refs.get(ref.provider)
        if old and old != ref:
            raise ValueError("同一平台的作品 ID 与链接不一致，请核对后再获取。")
        refs[ref.provider] = ref

    for provider in PROVIDERS:
        value = (identifiers or {}).get(provider)
        if value is not None and str(value).strip():
            supplied = True
            ref = make_ref(provider, value)
            if not ref:
                raise ValueError("{} 标识符无效；请填写数字作品 ID 或该平台详情页链接。".format(PROVIDERS[provider]))
            add(ref)
    for value in ((identifiers or {}).get("url"), (identifiers or {}).get("uri"), title):
        ref = parse_book_url(value) if isinstance(value, str) else None
        if ref:
            supplied = True
            add(ref)
    return list(refs.values()), supplied


def bounded_int(value, default, low, high):
    try:
        return min(high, max(low, int(value)))
    except (ValueError, TypeError, OverflowError):
        return default


class MetadataEngine:
    def __init__(self, settings=None, client_factory=None):
        self.settings = settings or {}
        self.client_factory = client_factory or NetworkClient
        self._log_lock = threading.Lock()

    def log(self, log, message):
        if log is not None:
            with self._log_lock:
                getattr(log, "info", log)(message)

    def load_book(self, client, ref, log=None):
        directory = str(self.settings.get("saved_html_dir", "") or "").strip()
        if directory:
            path = Path(directory).expanduser() / (ref.provider + "-" + ref.book_id + ".html")
            if path.is_file():
                client.budget.check()
                with path.open("rb") as stream:
                    data = stream.read(MAX_HTML_BYTES + 1)
                if len(data) > MAX_HTML_BYTES:
                    raise FetchError("已保存的 HTML 超过 4 MiB 上限。")
                # A mismatching or damaged saved file must not silently fetch another book.
                book = parse_detail(Payload(data, ref.url).text(), ref, final_url=ref.url)
                self.log(log, "{}：采用本地保存的详情页 {}-{}.html。".format(PROVIDERS[ref.provider], ref.provider, ref.book_id))
                return book
        last_error = None
        for url in detail_urls(ref):
            client.budget.check()
            try:
                response = client.fetch(url)
                return parse_detail(response.text(), ref, final_url=response.url)
            except (AccessRestricted, Cancelled, DeadlineExceeded):
                raise
            except (ValueError, OSError) as error:
                last_error = error
        raise FetchError(str(last_error) if last_error else "未取得作品详情。")

    def _provider_books(self, provider, refs, title, authors, budget, log):
        client = self.client_factory(provider, budget)
        limit = bounded_int(self.settings.get("max_candidates", 5), 5, 1, 10)
        direct = refs is not None
        if not direct:
            query = clean_query(title) or " ".join(known_authors(authors))
            refs = []
            for url in search_urls(provider, query):
                budget.check()
                try:
                    response = client.fetch(url)
                    refs = parse_search(response.text(), provider, response.url)
                    if refs:
                        break
                except (AccessRestricted, Cancelled, DeadlineExceeded):
                    raise
                except (ValueError, OSError) as error:
                    self.log(log, "{}搜索：{}".format(PROVIDERS[provider], error))
            if not refs:
                self.log(log, "{}：未取得可用搜索结果；可填写官网作品 ID / URL 后重试。".format(PROVIDERS[provider]))
        books, seen = [], set()
        for ref in refs[:limit]:
            key = (ref.provider, ref.book_id)
            if key in seen:
                continue
            seen.add(key)
            try:
                budget.check()
                book = self.load_book(client, ref, log)
                if direct or relevance(book, title, authors) is not None:
                    books.append(book)
            except Cancelled:
                return []
            except (AccessRestricted, DeadlineExceeded) as error:
                self.log(log, "{}：{}".format(PROVIDERS[provider], error))
                break
            except (ValueError, OSError) as error:
                self.log(log, "{} {}：{}".format(PROVIDERS[provider], ref.book_id, error))
        return books

    def identify(self, log, abort, title=None, authors=None, identifiers=None, timeout=30):
        budget = RequestBudget(timeout, abort, bounded_int(self.settings.get("request_timeout", 10), 10, 1, 30))
        try:
            budget.check()
            refs, direct = explicit_refs(identifiers, title)
        except (ValueError, Cancelled, DeadlineExceeded) as error:
            self.log(log, str(error))
            return []
        if not direct and not normalize(clean_query(title)) and not known_authors(authors):
            self.log(log, "请提供书名、作者或支持的平台作品 ID / URL；ISBN 无法定位网络连载版本。")
            return []
        enabled = [provider for provider in PROVIDERS if self.settings.get("enable_" + provider, True)]
        tasks = {provider: ([ref for ref in refs if ref.provider == provider] if direct else None)
                 for provider in enabled}
        if direct:
            tasks = {provider: values for provider, values in tasks.items() if values}
        if not tasks:
            self.log(log, "没有启用对应的数据源，请检查插件配置。")
            return []
        books = []
        # A maximum of three short-lived workers; every request shares one deadline.
        with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="webnovel") as pool:
            futures = {pool.submit(self._provider_books, provider, values, title, authors, budget, log): provider
                       for provider, values in tasks.items()}
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    books.extend(future.result())
                except (ValueError, OSError) as error:
                    self.log(log, "{}：{}".format(PROVIDERS[provider], error))
                except Exception as error:
                    # Isolate a platform parser regression without losing other sources.
                    self.log(log, "{}解析失败（{}）；其他来源继续处理。".format(
                        PROVIDERS[provider], type(error).__name__))
        if abort.is_set():
            return []
        order = {provider: index for index, provider in enumerate(PROVIDERS)}
        books.sort(key=lambda book: ((0, 0) if direct else relevance(book, title, authors),
                                    order[book.ref.provider], book.ref.book_id))
        return books
