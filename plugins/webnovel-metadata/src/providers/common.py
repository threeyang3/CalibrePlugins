"""Small, non-executing HTML helpers shared by the three public sites."""

import ipaddress
import json
import re
from datetime import date
from urllib.parse import urljoin, urlsplit

from lxml import etree, html


def class_xpath(name):
    return "contains(concat(' ', normalize-space(@class), ' '), ' %s ')" % name


def by_class(name):
    return './/*[%s]' % class_xpath(name)


def clean(value):
    if not isinstance(value, str):
        return ''
    return re.sub(r'\s+', ' ', value.replace('\xa0', ' ')).strip()


def node_text(node, breaks=False):
    """Convert only visible text; preserve synopsis paragraphs without HTML."""
    if node is None:
        return ''
    pieces = []

    def visit(element):
        if not isinstance(element.tag, str):
            return
        tag = element.tag.lower()
        if tag in ('script', 'style', 'noscript'):
            return
        if tag == 'br':
            pieces.append('\n')
        elif tag in ('p', 'div', 'li') and pieces:
            pieces.append('\n' if breaks else ' ')
        if element.text:
            pieces.append(element.text)
        for child in element:
            visit(child)
            if child.tail:
                pieces.append(child.tail)
        if tag in ('p', 'div', 'li'):
            pieces.append('\n' if breaks else ' ')

    visit(node)
    value = ''.join(pieces).replace('\xa0', ' ')
    if not breaks:
        return clean(value)
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    lines = [re.sub(r'[\t ]+', ' ', line).strip() for line in value.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def first(root, *paths):
    if root is None:
        return None
    for path in paths:
        found = root.xpath(path)
        if found:
            return found[0]
    return None


def text(root, *paths, **kwargs):
    return node_text(first(root, *paths), breaks=kwargs.get('breaks', False))


def attr(root, path, name):
    node = first(root, path)
    return clean(node.get(name)) if node is not None else ''


def meta(root, key):
    values = root.xpath('//meta[@property=$key or @name=$key]/@content', key=key)
    return clean(values[0]) if values else ''


def document(source):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('平台返回了空页面，可能需要在浏览器中完成正常访问。')
    try:
        # HTMLParser does not run JavaScript or load remote resources.
        parser = html.HTMLParser(no_network=True)
        return html.document_fromstring(source, parser=parser)
    except (etree.ParserError, ValueError) as err:
        raise ValueError('平台页面无法解析。') from err


def json_roots(root):
    """Read JSON-LD root objects, never nested recommendations or arbitrary JS."""
    result = []
    for node in root.xpath('//script[@type="application/ld+json"]'):
        try:
            parsed = json.loads(node.text or '')
        except (ValueError, TypeError):
            continue
        roots = parsed if isinstance(parsed, list) else [parsed]
        for value in roots:
            if not isinstance(value, dict):
                continue
            result.append(value)
            graph = value.get('@graph')
            if isinstance(graph, list):
                result.extend(item for item in graph if isinstance(item, dict))
    return result


def initial_state(root):
    """Fanqie emits a JSON literal after this assignment; parse, never eval it."""
    for node in root.xpath('//script[not(@src)]'):
        source = node.text or ''
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*', source)
        if not match:
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(source[match.end():])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def status(value):
    value = clean(value)
    if re.search(r'完结|完本|已完成', value):
        return '已完结'
    if re.search(r'暂停|停更|断更', value):
        return '暂停更新'
    if '连载' in value:
        return '连载中'
    return ''


def image_url(value, base):
    """Reject placeholders and URLs that cannot represent a public image."""
    if not isinstance(value, str) or not value.strip():
        return ''
    try:
        url = urljoin(base, value.strip())
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return ''
        if parts.username is not None or parts.password is not None or parts.port is not None:
            return ''
        hostname = parts.hostname.lower()
        if hostname == 'localhost' or hostname.endswith(('.localhost', '.local')):
            return ''
        try:
            ipaddress.ip_address(hostname)
            return ''  # Public platforms use CDN domain names, not IP literals.
        except ValueError:
            pass
        path = parts.path.lower()
        if re.search(r'(?:^|[/_.-])(?:placeholder|loading|no[-_]?cover|default[-_]?cover)(?:[/_.-]|$)', path):
            return ''
        if '/novel-static/5cb03bd354145bc7815a5e09d4b15cfc' in path:
            return ''
        return url
    except (ValueError, TypeError):
        return ''


def publication_date(root, ref, parse_url):
    """Only a field explicitly describing the work's publication can fill this."""
    candidates = [meta(root, key) for key in (
        'og:novel:published_time', 'og:novel:publish_time',
        'og:novel:first_publish_time',
    )]
    for record in json_roots(root):
        types = record.get('@type', [])
        types = [types] if isinstance(types, str) else types
        if not isinstance(types, list) or 'Book' not in types:
            continue
        own_url = record.get('@id') or record.get('url')
        if not isinstance(own_url, str) or parse_url(urljoin(ref.url, own_url)) != ref:
            continue
        candidates.append(record.get('datePublished'))
    for value in candidates:
        if not isinstance(value, str):
            continue
        match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:$|[T ])', value.strip())
        if not match:
            continue
        try:
            return date(*[int(part) for part in match.groups()]).isoformat()
        except ValueError:
            continue
    return ''


def unique(values):
    return list(dict.fromkeys(value for value in values if value))
