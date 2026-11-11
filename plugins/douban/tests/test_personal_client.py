import importlib
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

PACKAGE = "douban_personal_backend_tests"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "personal")]
    sys.modules[PACKAGE] = package
client = importlib.import_module(PACKAGE + ".client")
core = importlib.import_module(PACKAGE + ".core")


class Response:
    def __init__(self, body=b"<html></html>", url="https://book.douban.com/subject/1234567/", status=200):
        self.body, self.url, self.status = body, url, status

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PersonalClientTests(unittest.TestCase):
    def test_only_read_only_requests_and_timeout(self):
        api = client.DoubanClient(min_interval=0)
        with patch.object(api._opener, "open", return_value=Response()) as opened:
            api._get("https://book.douban.com/subject/1234567/")
            request = opened.call_args[0][0]
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            self.assertEqual(opened.call_args.kwargs["timeout"], 20)

    def test_credentials_never_sent_to_external_or_cleartext_redirect(self):
        redirect = client._SafeRedirect()
        req = Request("https://book.douban.com/subject/1234567/", headers={"Cookie": "secret=x"})
        for target in ("https://attacker.example/", "https://douban.com.attacker.example/",
                       "http://book.douban.com/", "https://book.douban.com:8080/",
                       "https://name:secret@book.douban.com/"):
            with self.assertRaises(core.DoubanError):
                redirect.redirect_request(req, None, 302, "Found", {}, target)
        redirected = redirect.redirect_request(req, None, 302, "Found", {},
                                               "https://www.douban.com/mine/")
        self.assertIsNone(redirected.get_header("Cookie"))

    def test_cookie_jar_has_host_policy_and_no_insecure_requests(self):
        api = client.DoubanClient(cookie_header='dbcl2="123:token"; ck=abc')
        good = Request("https://book.douban.com/subject/1234567/")
        api.cookie_jar.add_cookie_header(good)
        self.assertIn('dbcl2="123:token"', good.get_header("Cookie"))
        for url in ("https://attacker.example/", "https://unknown.douban.com/",
                    "http://book.douban.com/"):
            req = Request(url)
            api.cookie_jar.add_cookie_header(req)
            self.assertIsNone(req.get_header("Cookie"))

    def test_imported_host_only_cookies_keep_their_exact_host(self):
        source = client.CookieJar()
        for name, domain in (("apex_only", "douban.com"), ("www_only", "www.douban.com")):
            source.set_cookie(client.Cookie(
                version=0, name=name, value="value", port=None, port_specified=False,
                domain=domain, domain_specified=False, domain_initial_dot=False,
                path="/", path_specified=True, secure=True, expires=None,
                discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
            ))
        api = client.DoubanClient(cookie_jar=source)
        www = Request("https://www.douban.com/mine/")
        api.cookie_jar.add_cookie_header(www)
        self.assertEqual(www.get_header("Cookie"), "www_only=value")
        for url in ("https://book.douban.com/", "https://accounts.douban.com/", "https://douban.com/"):
            req = Request(url)
            api.cookie_jar.add_cookie_header(req)
            self.assertIsNone(req.get_header("Cookie"))

    def test_manual_cookie_rejects_header_injection(self):
        for cookie in ("dbcl2=x\r\nAuthorization: evil", "not a cookie"):
            with self.assertRaises(core.DoubanError):
                client.DoubanClient(cookie_header=cookie)

    def test_network_error_messages_do_not_expose_secrets(self):
        api = client.DoubanClient(min_interval=0)
        for error, expected in (
            (HTTPError("https://x/?secret", 429, "secret cookie", {}, None), core.AccessBlocked),
            (HTTPError("https://x/?secret", 403, "secret cookie", {}, None), core.AccessBlocked),
            (URLError("secret cookie"), core.DoubanError),
        ):
            with patch.object(api._opener, "open", side_effect=error):
                with self.assertRaises(expected) as caught:
                    api._get("https://book.douban.com/subject/1234567/")
                self.assertNotIn("secret", str(caught.exception))

    def test_cancellation_skips_request_and_delayed_request(self):
        event = threading.Event()
        event.set()
        api = client.DoubanClient(cancel_event=event)
        with patch.object(api._opener, "open") as opened:
            with self.assertRaises(core.Cancelled):
                api.verify_account()
            opened.assert_not_called()

    def test_bounded_response_and_login_redirects(self):
        api = client.DoubanClient(min_interval=0)
        responses = (
            (Response(body=b"x" * (client.MAX_RESPONSE_BYTES + 1)), core.DoubanError),
            (Response(url="https://accounts.douban.com/passport/login"), core.LoginRequired),
            (Response(url="https://sec.douban.com/a"), core.AccessBlocked),
        )
        for response, expected in responses:
            with patch.object(api._opener, "open", return_value=response):
                with self.assertRaises(expected):
                    api._get("https://book.douban.com/subject/1234567/")

    def test_fetch_rejects_changed_subject_even_before_parsing(self):
        api = client.DoubanClient(min_interval=0)
        with patch.object(api, "_get", return_value=(b"<html></html>",
                "https://book.douban.com/subject/7654321/")):
            with self.assertRaises(core.DoubanError):
                api.fetch_record("1234567", "reader")


if __name__ == "__main__":
    unittest.main()
