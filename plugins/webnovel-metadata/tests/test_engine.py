"""Lookup regressions at the network boundary, without a Calibre installation."""

import json
from pathlib import Path
import tempfile
import threading
import unittest

from support import SOURCE  # Register the pure-module namespace.
from webnovel_metadata.engine import MetadataEngine
from webnovel_metadata.models import BookRef
from webnovel_metadata.network import (
    AccessRestricted, Cancelled, DeadlineExceeded, FetchError, Payload,
)
from webnovel_metadata.providers import search_urls


FIXTURES = Path(__file__).with_name("fixtures")
QM = BookRef("qimao", "123456")
QD = BookRef("qidian", "1012345678")
FQ = BookRef("fanqie", "7123456789012345678")


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def settings(**changes):
    result = {"enable_qidian": False, "enable_qimao": True, "enable_fanqie": False}
    result.update(changes)
    return result


class ScriptedClients:
    """An injected HTTP boundary; unexpected requests fail the test immediately."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.created = []
        self.lock = threading.Lock()

    def __call__(self, provider, budget):
        owner = self
        with self.lock:
            self.created.append((provider, budget))

        class Client:
            def __init__(self):
                self.budget = budget

            def fetch(self, url, **kwargs):
                budget.check()
                with owner.lock:
                    owner.calls.append((provider, url))
                if url not in owner.routes:
                    raise AssertionError("Unexpected metadata request: " + url)
                value = owner.routes[url]
                if callable(value):
                    value = value()
                if isinstance(value, Exception):
                    raise value
                return value if isinstance(value, Payload) else Payload(value.encode("utf-8"), url)

        return Client()


class EngineTests(unittest.TestCase):
    def run_lookup(self, routes, configuration=None, abort=None, **query):
        clients = ScriptedClients(routes)
        messages = []
        books = MetadataEngine(configuration or settings(), clients).identify(
            messages.append, abort or threading.Event(), **query
        )
        return books, clients, messages

    def test_explicit_id_selects_only_that_book_even_if_local_title_has_changed(self):
        books, clients, _ = self.run_lookup(
            {QM.url: fixture("qimao.html")},
            identifiers={"qimao": QM.book_id}, title="我的自定书名", authors=["自定作者"],
        )
        self.assertEqual([book.ref for book in books], [QM])
        self.assertEqual(clients.calls, [("qimao", QM.url)])

    def test_failed_explicit_id_does_not_search_another_book(self):
        books, clients, _ = self.run_lookup(
            {QM.url: FetchError("详情暂时不可用")},
            configuration=settings(enable_qidian=True, enable_fanqie=True),
            identifiers={"qimao": QM.book_id}, title="山海拾遗",
        )
        self.assertEqual(books, [])
        self.assertEqual(clients.calls, [("qimao", QM.url)])
        self.assertEqual([provider for provider, _ in clients.created], ["qimao"])

    def test_invalid_or_conflicting_explicit_identifiers_make_no_requests(self):
        identifiers = [
            {"qimao": "not-a-number"},
            {"qimao": QD.url},
            {"qimao": QM.book_id, "url": "https://www.qimao.com/shuku/654321/"},
        ]
        for values in identifiers:
            with self.subTest(identifiers=values):
                books, clients, messages = self.run_lookup({}, identifiers=values, title="山海拾遗")
                self.assertEqual(books, [])
                self.assertEqual(clients.created, [])
                self.assertTrue(messages)

    def test_conflicting_title_url_does_not_override_identifier(self):
        books, clients, _ = self.run_lookup(
            {}, identifiers={"qimao": QM.book_id},
            title="https://www.qimao.com/shuku/654321/",
        )
        self.assertEqual(books, [])
        self.assertEqual(clients.created, [])

    def test_cancelled_lookup_and_disabled_source_do_not_contact_network(self):
        abort = threading.Event()
        abort.set()
        books, clients, _ = self.run_lookup({}, abort=abort, title="山海拾遗")
        self.assertEqual(books, [])
        self.assertEqual(clients.created, [])
        books, clients, _ = self.run_lookup(
            {}, configuration=settings(enable_qimao=False), identifiers={"qimao": QM.book_id},
        )
        self.assertEqual(books, [])
        self.assertEqual(clients.created, [])

    def test_isbn_alone_and_unknown_author_do_not_trigger_broad_search(self):
        books, clients, _ = self.run_lookup(
            {}, identifiers={"isbn": "9780000000000"}, authors=["Unknown", "佚名"],
        )
        self.assertEqual(books, [])
        self.assertEqual(clients.created, [])

    def test_same_title_wrong_author_is_rejected_before_returning_candidates(self):
        other = BookRef("qimao", "654321")
        search = search_urls("qimao", "山海拾遗")[0]
        payload = json.dumps({"data": {"search_list": [
            {"book_id": other.book_id}, {"book_id": QM.book_id},
        ]}})
        books, clients, _ = self.run_lookup(
            {search: payload,
             other.url: fixture("qimao.html").replace(QM.book_id, other.book_id).replace("青川", "另一个人"),
             QM.url: fixture("qimao.html")},
            title="山海拾遗（完结）.epub", authors=["青川"],
        )
        self.assertEqual([book.ref for book in books], [QM])
        self.assertEqual(len(clients.calls), 3)

    def test_detail_request_count_is_limited_even_when_search_returns_many(self):
        search = search_urls("qimao", "山海拾遗")[0]
        ids = [str(100000 + index) for index in range(10)]
        routes = {search: json.dumps({"data": {"search_list": [{"book_id": value} for value in ids]}})}
        for value in ids[:2]:
            routes[BookRef("qimao", value).url] = fixture("qimao.html").replace(QM.book_id, value)
        books, clients, _ = self.run_lookup(
            routes, configuration=settings(max_candidates=2), title="山海拾遗", authors=["青川"],
        )
        self.assertEqual([book.ref.book_id for book in books], ids[:2])
        self.assertEqual(len(clients.calls), 3)

    def test_valid_saved_html_is_offline_and_does_not_change_work_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "qimao-123456.html").write_text(fixture("qimao.html"), encoding="utf-8")
            books, clients, _ = self.run_lookup(
                {}, configuration=settings(saved_html_dir=directory), identifiers={"qimao": QM.book_id},
            )
        self.assertEqual([book.ref for book in books], [QM])
        self.assertEqual(books[0].published_at, "")
        self.assertEqual(clients.calls, [])

    def test_wrong_saved_html_never_silently_falls_back_to_network(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "qimao-123456.html").write_text(
                fixture("qimao.html").replace(QM.book_id, "654321"), encoding="utf-8",
            )
            books, clients, messages = self.run_lookup(
                {}, configuration=settings(saved_html_dir=directory), identifiers={"qimao": QM.book_id},
            )
        self.assertEqual(books, [])
        self.assertEqual(clients.calls, [])
        self.assertTrue(any("不一致" in message for message in messages))

    def test_later_timeout_or_access_restriction_retains_first_valid_result(self):
        other = BookRef("qimao", "654321")
        search = search_urls("qimao", "山海拾遗")[0]
        payload = json.dumps({"data": {"search_list": [
            {"book_id": QM.book_id}, {"book_id": other.book_id}, {"book_id": "777777"},
        ]}})
        for failure in (DeadlineExceeded("时间已到"), AccessRestricted("稍后重试")):
            with self.subTest(failure=type(failure).__name__):
                books, clients, _ = self.run_lookup(
                    {search: payload, QM.url: fixture("qimao.html"), other.url: failure},
                    title="山海拾遗", authors=["青川"],
                )
                self.assertEqual([book.ref for book in books], [QM])
                self.assertEqual(len(clients.calls), 3)

    def test_user_cancellation_discards_partial_results(self):
        abort = threading.Event()
        other = BookRef("qimao", "654321")
        search = search_urls("qimao", "山海拾遗")[0]

        def cancel():
            abort.set()
            return Cancelled("已取消")

        books, clients, _ = self.run_lookup(
            {search: json.dumps({"data": {"search_list": [
                {"book_id": QM.book_id}, {"book_id": other.book_id},
            ]}}), QM.url: fixture("qimao.html"), other.url: cancel},
            title="山海拾遗", authors=["青川"], abort=abort,
        )
        self.assertEqual(books, [])
        self.assertEqual(len(clients.calls), 3)

    def test_parallel_platform_workers_share_one_lookup_budget(self):
        books, clients, _ = self.run_lookup(
            {QM.url: fixture("qimao.html"), QD.url: fixture("qidian_desktop.html"),
             FQ.url: fixture("fanqie.html")},
            configuration=settings(enable_qidian=True, enable_fanqie=True),
            identifiers={"qidian": QD.book_id, "qimao": QM.book_id, "fanqie": FQ.book_id},
            timeout=17,
        )
        self.assertEqual([book.ref for book in books], [QD, QM, FQ])
        self.assertEqual(len(clients.created), 3)
        self.assertEqual(len({id(budget) for _, budget in clients.created}), 1)

    def test_unexpected_provider_failure_preserves_other_platform_results(self):
        books, _, messages = self.run_lookup(
            {QM.url: RuntimeError("unexpected decoder failure"), FQ.url: fixture("fanqie.html")},
            configuration=settings(enable_fanqie=True),
            identifiers={"qimao": QM.book_id, "fanqie": FQ.book_id},
        )
        self.assertEqual([book.ref for book in books], [FQ])
        self.assertTrue(messages)


if __name__ == "__main__":
    unittest.main()
