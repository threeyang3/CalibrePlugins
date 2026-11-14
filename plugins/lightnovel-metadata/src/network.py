"""Small, bounded HTTP client: public metadata only, fixed hosts, no cookies."""
import gzip
import io
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

META_HOSTS = frozenset(('api.bgm.tv', 'api.openbd.jp', 'ndlsearch.ndl.go.jp',
                        'search.books.com.tw', 'www.books.com.tw', 'www.kadokawa.com.tw', 'www.spp.com.tw'))
IMAGE_HOSTS = ('lain.bgm.tv', 'bgm.tv', 'cover.openbd.jp', 'books.com.tw',
               'book.com.tw', 'ndlsearch.ndl.go.jp', 'kadokawa.com.tw', 'spp.com.tw', 'shoplineimg.com', 'shoplineapp.com')
MAX_META = 3 * 1024 * 1024
MAX_IMAGE = 9 * 1024 * 1024
UA = 'LightNovelMetadata/0.2 (Calibre manual book lookup; https://github.com/threeyang3/CalibrePlugins)'


class FetchError(ValueError):
    pass


def allowed(url, image=False):
    if not isinstance(url, str) or re.search(r'[\x00-\x20\x7f]', url):
        return False
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.username or p.password or p.port or not p.hostname:
            return False
        host = p.hostname.lower()
        if not image:
            return host in META_HOSTS
        return any(host == suffix or host.endswith('.' + suffix) for suffix in IMAGE_HOSTS)
    except ValueError:
        return False


class GuardedRedirect(HTTPRedirectHandler):
    max_redirections = 3
    def __init__(self, image=False):
        self.image = image
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl, self.image):
            raise FetchError('访问被重定向到不允许的域名。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, abort, timeout=30, request_timeout=7):
        self.abort = abort
        self.end = time.monotonic() + max(0, float(timeout))
        self.request_timeout = min(20.0, max(1.0, float(request_timeout)))
        self.calls = 0

    def check(self):
        if self.abort.is_set():
            raise FetchError('用户已取消。')
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise FetchError('达到 Calibre 查询时间上限。')
        return min(remaining, self.request_timeout)

    def read(self, url, payload=None, image=False):
        if not allowed(url, image):
            raise FetchError('拒绝未知域名或不安全的 URL。')
        timeout = self.check()
        headers = {'User-Agent': UA, 'Accept': 'image/*' if image else 'application/json,application/xml,text/xml,text/html;q=0.8',
                   'Accept-Encoding': 'identity', 'Accept-Language': 'zh-TW,ja;q=0.9,zh;q=0.8'}
        if payload is not None:
            if image:
                raise FetchError('封面不允许 POST。')
            headers['Content-Type'] = 'application/json; charset=utf-8'
            payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        limit = MAX_IMAGE if image else MAX_META
        opener = build_opener(GuardedRedirect(image))
        self.calls += 1
        try:
            with opener.open(Request(url, data=payload, headers=headers), timeout=timeout) as response:
                if not allowed(response.geturl(), image):
                    raise FetchError('最终 URL 不在允许列表内。')
                length = response.headers.get('Content-Length', '0')
                if length.isdigit() and int(length) > limit:
                    raise FetchError('响应超过体积上限。')
                data = bytearray()
                while len(data) <= limit:
                    self.check()
                    chunk = response.read(min(65536, limit + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                if len(data) > limit:
                    raise FetchError('响应超过体积上限。')
                encoding = response.headers.get('Content-Encoding', '').lower()
                if encoding == 'gzip':
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                        data = stream.read(limit+1)
                elif encoding not in ('', 'identity'):
                    raise FetchError('不支持的编码格式。')
                if len(data) > limit or not data:
                    raise FetchError('响应为空或超出限制。')
                return bytes(data)
        except HTTPError as e:
            code = e.code
            e.close()
            raise FetchError('服务返回 HTTP %s（可能限流或需要人工验证）。' % code) from None
        except (URLError, TimeoutError, OSError):
            raise FetchError('网络连接失败或超时。') from None

    def json(self, url, payload=None):
        try:
            return json.loads(self.read(url, payload).decode('utf-8-sig'))
        except (UnicodeError, ValueError) as e:
            if isinstance(e, FetchError):
                raise
            raise FetchError('网站未返回可解析的 JSON。') from None

    def text(self, url):
        raw = self.read(url)
        for encoding in ('utf-8-sig', 'big5', 'gb18030'):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise FetchError('页面编码无法识别。')


def is_image(raw):
    return raw.startswith((b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'GIF87a', b'GIF89a')) or (raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')
