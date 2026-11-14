"""Taiwan SPP/尖端 official sale-page ISBN data, keyed by numeric product ID.

No undocumented site-search API is used. Users may provide a direct product
URL; the ISBN is required to prove a physical book edition.
"""
import re
from urllib.parse import urlsplit
from lxml import etree, html
from ..models import Record, clean, isbn

DOMAIN = 'www.spp.com.tw'
PRODUCT = 'https://' + DOMAIN + '/SalePage/Index/{}'
ID = re.compile(r'[1-9][0-9]{4,11}$')


def product_id(url):
    try:
        p = urlsplit(str(url).strip())
        if p.scheme != 'https' or p.hostname != DOMAIN or p.username or p.password or p.port:
            return ''
        m = re.fullmatch(r'/SalePage/Index/([1-9][0-9]{4,11})/?', p.path, re.I)
        return m.group(1) if m else ''
    except ValueError:
        return ''


def _visible(node):
    # Drop script/style so identity is not accidentally drawn from a random JSON
    # response used for other product cards.
    for fragment in node.xpath('.//script|.//style|.//noscript'):
        fragment.drop_tree()
    return clean(' '.join(node.itertext()))


def parse_detail(source, requested):
    pid = str(requested)
    if not ID.fullmatch(pid):
        raise ValueError('尖端商品 ID 无效。')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('尖端商品页面为空。')
    try:
        root = html.document_fromstring(source, parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError) as err:
        raise ValueError('尖端商品页面无法解析。') from err
    urls = (root.xpath('//link[@rel="canonical"]/@href') + root.xpath('//meta[@property="og:url"]/@content'))
    if urls and any(product_id(u) != pid for u in urls):
        raise ValueError('尖端商品页面跳转到不同的商品。')
    body_nodes = root.xpath('//body')
    body = _visible(body_nodes[0]) if body_nodes else ''
    if not urls and not re.search(r'商品編號\s*[：:]?\s*' + re.escape(pid) + r'\b', body):
        raise ValueError('页面缺少可核对的尖端商品身份。')
    # Isolate official 商品特色 before reading barcodes; the bottom of the page
    # may contain recommendations for unrelated books.
    details = body.split('商品特色', 1)[-1].split('銷售重點', 1)[0][:3500]
    code_match = re.search(r'條\s*碼\s*[：:]\s*([0-9\- ]{10,20})', details)
    code = isbn(code_match.group(1)) if code_match else ''
    if not code:
        raise ValueError('尖端商品缺少有效 ISBN，可能是周边或特装礼包。')
    heads = root.xpath('//h1')
    title = _visible(heads[0]) if heads else ''
    if not title:
        titles = root.xpath('//meta[@property="og:title"]/@content')
        title = clean(titles[0]) if titles else ''
    title = re.sub(r'\s*[|｜]\s*尖端.*$', '', title)
    if not title:
        raise ValueError('尖端页面没有书名。')
    labels = r'(?:條\s*碼|書\s*號|作\s*者|繪\s*者|譯\s*者|書\s*系|規\s*格|等\s*級|上市日)'
    def field(label):
        m = re.search(label + r'\s*[：:]\s*(.*?)\s*(?=' + labels + r'\s*[：:]|$)', details)
        return clean(m.group(1)) if m else ''
    fields = {k: field(v) for k, v in
              [('author', r'作\s*者'), ('illustrator', r'繪\s*者'),
               ('translator', r'譯\s*者'), ('date', '上市日')]}
    date = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', fields['date'])
    cover = root.xpath('//meta[@property="og:image"]/@content')
    return Record('spp_tw', pid, title, [fields['author']] if fields['author'] else [], code,
                  publisher='尖端出版', pubdate=date.group(1) if date else '',
                  date_text=date.group(1) if date else '', language='zho',
                  cover=clean(cover[0]) if cover else '', url=PRODUCT.format(pid),
                  illustrators=[fields['illustrator']] if fields['illustrator'] else [],
                  translators=[fields['translator']] if fields['translator'] else [], tags=['台版'])


def detail(client, pid):
    if not ID.fullmatch(str(pid)):
        raise ValueError('尖端商品 ID 无效。')
    return parse_detail(client.text(PRODUCT.format(pid)), str(pid))
