# SPDX-License-Identifier: Apache-2.0
"""Read-only, bounded HTTP client for authenticated Douban book pages."""

from copy import copy
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from http.cookies import SimpleCookie, CookieError
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin
from urllib.request import (Request, HTTPRedirectHandler, HTTPCookieProcessor,
                            build_opener)

from .core import (AccessBlocked, Cancelled, DoubanError, LoginRequired,
                   parse_account, parse_personal_record,
                   subject_id_from_identifiers)


TRUSTED_HOSTS = frozenset(("www.douban.com", "book.douban.com",
                           "accounts.douban.com", "sec.douban.com"))
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def _allowed_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in TRUSTED_HOSTS
                and parsed.port in (None, 443) and not parsed.username
                and not parsed.password)
    except ValueError:
        return False


class _DoubanCookiePolicy(DefaultCookiePolicy):
    def set_ok(self, cookie, request):
        domain = cookie.domain.lstrip(".").lower()
        return (domain in TRUSTED_HOSTS | {"douban.com"}
                and _allowed_url(request.full_url)
                and super().set_ok(cookie, request))

    def return_ok(self, cookie, request):
        return (_allowed_url(request.full_url)
                and cookie.domain.lstrip(".").lower() in TRUSTED_HOSTS | {"douban.com"}
                and super().return_ok(cookie, request))


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not _allowed_url(target):
            raise DoubanError("豆瓣返回了不受支持的跳转，本次请求已停止。")
        request = super().redirect_request(req, fp, code, msg, headers, target)
        if request is not None:
            request.remove_header("Cookie")
            request.remove_header("Authorization")
        return request


def _new_jar(source=None, cookie_header=None):
    jar = CookieJar(policy=_DoubanCookiePolicy(
        strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain,
    ))
    if source is not None:
        for original in source:
            if original.domain.lstrip(".").lower() in TRUSTED_HOSTS | {"douban.com"}:
                cookie = copy(original)
                cookie.secure = True
                jar.set_cookie(cookie)
    if cookie_header:
        if not isinstance(cookie_header, str) or len(cookie_header) > 65536 or any(
            char in cookie_header for char in ("\r", "\n", "\x00")
        ):
            raise DoubanError("Cookie 格式无效，请只粘贴 Cookie 的值。")
        text = re.sub(r"^Cookie\s*:\s*", "", cookie_header.strip(), flags=re.I)
        parsed = SimpleCookie()
        try:
            parsed.load(text)
        except CookieError:
            raise DoubanError("Cookie 格式无效，请只粘贴 Cookie 的值。") from None
        if not parsed:
            raise DoubanError("没有识别到有效 Cookie，请重新复制。")
        for name, morsel in parsed.items():
            jar.set_cookie(Cookie(
                version=0, name=name, value=morsel.coded_value,
                port=None, port_specified=False,
                domain=".douban.com", domain_specified=True, domain_initial_dot=True,
                path="/", path_specified=True, secure=True, expires=None,
                discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
            ))
    return jar


class DoubanClient:
    def __init__(self, cookie_jar=None, cookie_header=None, cancel_event=None,
                 timeout=20, min_interval=1.5):
        self.cookie_jar = _new_jar(cookie_jar, cookie_header)
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.timeout = max(1.0, min(float(timeout), 60.0))
        self.min_interval = max(0.0, float(min_interval))
        self._last_request = 0.0
        self._opener = build_opener(_SafeRedirect(), HTTPCookieProcessor(self.cookie_jar))
        self._opener.addheaders = [
            ("User-Agent", _USER_AGENT),
            ("Accept", "text/html,application/xhtml+xml"),
            ("Accept-Language", "zh-CN,zh;q=0.9"),
        ]

    def _check_cancel(self):
        if self.cancel_event.is_set():
            raise Cancelled("已取消读取；未应用本次结果。")

    def _get(self, url):
        self._check_cancel()
        if not _allowed_url(url):
            raise DoubanError("请求地址不属于受支持的豆瓣页面。")
        delay = self.min_interval - (time.monotonic() - self._last_request)
        if delay > 0 and self.cancel_event.wait(delay):
            self._check_cancel()
        self._last_request = time.monotonic()
        try:
            request = Request(url, method="GET")
            with self._opener.open(request, timeout=self.timeout) as response:
                final_url = response.geturl()
                if not _allowed_url(final_url):
                    raise DoubanError("豆瓣返回了不受支持的跳转，本次请求已停止。")
                status = getattr(response, "status", 200)
                if status in (403, 429):
                    raise AccessBlocked("豆瓣暂时限制访问，请稍后再试。")
                if status >= 400:
                    raise DoubanError("豆瓣页面暂时无法读取，请稍后再试。")
                parsed = urlsplit(final_url)
                if parsed.hostname == "accounts.douban.com":
                    raise LoginRequired("豆瓣登录已失效，请重新登录。")
                if parsed.hostname == "sec.douban.com":
                    raise AccessBlocked("豆瓣要求安全验证，请在登录窗口完成验证后重试。")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise DoubanError("豆瓣返回的页面过大，已停止读取。")
        except HTTPError as error:
            if error.code in (403, 429):
                raise AccessBlocked("豆瓣暂时限制访问，请稍后再试。") from None
            if error.code == 401:
                raise LoginRequired("豆瓣登录已失效，请重新登录。") from None
            raise DoubanError("豆瓣页面暂时无法读取，请稍后再试。") from None
        except (URLError, TimeoutError, OSError):
            raise DoubanError("连接豆瓣失败或超时，请检查网络后重试。") from None
        self._check_cancel()
        return body, final_url

    def verify_account(self):
        body, final_url = self._get("https://www.douban.com/mine/")
        return parse_account(body, final_url)

    def fetch_record(self, subject_id, expected_account_id):
        subject_id = subject_id_from_identifiers({"douban": subject_id})
        if subject_id is None:
            raise DoubanError("该书没有豆瓣条目 ID。")
        body, final_url = self._get("https://book.douban.com/subject/%s/" % subject_id)
        parsed = urlsplit(final_url)
        if parsed.hostname != "book.douban.com" or parsed.path.rstrip("/") != "/subject/" + subject_id:
            raise DoubanError("豆瓣返回的图书与请求不一致，请核对条目 ID。")
        return parse_personal_record(body, subject_id, expected_account_id)
