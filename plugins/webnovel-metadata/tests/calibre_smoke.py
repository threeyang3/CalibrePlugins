"""Offline smoke checks using an installed ZIP and the real Calibre runtime.

First build/install the ZIP into an isolated CALIBRE_CONFIG_DIRECTORY, then run:
    calibre-debug -e tests/calibre_smoke.py

HTTP is replaced with compact fixtures. Passing this script validates Calibre
integration, not live platform availability. No library or ebook is opened.
"""

import json
import os
from pathlib import Path
from queue import Queue
from threading import Event


def main():
    if not os.environ.get("CALIBRE_CONFIG_DIRECTORY"):
        raise SystemExit("Set CALIBRE_CONFIG_DIRECTORY to an isolated test configuration before running.")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qt.core import QApplication, QColor, QImage
    from calibre.constants import __version__
    from calibre.customize.ui import metadata_plugins
    from calibre.ebooks.metadata.sources.base import create_log
    from calibre.ebooks.metadata.sources.covers import Worker, process_result
    from calibre.utils.img import image_to_data
    import calibre_plugins.webnovel_metadata as plugin
    import calibre_plugins.webnovel_metadata.engine as engine
    from calibre_plugins.webnovel_metadata.network import FetchError, Payload

    fixtures = Path(__file__).resolve().parent / "fixtures"
    books = {
        "qidian": ("1012345678", "qidian_desktop.html", "星河旅人", "风与河"),
        "qimao": ("123456", "qimao.html", "山海拾遗", "青川"),
        "fanqie": ("7123456789012345678", "fanqie.html", "漫长的归途", "北风"),
    }
    requests = []
    checks = []
    app = QApplication.instance() or QApplication([])
    image = QImage(120, 180, QImage.Format.Format_RGB32)
    image.fill(QColor("#5c89bc"))
    cover_bytes = image_to_data(image, fmt="PNG")

    class FixtureClient:
        def __init__(self, provider, budget):
            self.provider, self.budget = provider, budget

        def fetch(self, url, cover=False, referer=None):
            self.budget.check()
            requests.append((self.provider, url, cover))
            if cover:
                if url.endswith("/expired.jpg"):
                    raise FetchError("Expired cover fixture.")
                return Payload(cover_bytes, url, "image/png")
            identity, fixture, title, author = books[self.provider]
            if "/so/" in url:
                source = '<a href="https://www.qidian.com/book/{}/">{}</a>'.format(identity, title)
                return Payload(source.encode("utf-8"), url, "text/html")
            if "/search/" in url:
                key = "search_list" if self.provider == "qimao" else "search_book_data_list"
                data = {"code": 0, "data": {key: [{"book_id": identity}]}}
                return Payload(json.dumps(data).encode("utf-8"), url, "application/json")
            return Payload((fixtures / fixture).read_bytes(), url, "text/html; charset=utf-8")

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        print("PASS", label)

    candidates = [p for p in metadata_plugins(["identify"]) if p.name == "WebNovel Metadata"]
    if len(candidates) != 1:
        raise SystemExit("Install the built WebNovelMetadata.zip into the test configuration first.")
    source = candidates[0]
    saved_prefs = {option.name: source.prefs[option.name] for option in source.options}
    saved_prefs["ignore_fields"] = list(source.prefs["ignore_fields"])
    original_engine_client, original_plugin_client = engine.NetworkClient, plugin.NetworkClient
    log = create_log()

    try:
        # Use reproducible options, restoring this isolated profile afterwards.
        for option in source.options:
            source.prefs[option.name] = option.default
        engine.NetworkClient = FixtureClient
        plugin.NetworkClient = FixtureClient

        widget = source.config_widget()
        widget.commit()
        check("real Qt config widget and preference commit", len(widget.widgets) == len(source.options))

        for provider, (identity, fixture, title, author) in books.items():
            queue = Queue()
            source.identify(log, queue, Event(), identifiers={provider: identity}, timeout=20)
            check(provider + " identify result count", queue.qsize() == 1)
            result = queue.get_nowait()
            check(provider + " real Metadata values",
                  result.title == title and result.authors == [author] and result.languages == ["zho"])
            check(provider + " identifier round trip",
                  source.id_from_url(source.get_book_url(result.identifiers)[2]) == (provider, identity))
            check(provider + " cover cached before publication", bool(source.get_cached_cover_url(result.identifiers)))
            check(provider + " personal rating and date not invented", result.rating is None and result.pubdate is None)
            book, = source.identify_books(log, Event(), identifiers={provider: identity}, timeout=20)
            check(provider + " structured result and synopsis-only comments",
                  book.ref.book_id == identity and result.comments == plugin.comments_html(book)
                  and "作品 ID：" not in result.comments and "字数：" not in result.comments)
            covers = Queue()
            source.download_cover(log, covers, Event(), identifiers={provider: identity}, timeout=20, get_best_cover=True)
            check(provider + " cover download through Source", covers.qsize() == 1)
            normalized = process_result(log, covers.get_nowait())
            check(provider + " real Calibre image pipeline", normalized and normalized[1:3] == (120, 180))

        queue = Queue()
        source.identify(log, queue, Event(), title="星河旅人", authors=["风与河"], timeout=20)
        check("search candidate matching across three platforms",
              queue.qsize() == 1 and queue.get_nowait().identifiers == {"qidian": books["qidian"][0]})

        queue = Queue()
        source.identify(log, queue, Event(), title="星河旅人", authors=["错误作者"], timeout=20)
        check("conflicting author search rejected", queue.empty())

        before = len(requests)
        abort = Event()
        abort.set()
        queue = Queue()
        source.identify(log, queue, abort, identifiers={"qidian": books["qidian"][0]}, timeout=20)
        check("cancellation produces no network requests", queue.empty() and len(requests) == before)

        source.cache_identifier_to_cover_url("qidian:88", "https://bookcover.yuewen.com/qidian88.jpg")
        source.cache_identifier_to_cover_url("qimao:88", "https://cdn.qimao.com/qimao88.jpg")
        check("identical IDs on different platforms keep separate covers",
              source.get_cached_cover_url({"qidian": "88"}) != source.get_cached_cover_url({"qimao": "88"}))

        covers = Queue()
        worker = Worker(source, Event(), None, None,
                        {"qidian": books["qidian"][0], "qimao": books["qimao"][0]},
                        20, covers, get_best_cover=True)
        worker.run()
        check("real Calibre Worker forwards best-cover request",
              source.can_get_multiple_covers and covers.qsize() == 1)

        expired = "https://bookcover.yuewen.com/expired.jpg"
        source.cache_identifier_to_cover_url("qidian:" + books["qidian"][0], expired)
        before = len(requests)
        covers = Queue()
        source.download_cover(log, covers, Event(), identifiers={"qidian": books["qidian"][0]},
                              timeout=20, get_best_cover=True)
        recent = requests[before:]
        check("expired cover cache is refreshed from the same book",
              covers.qsize() == 1 and sum(1 for item in recent if item[2]) == 2
              and any(not item[2] for item in recent)
              and source.get_cached_cover_url({"qidian": books["qidian"][0]}) != expired)

        source.prefs["enable_qidian"] = False
        before = len(requests)
        covers = Queue()
        source.download_cover(log, covers, Event(), identifiers={"qidian": books["qidian"][0]}, timeout=20)
        check("disabled platform does not fetch even with cached cover", covers.empty() and len(requests) == before)
        print("PASSED {} assertions using real Calibre {}; fixture HTTP only.".format(len(checks), __version__))
    finally:
        engine.NetworkClient, plugin.NetworkClient = original_engine_client, original_plugin_client
        for key, value in saved_prefs.items():
            source.prefs[key] = value
        # Keep the QApplication alive until every Qt widget has been used.
        app.processEvents()


if __name__ == "__main__":
    main()
