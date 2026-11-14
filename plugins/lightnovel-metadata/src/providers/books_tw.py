"""Taiwan Books.com.tw print-edition search and product-page extraction.

No login, no book content. This HTML adapter is intentionally replaceable and
rejects pages missing a product-bound ISBN rather than trusting recommendations.
"""
import json
import re
from urllib.parse import quote, urljoin, urlsplit
from lxml import etree, html
from ..models import Record, clean, isbn

SEARCH = 'https://search.books.com.tw/search/query/key/{}/cat/BKA'
PRODUCT = 'https://www.books.com.tw/products/{}'
ID = re.compile(r'^001[0-9]{7}$')


def product_id(value):
    try:
        url = urlsplit(str(value).strip())
        if url.scheme != 'https' or url.hostname != 'www.books.com.tw' or url.port or url.username or url.password:
            return ''
        match = re.fullmatch(r'/products/(001[0-9]{7})/?', url.path)
        return match.group(1) if match else ''
    except ValueError:
        return ''


def _doc(source):
    if not source or not source.strip():
        raise ValueError('博客来返回空白页面。')
    try:
        return html.document_fromstring(source, parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError) as e:
        raise ValueError('博客来页面不能解析。') from e


def _metas(root, key):
    values = root.xpath('//meta[@property=$key or @name=$key]/@content', key=key)
    return clean(values[0]) if values else ''


def _text(nodes):
    return clean(' '.join(' '.join(node.itertext()) for node in nodes))


def search_ids(source, limit=5):
    root = _doc(source)
    ids = []
    # Restrict to printed-book product URLs and preserve search ranking.
    for path in root.xpath('//a[@href]/@href'):
        full = urljoin('https://search.books.com.tw/', path)
        key = product_id(full.split('?', 1)[0])
        if key and key not in ids:
            ids.append(key)
            if len(ids) >= limit:
                break
    return ids


def _structured_book(root, expected):
    for script in root.xpath('//script[@type="application/ld+json"]'):
        try:
            parsed = json.loads(script.text or '{}')
        except (TypeError, ValueError):
            continue
        data = parsed if isinstance(parsed, list) else [parsed]
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if entry.get('@type') not in ('Book', 'Product'):
                continue
            url = entry.get('url') or entry.get('@id') or ''
            if url and product_id(url.split('?', 1)[0]) != expected:
                continue
            # Prefer page-bound structured metadata, never an unrelated work in @graph.
            yield entry


def _names(raw):
    raw = raw if isinstance(raw, list) else [raw]
    return [clean(x.get('name', '')) if isinstance(x, dict) else clean(x) for x in raw if clean(x.get('name', '') if isinstance(x, dict) else x)]


def parse_detail(source, expected):
    if not ID.fullmatch(str(expected)):
        raise ValueError('博客来商品 ID 不合法。')
    root = _doc(source)
    page_urls = (root.xpath('//link[@rel="canonical"]/@href') +
                 root.xpath('//meta[@property="og:url"]/@content'))
    identities = [product_id(raw.split('?', 1)[0]) for raw in page_urls]
    if not identities or any(identity != expected for identity in identities):
        raise ValueError('博客来页面缺少可靠商品标识或指向另一件商品，已拒绝。')
    structured = next(_structured_book(root, expected), {})
    title = clean(structured.get('name') or _metas(root, 'og:title'))
    # The page's own h1 is preferred over browser and OG suffixes when present.
    heading = _text(root.xpath('//h1')[:1])
    if heading:
        title = heading
    if not title:
        raise ValueError('未找到书名。')
    title = re.sub(r'^博客來[-－—:]\s*', '', title)
    top = _text(root.xpath('//div[contains(@class,"type02_p003")]')[:1])
    if not top:
        top = _text(root.xpath('//body')[:1])[:7000]
    detail_section = _text(root.xpath('//*[contains(@class,"bd") and contains(@class,"type02_m02")]')[:1])
    # Attribute section is the source of truth for ISBN, not random recommended products.
    detail_match = re.search(r'詳細資料(.{0,3000})', detail_section or top, re.S)
    detail_str = detail_match.group(1) if detail_match else top
    declared = isbn(structured.get('isbn', '') or _metas(root, 'books:isbn'))
    detected = next((isbn(m.group(1)) for m in re.finditer(r'ISBN\s*[：:]?\s*([0-9\-]{10,22})', detail_str, re.I)
                     if isbn(m.group(1))), '')
    if declared and detected and declared != detected:
        raise ValueError('博客来 ISBN 字段存在冲突。')
    code = declared or detected
    if not code:
        raise ValueError('当前页面缺少商品所属 ISBN，不能安全匹配出版版本。')
    authors = _names(structured.get('author', []))
    match_author = re.search(r'(?:^|\s)作者\s*[：:]\s*(.{1,90}?)(?=\s*(?:譯者|译者|出版社|出版日期|語言|語系|原文作者)\s*[：:]|$)', top)
    if match_author and not authors:
        authors = [clean(match_author.group(1))]
    pub = re.search(r'出版社\s*[：:]\s*(.{1,70}?)(?=\s*(?:出版日期|語言|譯者|译者|ISBN)\s*[：:]|$)', top)
    publisher = clean((structured.get('publisher') or {}).get('name', '') if isinstance(structured.get('publisher'), dict) else structured.get('publisher', '')) or (clean(pub.group(1)) if pub else '')
    dt = re.search(r'出版日期\s*[：:]\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})', top)
    date_text = clean(structured.get('datePublished') or (dt.group(1) if dt else ''))
    translator = re.search(r'[譯译]者\s*[：:]\s*(.{1,80}?)(?=\s*(?:出版社|出版日期|語言|原文作者)\s*[：:]|$)', top)
    illustration = re.search(r'(?:插畫|插图|插畫家)\s*[：:]\s*(.{1,80}?)(?=\s*(?:出版社|出版日期|語言)\s*[：:]|$)', top)
    blurb = clean(structured.get('description') or '')
    if not blurb:
        intro = root.xpath('//*[contains(@class,"type02_p006")]')
        if intro:
            blurb = _text(intro[:1])[:5000]
    cover = structured.get('image') or _metas(root, 'og:image')
    if isinstance(cover, list):
        cover = cover[0] if cover else ''
    if isinstance(cover, dict):
        cover = cover.get('url', '')
    return Record('books_tw', expected, title, authors, code, publisher=publisher,
                  pubdate=date_text, date_text=date_text, language='zho',
                  description=blurb, cover=clean(cover), url=PRODUCT.format(expected),
                  translators=[translator.group(1)] if translator else [],
                  illustrators=[illustration.group(1)] if illustration else [], tags=['台版'])


def search(client, query, limit=5):
    if not clean(query):
        return []
    return search_ids(client.text(SEARCH.format(quote(query, safe=''))), limit)


def detail(client, pid):
    if not ID.fullmatch(str(pid)):
        raise ValueError('无效的博客来印刷书商品 ID。')
    return parse_detail(client.text(PRODUCT.format(pid)), str(pid))
