"""Bounded HTTP reads for public metadata. No login, JS execution or chapter APIs."""

import gzip
import io
import re
import time
import zlib
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_COVER_BYTES = 10 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
PAGE_HOSTS = {
    "qidian": frozenset(("www.qidian.com", "m.qidian.com", "book.qidian.com")),
    "qimao": frozenset(("www.qimao.com", "m.qimao.com")),
    "fanqie": frozenset(("fanqienovel.com", "www.fanqienovel.com")),
}
COVER_DOMAINS = {
    "qidian": ("qpic.cn", "qdmm.com", "yuewen.com", "qidian.com"),
    "qimao": ("qimao.com", "qimao.cn", "kmimg.com", "wtzw.com"),
    "fanqie": ("byteimg.com", "pstatp.com", "douyinpic.com", "fqnovelpic.com", "fanqienovel.com"),
}


class FetchError(ValueError):
    """A concise, safe-to-display request failure."""


class AccessRestricted(FetchError):
    """Do not retry this provider during the current lookup."""


class Cancelled(FetchError):
    pass


class DeadlineExceeded(FetchError):
    pass


class RequestBudget:
    def __init__(self, timeout, abort, request_timeout=10):
        self.abort = abort
        self.deadline = time.monotonic() + max(0.0, float(timeout))
        self.request_timeout = min(30.0, max(1.0, float(request_timeout)))

    def check(self):
        if self.abort.is_set():
            raise Cancelled("已取消获取元数据。")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DeadlineExceeded("已达到本次查询的时间上限。")
        return min(remaining, self.request_timeout)


def allowed_url(url, provider, cover=False):
    """Apply the same allowlist to the initial request and every redirect."""
    if not isinstance(url, str) or not url or re.search(r"[\x00-\x20\x7f]", url):
        return False
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or not parsed.hostname):
            return False
    except ValueError:
        return False
    host = parsed.hostname.lower()
    if not cover:
        return host in PAGE_HOSTS.get(provider, ())
    return any(host == domain or host.endswith("." + domain)
               for domain in COVER_DOMAINS.get(provider, ()))


class _CheckedRedirect(HTTPRedirectHandler):
    max_redirections = 4
    max_repeats = 2

    def __init__(self, provider, cover, budget):
        self.provider, self.cover, self.budget = provider, cover, budget

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        remaining = self.budget.check()
        if not allowed_url(newurl, self.provider, self.cover):
            raise FetchError("网站跳转到了不受支持的地址，已停止。")
        # urllib's redirect handler opens the new request with req.timeout.
        req.timeout = remaining
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Payload:
    data: bytes
    url: str
    content_type: str = ""

    def text(self):
        # UTF-8 first also supports browser-saved pages with stale charset tags.
        try:
            return self.data.decode("utf-8-sig")
        except UnicodeDecodeError:
            declared = self.content_type + " " + self.data[:4096].decode("ascii", "ignore")
            if re.search(r"charset\s*=\s*[\"']?(?:gb18030|gbk|gb2312)", declared, re.I):
                try:
                    return self.data.decode("gb18030")
                except UnicodeDecodeError:
                    pass
            raise FetchError("页面编码无法识别，未采用乱码元数据。")


class NetworkClient:
    """One client per platform worker; no persistent threads or cookie storage."""

    def __init__(self, provider, budget):
        self.provider = provider
        self.budget = budget

    def fetch(self, url, cover=False, referer=None):
        if not allowed_url(url, self.provider, cover):
            raise FetchError("不是该平台允许的公开页面或封面地址。")
        timeout = self.budget.check()
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/*" if cover else "application/json,text/html;q=0.9,*/*;q=0.5",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "Accept-Encoding": "identity",
        }
        if referer and allowed_url(referer, self.provider):
            headers["Referer"] = referer
        limit = MAX_COVER_BYTES if cover else MAX_HTML_BYTES
        opener = build_opener(_CheckedRedirect(self.provider, cover, self.budget))
        try:
            with opener.open(Request(url, headers=headers), timeout=timeout) as response:
                final_url = response.geturl()
                if not allowed_url(final_url, self.provider, cover):
                    raise FetchError("响应地址不属于该平台。")
                status = getattr(response, "status", 200)
                if status != 200:
                    raise FetchError("网站未返回可用内容（HTTP {}）。".format(status))
                try:
                    length = int(response.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length > limit:
                    raise FetchError("响应超过大小上限，已停止下载。")
                chunks, size = [], 0
                read = getattr(response, "read1", response.read)
                while True:
                    self.budget.check()
                    chunk = read(min(65536, limit + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > limit:
                        raise FetchError("响应超过大小上限，已停止下载。")
                data = b"".join(chunks)
                encoding = response.headers.get("Content-Encoding", "").lower()
                if encoding == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                        data = stream.read(limit + 1)
                    if len(data) > limit:
                        raise FetchError("解压后的响应超过大小上限。")
                elif encoding not in ("", "identity"):
                    raise FetchError("网站返回了不支持的压缩格式。")
                self.budget.check()
                if not data.strip():
                    raise FetchError("网站返回空响应，可能需要浏览器验证；不视为零条搜索结果。")
                return Payload(data, final_url, response.headers.get("Content-Type", ""))
        except HTTPError as error:
            error.close()
            if error.code in (401, 403, 429):
                raise AccessRestricted("网站限制访问（HTTP {}）；请稍后重试或使用已保存的详情页。".format(error.code)) from None
            raise FetchError("网站返回 HTTP {}。".format(error.code)) from None
        except (URLError, TimeoutError, OSError, EOFError, zlib.error):
            # Do not log raw headers, signed URLs, proxy credentials or body HTML.
            raise FetchError("网络请求失败或超时，请检查网络连接。") from None


def is_image(data):
    return (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")
            or data.startswith((b"GIF87a", b"GIF89a"))
            or (data.startswith(b"RIFF") and data[8:12] == b"WEBP"))
