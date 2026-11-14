"""National Diet Library OpenSearch: title and ISBN edition bibliography."""
import re
from xml.etree import ElementTree as ET
from urllib.parse import urlencode
from ..models import Record, isbn, clean

BASE = 'https://ndlsearch.ndl.go.jp/api/opensearch?'


def url_for(title='', isbn_value='', count=8):
    params = {'cnt': min(15, max(1, int(count)))}
    if isbn_value:
        valid = isbn(isbn_value)
        if not valid:
            raise ValueError('NDL 查询 ISBN 不合法。')
        params['isbn'] = valid
    elif title:
        params['title'] = clean(title)
    else:
        raise ValueError('请提供题名或有效 ISBN。')
    return BASE + urlencode(params)


def _first(node, local):
    for item in node.iter():
        if item is not node and item.tag.rsplit('}', 1)[-1].lower() == local.lower():
            value = clean(''.join(item.itertext()))
            if value:
                return value
    return ''


def parse_search(payload, expected_isbn=''):
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError('日本国会图书馆没有返回有效 XML。') from exc
    records = []
    expected = isbn(expected_isbn)
    for item in root.iter():
        if item.tag.rsplit('}', 1)[-1] != 'item':
            continue
        title = _first(item, 'title')
        if not title:
            continue
        fields = [clean(''.join(x.itertext())) for x in item.iter() if x.tag.rsplit('}', 1)[-1].lower() in ('identifier', 'isbn')]
        found = next((isbn(re.search(r'(97[89][0-9\- ]{10,18}|[0-9]{9}[0-9X])', text, re.I).group(1))
                      for text in fields if re.search(r'(97[89][0-9\- ]{10,18}|[0-9]{9}[0-9X])', text, re.I)
                      and isbn(re.search(r'(97[89][0-9\- ]{10,18}|[0-9]{9}[0-9X])', text, re.I).group(1))), '')
        if expected and found != expected:
            continue
        link = _first(item, 'link')
        # Titles can repeat across editions. Keep each ISBN distinct.
        if link and not link.startswith('https://ndlsearch.ndl.go.jp/'):
            link = ''
        sid = found or link
        if not sid:
            continue
        creators = [clean(''.join(x.itertext())) for x in item.iter()
                    if x.tag.rsplit('}', 1)[-1] == 'creator' and clean(''.join(x.itertext()))]
        publisher = _first(item, 'publisher')
        date = _first(item, 'issued') or _first(item, 'date')
        records.append(Record('ndl', sid, title, creators[:5], found, publisher=publisher,
                              pubdate=date, date_text=date, language='jpn' if found.startswith('9784') else '',
                              description=_first(item, 'description'), url=link))
    return records


def search(client, title='', isbn_value='', limit=8):
    return parse_search(client.read(url_for(title, isbn_value, limit)), expected_isbn=isbn_value)
