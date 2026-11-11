"""Platform registry, canonical identities, public search and detail parsing."""

import json
import re
from urllib.parse import quote, urlencode, urljoin, urlsplit

from ..models import BookRef
from . import fanqie, qidian, qimao
from .common import (by_class, class_xpath, clean, document, first, image_url,
                     initial_state, json_roots, meta, publication_date, unique)


PROVIDERS = {'qidian': '起点中文网', 'qimao': '七猫中文网', 'fanqie': '番茄小说'}


def parse_book_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or re.search(r'[\x00-\x20\\]', value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or parts.username is not None or parts.password is not None or parts.port is not None:
            return None
        host = parts.hostname
        provider = ''
        pattern = ''
        if host in ('www.qidian.com', 'm.qidian.com'):
            provider, pattern = 'qidian', r'/book/([0-9]{1,32})/?'
        elif host == 'book.qidian.com':
            provider, pattern = 'qidian', r'/info/([0-9]{1,32})/?'
        elif host == 'www.qimao.com':
            provider, pattern = 'qimao', r'/shuku/([0-9]{1,32})/?'
        elif host == 'fanqienovel.com':
            provider, pattern = 'fanqie', r'/page/([0-9]{1,32})/?'
        match = re.fullmatch(pattern, parts.path) if pattern else None
        return BookRef(provider, match.group(1)) if match else None
    except (ValueError, TypeError):
        return None


def make_ref(provider, value):
    if provider not in PROVIDERS or isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r'[0-9]{1,32}', value):
        return BookRef(provider, value)
    ref = parse_book_url(value)
    return ref if ref and ref.provider == provider else None


def detail_urls(ref):
    urls = [ref.url]
    if ref.provider == 'qidian':
        urls.append('https://m.qidian.com/book/{}/'.format(ref.book_id))
    return urls


def search_urls(provider, query):
    query = clean(query)
    if provider not in PROVIDERS or not query or query in ('.', '..'):
        return []
    encoded = quote(query, safe='')
    if provider == 'qidian':
        # Mobile SSR provides structured search records even if desktop is gated.
        return ['https://m.qidian.com/so/{}.html'.format(encoded),
                'https://www.qidian.com/so/{}.html'.format(encoded)]
    if provider == 'qimao':
        return ['https://www.qimao.com/qimaoapi/api/search/result?' + urlencode({
                    'keyword': query, 'page': 1, 'page_size': 15}),
                'https://www.qimao.com/search/index/?keyword=' + encoded]
    # This is the website's own search endpoint. It can return an empty body
    # under verification; parse_search reports that condition, not zero matches.
    return ['https://fanqienovel.com/api/author/search/search_book/v1?' + urlencode({
                'query_word': query, 'page_count': 10, 'page_index': 0,
                'query_type': 0, 'filter': '127,127,127,127'}),
            'https://fanqienovel.com/search/' + encoded]


def _identity_evidence(root, ref):
    identities = []

    def add_url(value):
        if isinstance(value, str) and value.strip():
            identity = parse_book_url(urljoin(ref.url, value.strip()))
            if identity:
                identities.append(identity)

    for href in root.xpath('//link[contains(concat(" ", normalize-space(@rel), " "), " canonical ")]/@href'):
        add_url(href)
    for key in ('og:url', 'og:novel:book_url', 'og:novel:read_url'):
        add_url(meta(root, key))
    if ref.provider == 'qidian':
        for value in root.xpath('//*[@id="book-detail"]//*[@id="bookImg"]/@data-bid'):
            identity = make_ref('qidian', value)
            if identity:
                identities.append(identity)
        data = qidian.page_data(root)
        if isinstance(data, dict):
            identity = make_ref('qidian', data.get('bookId'))
            if identity:
                identities.append(identity)
    elif ref.provider == 'qimao':
        header = first(root, by_class('book-information'))
        if header is not None:
            for href in header.xpath('.//*[%s]//*[%s]/a/@href' % (
                    class_xpath('update-info'), class_xpath('update-chapter-title'))):
                try:
                    chapter = urlsplit(urljoin(ref.url, href))
                    match = re.fullmatch(r'/shuku/([0-9]{1,32})-[0-9]+/?', chapter.path)
                    if chapter.hostname == 'www.qimao.com' and match and chapter.scheme in ('http', 'https') and chapter.username is None and chapter.password is None and chapter.port is None:
                        identities.append(BookRef('qimao', match.group(1)))
                except ValueError:
                    continue
    else:
        page = initial_state(root).get('page', {})
        if isinstance(page, dict):
            identity = make_ref('fanqie', page.get('bookId'))
            if identity:
                identities.append(identity)
    if not identities:
        # A top-level Book / Baidu @id may prove identity. Nested recommendations
        # never do; multiple root book identities are deliberately ambiguous.
        for record in json_roots(root):
            add_url(record.get('@id') or record.get('url'))
    return identities


