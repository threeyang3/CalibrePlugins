"""Taiwan KADOKAWA publisher listings, keyed by the edition's ISBN.

No keyword endpoint is assumed. Only an ISBN-identity product page is read;
preorder bundles and arbitrary store SKUs are explicitly not ISBN records.
"""
import re
from urllib.parse import urlsplit
from lxml import etree, html
from ..models import Record, clean, isbn

DOMAIN = 'www.kadokawa.com.tw'
PRODUCT = 'https://' + DOMAIN + '/products/{}'


def isbn_from_url(url):
    try:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme != 'https' or parsed.hostname != DOMAIN or parsed.username or parsed.password or parsed.port:
            return ''
        match = re.fullmatch(r'/products/([0-9]{13})/?', parsed.path)
        return isbn(match.group(1)) if match else ''
    except ValueError:
        return ''


def _page(source):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('台湾角川返回空页面。')
    try:
        root = html.document_fromstring(source, parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError) as error:
        raise ValueError('台湾角川页面无法解析。') from error
    return root


def _text(nodes):
    return clean(' '.join(' '.join(x.itertext()) for x in nodes))


def _field(text, label, end):
    matched = re.search(label + r'\s*[：:]\s*(.{1,110}?)(?=\s*(?:' + end + r')\s*[：:]|$)', text)
    return clean(matched.group(1)) if matched else ''


def parse_detail(source, expected):
    code = isbn(expected)
    if not code or expected != code:
        raise ValueError('台湾角川需要有效 ISBN-13。')
    root = _page(source)
    urls = (root.xpath('//link[contains(concat(" ", normalize-space(@rel), " "), " canonical ")]/@href') +
            root.xpath('//meta[@property="og:url"]/@content'))
    if not urls or any(isbn_from_url(u) != code for u in urls):
        raise ValueError('台湾角川商品页面缺少匹配 ISBN 的规范地址。')
    # Restrict edition verification to published product details, not a random
    # ISBN elsewhere in site navigation or other promoted titles.
    for fragment in root.xpath('//script|//style|//noscript'):
        fragment.drop_tree()
    body = _text(root.xpath('//body')[:1])
    matched = re.search(r'ISBN\s*[：:]\s*([0-9\- ]{13,21})', body, re.I)
    if not matched or isbn(matched.group(1)) != code:
        raise ValueError('台湾角川页面 ISBN 与请求版本不一致。')
    title = _text(root.xpath('//h1')[:1])
    if not title:
        raise ValueError('台湾角川未返回书名。')
    author_info = _field(body, '作者資訊', '上市日期|ISBN|商品描述|作者介紹')
    author_info = author_info or _field(body, '作者', '插畫|插画|上市日期|ISBN')
    author_parts = [clean(x) for x in re.split(r'\s*/\s*', author_info) if clean(x)]
    authors, illustrators, translators = [], [], []
    for part in author_parts:
        if re.match(r'^(?:插畫|插画|插圖|繪者)\s*[：:]', part):
            illustrators.append(re.split(r'[：:]', part, maxsplit=1)[-1].strip())
        elif re.match(r'^(?:譯者|译者|翻譯)\s*[：:]', part):
            translators.append(re.split(r'[：:]', part, maxsplit=1)[-1].strip())
        elif re.match(r'^(?:作者|著者)\s*[：:]', part):
            authors.append(re.split(r'[：:]', part, maxsplit=1)[-1].strip())
        elif re.match(r'^(?:原作|漫畫|漫画|角色原案)\s*[：:]', part):
            # Do not put the original work writer in the comic's book author slot.
            continue
        else:
            authors.append(part)
    published = re.search(r'上市日期\s*[：:]\s*(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})', body)
    date_text = published.group(1) if published else ''
    description = (body.split('〖內容介紹〗', 1)[1].split('〖作者介紹〗', 1)[0][:5000] if '〖內容介紹〗' in body else '')
    image = root.xpath('//meta[@property="og:image"]/@content')
    return Record('kadokawa_tw', code, title, authors, code, publisher='台灣角川',
                  pubdate=date_text, date_text=date_text, language='zho',
                  description=description[:5000], cover=clean(image[0]) if image else '',
                  url=PRODUCT.format(code), illustrators=illustrators,
                  translators=translators, tags=['台版'])


def detail(client, code):
    code = isbn(code)
    if not code:
        raise ValueError('台湾角川需要有效 ISBN。')
    return parse_detail(client.text(PRODUCT.format(code)), code)
