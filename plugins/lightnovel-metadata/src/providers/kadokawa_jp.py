"""KADOKAWA Japan's public store discovery and publisher edition pages."""

import re
from urllib.parse import urljoin, urlsplit

from lxml import etree, html

from ..models import Record, clean, isbn


STORE = 'https://store.kadokawa.co.jp'
SEARCH = STORE + '/shop/goods/search.aspx?keyword={}'
PRODUCT = 'https://www.kadokawa.co.jp/product/{}/'
ID = re.compile(r'[0-9]{12}')
COMIC_CATEGORIES = {'コミック', 'コミックス', '漫画'}


def product_id(value):
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or url.username or url.password or url.port:
            return ''
        if url.hostname == 'www.kadokawa.co.jp':
            pattern = r'/product/([0-9]{12})/?'
        elif url.hostname == 'store.kadokawa.co.jp':
            pattern = r'/shop/g/g([0-9]{12})/?'
        else:
            return ''
        match = re.fullmatch(pattern, url.path)
        return match.group(1) if match else ''
    except (TypeError, ValueError):
        return ''


def _doc(source):
    try:
        return html.document_fromstring(source, parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError) as error:
        raise ValueError('KADOKAWA 页面不能解析。') from error


def _text(node):
    return clean(node.text_content()) if node is not None else ''


def search_ids(source, limit):
    root = _doc(source)
    result = root.xpath('//a[contains(concat(" ", normalize-space(@class), " "), " js-enhanced-ecommerce-image ")]/@href')
    ids = (product_id(urljoin(STORE, href)) for href in result)
    return list(dict.fromkeys(value for value in ids if value))[:limit]


def search(client, code, limit=3):
    code = isbn(code)
    if not code.startswith('9784'):
        return []
    return search_ids(client.text(SEARCH.format(code)), limit)


def _cover_url(root, pid):
    for value in root.xpath('/html/head/meta[@property="og:image"]/@content'):
        try:
            url = urlsplit(value)
            if (
                url.scheme == 'https' and url.netloc == 'cdn.kdkw.jp'
                and re.fullmatch(r'/cover_1000/' + pid[:6] + '/' + pid + r'\.(?:webp|jpe?g|png)', url.path)
            ):
                return value
        except ValueError:
            continue
    return ''


def parse_detail(source, pid, expected_isbn=''):
    if not ID.fullmatch(pid):
        raise ValueError('KADOKAWA 商品 ID 不合法。')
    root = _doc(source)
    identities = root.xpath('/html/head/link[@rel="canonical"]/@href | /html/head/meta[@property="og:url"]/@content')
    if not identities or any(product_id(value) != pid for value in identities):
        raise ValueError('KADOKAWA 商品页面指向不同条目或缺少商品标识。')

    categories = root.xpath('//*[@itemtype="https://schema.org/BreadcrumbList"]//span[@itemprop="name"]/text()')
    if COMIC_CATEGORIES.intersection(clean(value) for value in categories):
        raise ValueError('这是漫画版，已跳过。')

    work_examples = root.xpath('//dl[@itemprop="workExample"]/dd[@itemprop="isbn"]')
    declared = {_text(node) for node in work_examples}
    codes = {isbn(value) for value in declared if value}
    if len(codes) != 1 or not next(iter(codes)).startswith('9784'):
        raise ValueError('KADOKAWA 商品缺少唯一有效的日本 ISBN。')
    code, = codes
    if expected_isbn and code != expected_isbn:
        raise ValueError('KADOKAWA 商品 ISBN 与请求不一致。')

    heading = root.xpath('//h1[@itemprop="name" and (@id="book-title" or @id="book-title-sp")]')
    titles = {_text(node) for node in heading if _text(node)}
    if len(titles) != 1:
        raise ValueError('KADOKAWA 商品缺少唯一书名。')
    title, = titles
    authors, illustrators, translators = [], [], []
    roles = {'著者': authors, 'イラスト': illustrators, '訳': translators, '翻訳': translators}
    for node in root.xpath('//ul[@itemprop="author"]/li'):
        role, _, name = _text(node).partition(' ')
        if role in roles and name:
            roles[role].append(name)

    dates = root.xpath('//span[@itemprop="datePublished"]/@content')
    descriptions = root.xpath('//*[@id="book-description"]//*[contains(concat(" ", normalize-space(@class), " "), " show-text ")]')
    date = dates[0] if dates else ''
    return Record('kadokawa_jp', pid, title, authors, code, publisher='KADOKAWA',
                  pubdate=date, date_text=date, language='jpn',
                  description=_text(descriptions[0]) if descriptions else '',
                  cover=_cover_url(root, pid), url=PRODUCT.format(pid),
                  illustrators=illustrators, translators=translators)


def detail(client, pid, expected_isbn=''):
    if not ID.fullmatch(pid):
        raise ValueError('KADOKAWA 商品 ID 不合法。')
    return parse_detail(client.text(PRODUCT.format(pid)), pid, expected_isbn)
