"""Bangumi public v0: book/novel subjects, never users' personal data."""
import re
from ..models import Record, isbn, clean

BASE = 'https://api.bgm.tv'


def _names(value):
    if isinstance(value, list):
        return [clean(v.get('v', '')) if isinstance(v, dict) else clean(v) for v in value if clean(v.get('v', '') if isinstance(v, dict) else v)]
    return [clean(value)] if clean(value) else []


def _infobox(data):
    result = {}
    for row in data.get('infobox', []):
        if isinstance(row, dict):
            result[clean(row.get('key'))] = _names(row.get('value'))
    return result


def parse_detail(data):
    if not isinstance(data, dict) or data.get('type') != 1:
        return None
    # The v0 detail may expose platform="小说" while some API snapshots
    # expose the numeric book category 1002. Never assume platform is numeric.
    cat = data.get('platform') or data.get('category')
    if str(cat) not in ('1002', '小说', '小說', '小説'):
        # Unknown book subtypes must not be mislabelled as novels.
        return None
    sid = str(data.get('id', ''))
    if not re.fullmatch(r'[1-9][0-9]{0,11}', sid):
        return None
    info = _infobox(data)
    def fields(*keys):
        return [n for k in keys for n in info.get(k, [])]
    authors = fields('作者', '著者', '原作', '著')
    illustrators = fields('插画', '插畫', '插图', '插圖', 'イラスト')
    translators = fields('译者', '譯者', '翻译', '翻譯')
    tags = [clean(t.get('name')) for t in data.get('tags', []) if isinstance(t, dict) and clean(t.get('name'))][:10]
    raw_isbn = next((isbn(v) for v in fields('ISBN', 'ISBN-13', 'ISBN13') if isbn(v)), '')
    pic = data.get('images') or {}
    cover = pic.get('large', '') if isinstance(pic, dict) else ''
    if cover.startswith('http://lain.bgm.tv/'):
        cover = 'https://' + cover[len('http://'):]
    if 'no_icon_subject' in cover:
        cover = ''
    title = clean(data.get('name_cn') or data.get('name'))
    if not title:
        return None
    original = clean(data.get('name'))
    date_value = clean(data.get('date'))
    series_flag = data.get('series') is True
    publisher = fields('出版社', '出版', '发行', '發行', '出版社/品牌')
    return Record('bangumi', sid, title, authors, raw_isbn,
                  original_title=original if original != title else '',
                  publisher=publisher[0] if publisher else '',
                  pubdate=date_value, date_text=date_value, language=('jpn' if raw_isbn.startswith('9784') else 'zho' if raw_isbn.startswith(('978626','978986')) else ''),
                  description=clean(data.get('summary', '')), cover=cover,
                  url='https://bgm.tv/subject/' + sid, tags=tags,
                  translators=translators, illustrators=illustrators, work_level=series_flag)


def search(client, title, max_candidates=5):
    if not title:
        return []
    body = {'keyword': title, 'sort': 'match', 'filter': {'type': [1]}}
    data = client.json(BASE + '/v0/search/subjects?limit=%s&offset=0' % min(12, max_candidates * 2), body)
    if not isinstance(data, dict) or not isinstance(data.get('data'), list):
        raise ValueError('Bangumi 搜索结构发生变化。')
    candidates = []
    for entry in data['data']:
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get('id', ''))
        if (re.fullmatch(r'[1-9][0-9]{0,11}', sid) and entry.get('type') == 1
                and str(entry.get('platform') or entry.get('category') or '') not in ('1001', '1003', '漫画', '漫畫', '画集', '畫集')):
            candidates.append(sid)
    return list(dict.fromkeys(candidates))[:max_candidates]


def detail(client, sid):
    if not re.fullmatch(r'[1-9][0-9]{0,11}', str(sid)):
        raise ValueError('Bangumi Subject ID 不正确。')
    result = parse_detail(client.json(BASE + '/v0/subjects/' + str(sid)))
    if result is None or result.source_id != str(sid):
        raise ValueError('Bangumi 条目身份或类别与请求不一致。')
    return result


RELATION_TO_SERIES = frozenset(('单行本', '單行本', '系列', '主系列', '系列作品'))


def parse_relations(data):
    """Keep only explicit book-to-book relations; never infer via adaptations."""
    if not isinstance(data, list):
        raise ValueError('Bangumi 条目关联返回结构异常。')
    output = []
    for link in data[:80]:
        if not isinstance(link, dict) or link.get('type') != 1:
            continue
        sid = str(link.get('id', ''))
        relation = clean(link.get('relation'))
        if not re.fullmatch(r'[1-9][0-9]{0,11}', sid) or not relation:
            continue
        output.append({'id': sid, 'relation': relation,
                       'name': clean(link.get('name_cn') or link.get('name'))})
    return output


def enrich_series(client, record):
    """Resolve at most two explicit related series, without merging editions.

    Bangumi's relation vocabulary is not a guaranteed series designation.
    Confirm the related entry is an actual book series before assigning it.
    """
    if record.source != 'bangumi' or record.work_level:
        return record
    data = client.json(BASE + '/v0/subjects/' + record.source_id + '/subjects')
    record.relations = parse_relations(data)
    candidates = [x for x in record.relations if x['relation'] in RELATION_TO_SERIES]
    for rel in candidates[:2]:
        parent = detail(client, rel['id'])
        if parent.work_level and parent.title:
            record.series_subject_id = parent.source_id
            # Calibre series ordering requires a *known* volume number.
            if record.series_index is not None:
                record.series = parent.title
            break
    return record
