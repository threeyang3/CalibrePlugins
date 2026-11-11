"""HTTP boundaries: redirects, bounded reads, cancellation and honest failures."""

import gzip
import io
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request

from support import SOURCE  # Register the pure-module namespace.
from webnovel_metadata import network
from webnovel_metadata.network import (
    AccessRestricted, Cancelled, DeadlineExceeded, FetchError, NetworkClient,
    Payload, RequestBudget, _CheckedRedirect, allowed_url, is_image,
)


PAGE = "https://www.qimao.com/shuku/123456/"


class Response(io.BytesIO):
    def __init__(self, data=b"metadata", url=PAGE, headers=None, status=200, after_read=None):
        super().__init__(data)
        self.url, self.headers, self.status = url, headers or {}, status
        self.read_calls = 0
        self.after_read = after_read

    def geturl(self):
        return self.url

    def read1(self, size=-1):
        self.read_calls += 1
        data = super().read(size)
        if self.after_read:
            self.after_read()
        return data


class NetworkTests(unittest.TestCase):
    def client(self, provider="qimao", abort=None, timeout=30):
        return NetworkClient(provider, RequestBudget(timeout, abort or threading.Event(), 10))

    def fetch_response(self, response, client=None, **kwargs):
        opener = Mock()
        opener.open.return_value = response
        with patch.object(network, "build_opener", return_value=opener):
            result = (client or self.client()).fetch(PAGE, **kwargs)
        return result, opener

    def test_page_and_cover_allowlists_are_platform_specific(self):
        self.assertTrue(allowed_url("https://m.qidian.com/book/123/", "qidian"))
        self.assertTrue(allowed_url("https://bookcover.yuewen.com/qdbimg/123/600", "qidian", True))
        self.assertTrue(allowed_url("https://cdn.wtzw.com/bookimg/cover.jpg", "qimao", True))
        self.assertTrue(allowed_url("https://p9-novel-sign.byteimg.com/cover.image?x-signature=a%2Bb", "fanqie", True))
        invalid = [
            ("https://fanqienovel.com/page/123", "qidian", False),
            ("https://bookcover.yuewen.com/cover.jpg", "qimao", True),
            ("https://cdn.qimao.com.evil.invalid/cover.jpg", "qimao", True),
            ("https://evilqimao.com/cover.jpg", "qimao", True),
            ("http://127.0.0.1/cover.jpg", "qimao", True),
            ("https://localhost/", "qidian", False),
            ("file:///tmp/cover.jpg", "qimao", True),
            ("https://user:secret@www.qimao.com/shuku/123/", "qimao", False),
            ("https://@www.qimao.com/shuku/123/", "qimao", False),
            ("https://www.qimao.com:443/shuku/123/", "qimao", False),
            ("https://www.qimao.com/\nshuku/123/", "qimao", False),
        ]
        for url, provider, cover in invalid:
            with self.subTest(url=url):
                self.assertFalse(allowed_url(url, provider, cover))

    def test_disallowed_initial_url_never_builds_an_opener(self):
        with patch.object(network, "build_opener") as build:
            with self.assertRaises(FetchError):
                self.client().fetch("http://127.0.0.1/metadata")
        build.assert_not_called()

    def test_redirect_handler_rechecks_target_and_cancellation(self):
        abort = threading.Event()
        handler = _CheckedRedirect("qidian", False, RequestBudget(30, abort))
        request = Request("https://www.qidian.com/book/123/")
        allowed = handler.redirect_request(request, None, 302, "Found", {}, "https://m.qidian.com/book/123/")
        self.assertEqual(allowed.full_url, "https://m.qidian.com/book/123/")
        for destination in ("https://fanqienovel.com/page/123", "http://127.0.0.1/private"):
            with self.subTest(destination=destination), self.assertRaises(FetchError):
                handler.redirect_request(request, None, 302, "Found", {}, destination)
        abort.set()
        with self.assertRaises(Cancelled):
            handler.redirect_request(request, None, 302, "Found", {}, "https://m.qidian.com/book/123/")

    def test_final_response_address_is_checked_before_reading_body(self):
        response = Response(url="https://fanqienovel.com/page/123")
        with self.assertRaises(FetchError):
            self.fetch_response(response)
        self.assertEqual(response.read_calls, 0)
        self.assertTrue(response.closed)

    def test_non_success_http_status_is_not_parsed_as_metadata(self):
        response = Response(data=b"<script>challenge()</script>", status=202)
        with self.assertRaisesRegex(FetchError, "HTTP 202"):
            self.fetch_response(response)
        self.assertEqual(response.read_calls, 0)

    def test_restriction_is_distinct_and_does_not_expose_error_details(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                opener = Mock()
                opener.open.side_effect = HTTPError(PAGE, status, "private-cookie-value", {}, None)
                with patch.object(network, "build_opener", return_value=opener):
                    with self.assertRaises(AccessRestricted) as raised:
                        self.client().fetch(PAGE)
                self.assertNotIn("private-cookie-value", str(raised.exception))
                self.assertEqual(opener.open.call_count, 1)

    def test_oversized_declared_and_streamed_bodies_are_closed(self):
        for response in (Response(b"small", headers={"Content-Length": "129"}), Response(b"x" * 129)):
            with self.subTest(headers=response.headers), patch.object(network, "MAX_HTML_BYTES", 128):
                with self.assertRaisesRegex(FetchError, "大小上限"):
                    self.fetch_response(response)
                self.assertTrue(response.closed)
                self.assertLessEqual(response.read_calls, 1)

    def test_compressed_expansion_is_bounded(self):
        response = Response(gzip.compress(b"x" * 129), headers={"Content-Encoding": "gzip"})
        with patch.object(network, "MAX_HTML_BYTES", 128):
            with self.assertRaisesRegex(FetchError, "解压.*上限"):
                self.fetch_response(response)
        self.assertTrue(response.closed)

    def test_gzip_and_invalid_length_header_still_return_utf8_metadata(self):
        value = "<h1>山海拾遗</h1>"
        response = Response(gzip.compress(value.encode("utf-8")), headers={
            "Content-Encoding": "gzip", "Content-Length": "invalid", "Content-Type": "text/html; charset=utf-8",
        })
        payload, _ = self.fetch_response(response)
        self.assertEqual(payload.text(), value)
        self.assertTrue(response.closed)

    def test_corrupt_gzip_is_an_isolated_fetch_failure(self):
        data = bytearray(gzip.compress(b"metadata"))
        data[10] = 0x07  # Reserved DEFLATE block type inside an otherwise valid gzip header.
        response = Response(bytes(data), headers={"Content-Encoding": "gzip"})
        with self.assertRaises(FetchError):
            self.fetch_response(response)
        self.assertTrue(response.closed)

    def test_empty_response_does_not_claim_zero_search_results(self):
        for data in (b"", b" \r\n\t"):
            with self.subTest(data=data), self.assertRaisesRegex(FetchError, "空响应.*不视为零条"):
                self.fetch_response(Response(data))

    def test_unsupported_compression_is_reported_as_failure(self):
        with self.assertRaisesRegex(FetchError, "压缩格式"):
            self.fetch_response(Response(b"not-decoded", headers={"Content-Encoding": "br"}))

    def test_each_request_uses_remaining_shared_deadline(self):
        clock = [100.0]
        with patch.object(network.time, "monotonic", side_effect=lambda: clock[0]):
            budget = RequestBudget(5, threading.Event(), request_timeout=10)
            first = NetworkClient("qimao", budget)
            second = NetworkClient("qimao", budget)
            _, opener = self.fetch_response(Response(), client=first)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 5)
            clock[0] = 104.5
            _, opener = self.fetch_response(Response(), client=second)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 0.5)
            clock[0] = 105
            with patch.object(network, "build_opener") as build:
                with self.assertRaises(DeadlineExceeded):
                    second.fetch(PAGE)
                build.assert_not_called()

    def test_per_request_timeout_does_not_exceed_configured_limit(self):
        _, opener = self.fetch_response(Response(), client=self.client(timeout=100))
        self.assertLessEqual(opener.open.call_args.kwargs["timeout"], 10)

    def test_cancellation_during_read_never_returns_partial_payload(self):
        abort = threading.Event()
        response = Response(b"partial-data", after_read=abort.set)
        with self.assertRaises(Cancelled):
            self.fetch_response(response, client=self.client(abort=abort))
        self.assertTrue(response.closed)
        self.assertEqual(response.read_calls, 1)

    def test_signed_cover_query_is_preserved_and_foreign_referer_omitted(self):
        url = "https://p9-novel-sign.byteimg.com/cover.image?x-expires=1900000000&x-signature=a%2Bb%3D"
        opener = Mock()
        opener.open.return_value = Response(b"\xff\xd8\xffimage", url=url)
        with patch.object(network, "build_opener", return_value=opener):
            self.client("fanqie").fetch(url, cover=True, referer="https://www.qimao.com/")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, url)
        self.assertIsNone(request.get_header("Referer"))


