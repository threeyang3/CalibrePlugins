"""Sanmin Taiwan's public edition records, matched by the product's own ISBN."""

import json
import re
from urllib.parse import urljoin, urlsplit

from lxml import etree, html

from ..models import Record, clean, isbn


BASE = 'https://www.sanmin.com.tw'
SEARCH = BASE + '/search?isbn={}'
PRODUCT = BASE + '/product/index/{}'
ID = re.compile(r'[0-9]{9}')
TAIWAN_PREFIXES = ('978626', '978957', '978986')


def product_id(value):
    if not isinstance(value, str):
        return ''
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or url.netloc != 'www.sanmin.com.tw':
            return ''
        match = re.fullmatch(r'/product/index/([0-9]{9})/?', url.path)
        return match.group(1) if match else ''
    except ValueError:
        return ''


def _doc(source):
    try:
        return html.document_fromstring(source, parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError) as error:
        raise ValueError('三民页面不能解析。') from error


def _text(node):
    return clean(node.text_content()) if node is not None else ''


def search_ids(source, limit):
    root = _doc(source)
    links = root.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " sProduct ")]//a/@href')
    ids = (product_id(urljoin(BASE, value)) for value in links)
    return list(dict.fromkeys(value for value in ids if value))[:limit]


def search(client, code, limit=3):
    code = isbn(code)
    if not code.startswith(TAIWAN_PREFIXES):
        return []
    return search_ids(client.text(SEARCH.format(code)), limit)


def _book_data(root, pid):
    for script in root.xpath('//script[@type="application/ld+json"]'):
        try:
            data = json.loads(script.text or '')
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get('@type') != 'Book':
            continue
        urls = [value for value in (data.get('@id'), data.get('url')) if value]
        if urls and all(product_id(value) == pid for value in urls):
            yield data


def _attributes(root):
    fields = {}
    rows = root.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " ProductInfo ")]'
                      '//*[contains(concat(" ", normalize-space(@class), " "), " ProdAttr ")]/li/h3')
    for row in rows:
        key = row.xpath('./span[contains(concat(" ", normalize-space(@class), " "), " Bold ")]')
        value = row.xpath('./span[contains(concat(" ", normalize-space(@class), " "), " colon ")]/following-sibling::span[1]')
        if key and value and _text(value[0]):
            fields.setdefault(_text(key[0]), []).append(_text(value[0]))
    return fields


def _cover(root, books, code):
    images = root.xpath('/html/head/meta[@property="og:image"]/@content')
    images.extend(book.get('image') for book in books if book.get('image'))
    if not images or any(not isinstance(value, str) for value in images):
        return ''
    urls = set(images)
    if len(urls) != 1:
        return ''
    value, = urls
    try:
        url = urlsplit(value)
    except ValueError:
        return ''
    pattern = r'/product_images/' + code[3:6] + '/' + code[3:-1] + r'\.(?:jpe?g|png|webp)'
    if url.scheme == 'https' and url.netloc == 'cdnec.sanmin.com.tw' and re.fullmatch(pattern, url.path):
        return value
    return ''


def parse_detail(source, pid, expected_isbn=''):
    if not ID.fullmatch(pid):
        raise ValueError('三民商品 ID 不合法。')
    root = _doc(source)
    urls = root.xpath('/html/head/link[@rel="canonical"]/@href | /html/head/meta[@property="og:url"]/@content')
    if not urls or any(product_id(value) != pid for value in urls):
        raise ValueError('三民商品页面指向不同条目或缺少商品标识。')

    fields = _attributes(root)
    books = list(_book_data(root, pid))
    declared = fields.get('ISBN13', []) + [book['isbn'] for book in books if book.get('isbn')]
    codes = {isbn(value) for value in declared}
    if len(codes) != 1 or not next(iter(codes)).startswith(TAIWAN_PREFIXES):
        raise ValueError('三民商品缺少唯一有效的台版 ISBN。')
    code, = codes
    if expected_isbn and code != expected_isbn:
        raise ValueError('三民商品 ISBN 与请求不一致。')

    heading = root.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " ProductInfo ")]/h1')
    title = _text(heading[0]) if heading else ''
    if not title:
        raise ValueError('三民商品缺少书名。')
    formats = [str(book.get('bookFormat') or book.get('BookFormat') or '') for book in books]
    binding = fields.get('裝訂', []) + fields.get('裝訂／頁數', [])
    if (
        any(re.search(r'電子書|电子书|EPUB|PDF', value, re.I) for value in [title, *binding])
        or any(value.lower().endswith(('ebook', 'audiobook')) for value in formats)
    ):
        raise ValueError('三民商品是电子书或有声版，已跳过。')

    date = next(iter(fields.get('出版日', [])), '')
    description = root.xpath('//*[@id="Intro1"]/following-sibling::*[1]'
                             '[contains(concat(" ", normalize-space(@class), " "), " SectionBody ")]')
    return Record(
        'sanmin_tw', pid, title, fields.get('作者', []), code,
        original_title=next(iter(fields.get('原文書名', [])), ''),
        publisher=next(iter(fields.get('出版社', [])), ''),
        pubdate=date, date_text=date, language='zho',
        description=_text(description[0]) if description else '',
        cover=_cover(root, books, code), url=PRODUCT.format(pid),
        illustrators=fields.get('繪者', []) + fields.get('插畫', []),
        translators=fields.get('譯者', []),
    )


def detail(client, pid, expected_isbn=''):
    if not ID.fullmatch(pid):
        raise ValueError('三民商品 ID 不合法。')
    return parse_detail(client.text(PRODUCT.format(pid)), pid, expected_isbn)