def parse_detail(source, ref, final_url=None):
    if final_url is not None and parse_book_url(final_url) != ref:
        raise ValueError('平台跳转后的地址与请求的作品不一致。')
    root = document(source)
    identities = _identity_evidence(root, ref)
    if not identities:
        raise ValueError('页面没有可靠的作品 ID；可能是验证页、搜索页或不完整的 HTML。')
    if any(identity != ref for identity in identities):
        raise ValueError('页面中的作品 ID 与输入链接不一致，已停止采用元数据。')
    if ref.provider == 'qidian':
        result = qidian.parse(root, ref, parse_book_url)
    elif ref.provider == 'qimao':
        result = qimao.parse(root, ref)
    else:
        result = fanqie.parse(root, ref, parse_book_url)
    for record in json_roots(root):
        types = record.get('@type', [])
        types = [types] if isinstance(types, str) else types
        own_url = record.get('@id') or record.get('url')
        if not isinstance(types, list) or 'Book' not in types or not isinstance(own_url, str) or parse_book_url(urljoin(ref.url, own_url)) != ref:
            continue
        result.title = result.title or clean(record.get('name'))
        authors = record.get('author', [])
        authors = authors if isinstance(authors, list) else [authors]
        if not result.authors:
            result.authors = unique(clean(author.get('name') if isinstance(author, dict) else author) for author in authors)
        result.description = result.description or clean(record.get('description'))
        result.cover_url = result.cover_url or image_url(record.get('image'), ref.url)
    if not result.title or not result.authors:
        raise ValueError('未识别到可靠的书名和作者；页面可能需要验证、登录或结构已变化。')
    result.published_at = publication_date(root, ref, parse_book_url)
    return result


def _search_json(data, provider):
    if not isinstance(data, dict):
        raise ValueError('平台搜索数据格式不正确。')
    for key in ('code', 'status_code'):
        value = data.get(key)
        if value not in (None, 0, '0', 200, '200'):
            raise ValueError('平台搜索暂时不可用或需要验证。')
    body = data.get('data')
    if not isinstance(body, dict):
        raise ValueError('平台搜索未返回作品列表。')
    key = 'search_list' if provider == 'qimao' else 'search_book_data_list'
    records = body.get(key)
    if not isinstance(records, list):
        raise ValueError('平台搜索未返回可识别的作品列表。')
    result = []
    for record in records:
        if not isinstance(record, dict):
            continue
        ref = make_ref(provider, record.get('book_id'))
        if ref:
            url = record.get('read_url')
            if isinstance(url, str) and parse_book_url(url) != ref:
                continue
            result.append(ref)
    return unique(result)


def parse_search(source, provider, base_url):
    if provider not in PROVIDERS:
        raise ValueError('未知的元数据来源。')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('搜索接口返回空响应，可能需要验证；不能据此判断没有作品。')
    if source.lstrip().startswith(('{', '[')):
        try:
            return _search_json(json.loads(source), provider)
        except json.JSONDecodeError as err:
            raise ValueError('搜索接口返回了无效的 JSON。') from err
    root = document(source)
    result = []
    if provider == 'qidian':
        script = first(root, '//script[@id="vite-plugin-ssr_pageContext"][@type="application/json"]')
        if script is not None:
            try:
                value = json.loads(script.text or '')
                records = value['pageContext']['pageProps']['pageData']['bookInfo']['records']
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict):
                            ref = make_ref(provider, record.get('bid'))
                            if ref:
                                result.append(ref)
            except (ValueError, KeyError, TypeError):
                pass
    elif provider == 'fanqie':
        search = initial_state(root).get('search', {})
        records = search.get('searchBookList') if isinstance(search, dict) else None
        if isinstance(records, list):
            for record in records:
                if isinstance(record, dict):
                    ref = make_ref(provider, record.get('book_id'))
                    if ref:
                        result.append(ref)
    for href in root.xpath('//a/@href'):
        ref = parse_book_url(urljoin(base_url, href))
        if ref and ref.provider == provider:
            result.append(ref)
    return unique(result)