class TextAndImageTests(unittest.TestCase):
    def test_utf8_saved_page_wins_over_stale_gbk_declaration(self):
        source = '<meta charset="gbk"><h1>山海拾遗</h1>'
        self.assertEqual(Payload(b"\xef\xbb\xbf" + source.encode("utf-8"), PAGE, "text/html; charset=gbk").text(), source)

    def test_explicit_legacy_encoding_is_supported(self):
        self.assertEqual(Payload("你好".encode("gb18030"), PAGE, "text/html; charset=gb2312").text(), "你好")
        data = '<meta charset="gbk"><h1>你好</h1>'.encode("gb18030")
        self.assertIn("你好", Payload(data, PAGE).text())

    def test_unknown_encoding_is_rejected_instead_of_returning_mojibake(self):
        with self.assertRaisesRegex(FetchError, "编码"):
            Payload(b"\xff\xfe\xfa", PAGE).text()

    def test_malformed_declared_legacy_encoding_has_a_readable_error(self):
        with self.assertRaisesRegex(FetchError, "编码"):
            Payload(b"\xff", PAGE, "text/html; charset=gbk").text()

    def test_html_and_svg_are_not_accepted_as_downloaded_covers(self):
        for data in (b"<html>challenge</html>", b"<svg onload='alert(1)'></svg>", b"not-an-image", b""):
            with self.subTest(data=data):
                self.assertFalse(is_image(data))
        for data in (b"\xff\xd8\xffjpeg", b"\x89PNG\r\n\x1a\npng", b"GIF89a123", b"RIFF1234WEBPimage"):
            with self.subTest(data=data):
                self.assertTrue(is_image(data))


if __name__ == "__main__":
    unittest.main()
